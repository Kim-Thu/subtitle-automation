import os
import sys
import threading

# Add local 'bin' folder to PATH for FFmpeg
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
if os.path.exists(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ["PATH"]

import uuid
import time
import whisper
import requests # Added for Ollama proxy
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, send_from_directory
# Use modular pipeline instead of legacy script
from modules.workflow import process_video_pipeline
from modules.utils import resolve_managed_path, normalize_relative_path

# Import Gemini client (optional)
try:
    from modules.translation import test_gemini_connection, GEMINI_AVAILABLE
    print(f"DEBUG: app.py imported GEMINI_AVAILABLE = {GEMINI_AVAILABLE}")
except ImportError as e:
    print(f"Error importing Gemini client: {e}")
    GEMINI_AVAILABLE = False
    def test_gemini_connection(api_key):
        return {"success": False, "error": "Gemini client not available"}

app = Flask(__name__)

# Configuration
INPUT_DIR = "inputs"
OUTPUT_DIR = "outputs"
TEMP_DIR = "temp"
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "3"))  # Max concurrent video processing
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # Default Gemini API key from env

# Ensure directories
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Global Resources
# model and current_model_size are now managed by modules.workflow globally if desired, 
# or we can keep them here if we want to pass them in. 
# For true modularity, we should let workflow handle the model loading singleton, 
# BUT workflow currently has a lazy loader. 
# app.py's load_model_if_needed is now redundant if workflow handles it.
# However, to avoid breakage of current logic if workflow relies on us passing model...
# Checking workflow.py: get_whisper_model is internal there. It handles its own single instance.
# So we can remove model loading logic from here!

task_status = {}  # taskId -> {status, message, progress, duration, output_file}

# Worker pool for parallel video processing
video_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# Background Worker
def processing_worker(task_id, video_filename, output_filename, target_lang, model_size, translation_engine, ollama_model, 
                      dubbing, voice, audio_merge, manual_srt=None, manual_script=None, skip_transcription=False,
                      gemini_api_key=None, subtitle_color="yellow", subtitle_position="below", subtitle_bg_opacity="solid"):
    start_time = time.time()
    temp_srt_path = None
    try:
        # Resolve the requested input inside the managed input directory.
        safe_video_rel = normalize_relative_path(video_filename)
        
        task_status[task_id] = {
            "status": "processing", 
            "message": "Starting...", 
            "progress": 0, 
            "duration": "0s",
            "start_time": start_time 
        }
        
        def update_progress(pct, msg=None):
            if pct is not None:
                task_status[task_id]["progress"] = pct
            if msg is not None:
                task_status[task_id]["message"] = msg
        
        video_path = resolve_managed_path(INPUT_DIR, safe_video_rel)
        if not os.path.exists(video_path):
             raise FileNotFoundError(f"Video not found: {video_path}")
        
        # Determine subdirectory structure
        rel_dir = os.path.dirname(safe_video_rel)
        
        # Create output dirs relative to structure
        current_output_dir = os.path.join(OUTPUT_DIR, rel_dir)
        current_temp_dir = os.path.join(TEMP_DIR, rel_dir)
        
        os.makedirs(current_output_dir, exist_ok=True)
        os.makedirs(current_temp_dir, exist_ok=True)

        # Prepare manual inputs
        manual_script_list = None
        if manual_script:
            manual_script_list = [line.strip() for line in manual_script.split('\n') if line.strip()]
            
        if manual_srt:
            # Save manual SRT to temp specific location
            temp_srt_path = os.path.join(current_temp_dir, f"manual_{task_id}.srt")
            with open(temp_srt_path, "w", encoding="utf-8") as f:
                f.write(manual_srt)

        # Call Modular Pipeline
        # Note: We pass directories, not models. Workflow handles model loading.
        output_video_path = process_video_pipeline(
            video_path=video_path,
            output_dir=current_output_dir,
            temp_dir=current_temp_dir,
            target_lang=target_lang,
            translation_engine=translation_engine,
            ollama_model=ollama_model,
            gemini_api_key=gemini_api_key,
            dubbing=dubbing,
            voice=voice,
            audio_merge=audio_merge,
            model_size=model_size,
            progress_callback=update_progress,
            skip_transcription=skip_transcription,
            manual_srt_path=temp_srt_path,
            manual_script=manual_script_list,
            subtitle_color=subtitle_color,
            subtitle_position=subtitle_position,
            subtitle_bg_opacity=subtitle_bg_opacity
        )
        
        # Rename/Move Logic for custom Output Filename
        # The pipeline returns the path to the burned video (usually in /subtitled)
        default_output = output_video_path
        
        # Target output must remain inside OUTPUT_DIR.
        safe_output_rel = normalize_relative_path(output_filename)
        if os.path.dirname(safe_output_rel):
            target_rel = safe_output_rel
        else:
            target_rel = os.path.join(rel_dir, safe_output_rel) if rel_dir else safe_output_rel
        target_output = resolve_managed_path(OUTPUT_DIR, target_rel)

        if target_output:
            if not target_output.lower().endswith(".mp4"):
                target_output += ".mp4"
            
            # Ensure target dir exists
            os.makedirs(os.path.dirname(target_output), exist_ok=True)
                
            final_file_name = os.path.relpath(target_output, OUTPUT_DIR).replace("\\", "/")
                
            if os.path.exists(default_output) and default_output != target_output:
                if os.path.exists(target_output):
                    os.remove(target_output)
                os.rename(default_output, target_output)
            elif os.path.exists(default_output):
                 final_file_name = os.path.relpath(default_output, OUTPUT_DIR).replace("\\", "/")
        else:
            final_file_name = os.path.relpath(default_output, OUTPUT_DIR).replace("\\", "/")
        
        duration = round(time.time() - start_time, 2)
        duration_str = f"{duration}s"
        
        # Read SRT content for frontend convenience (optional)
        srt_content = ""
        try:
             # workflow uses temp_dir/basename_lang.srt
             base_name = os.path.splitext(os.path.basename(video_filename))[0]
             srt_path = os.path.join(current_temp_dir, f"{base_name}_{target_lang}.srt")
             if os.path.exists(srt_path):
                 with open(srt_path, "r", encoding="utf-8") as f:
                     srt_content = f.read()
        except:
             pass

        task_status[task_id].update({
            "status": "done",
            "message": "Completed",
            "progress": 100,
            "duration": duration_str,
            "output_file": final_file_name,
            "srt_content": srt_content
        })

    except Exception as e:
        print(f"Error processing video: {e}")
        import traceback
        traceback.print_exc()
        duration = round(time.time() - start_time, 2)
        task_status[task_id].update({
            "status": "error",
            "message": f"Error: {str(e)}",
            "progress": 0,
            "duration": f"{duration}s"
        })
    finally:
         if temp_srt_path and os.path.exists(temp_srt_path):
             try:
                os.remove(temp_srt_path)
             except:
                pass

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/documentation')
def documentation():
    return render_template('documentation.html')

@app.route('/support')
def support():
    return render_template('support.html')
    return render_template('index.html')

@app.route('/videos/input/<path:filename>')
def serve_input_video(filename):
    return send_from_directory(INPUT_DIR, filename)

@app.route('/videos/output/<path:filename>')
def serve_output_video(filename):
    # First try direct path
    if os.path.exists(os.path.join(OUTPUT_DIR, filename)):
        return send_from_directory(OUTPUT_DIR, filename)
    
    # Check in subdirectories (subtitled, dubbed)
    for subdir in ['subtitled', 'dubbed', 'audios']:
        subpath = os.path.join(OUTPUT_DIR, subdir, filename)
        if os.path.exists(subpath):
            return send_from_directory(os.path.join(OUTPUT_DIR, subdir), filename)
    
    # Not found
    return f"File not found: {filename}", 404

from modules.file_manager import VideoFileManager

# Initialize Manager
file_manager = VideoFileManager(INPUT_DIR, OUTPUT_DIR, TEMP_DIR)

@app.route('/api/upload', methods=['POST'])
def upload_video():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    
    file = request.files['file']
    result = file_manager.save_uploaded_video(file)
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/videos', methods=['GET'])
def list_videos():
    try:
        video_list = file_manager.list_videos()
        # Return full info now including has_srt, has_output, etc.
        # Frontend expects "name" for ID, but we can pass everything else too
        # Mapping for frontend compatibility: "name" -> "filename"
        frontend_list = []
        for v in video_list:
             v["name"] = v["filename"] # Alias for backward compat
             frontend_list.append(v)
             
        return jsonify(frontend_list)
    except Exception as e:
        print(f"Error listing videos: {e}")
        return jsonify([])



@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Delete cached SRT files for a video to force full re-processing"""
    data = request.json
    filename = data.get('filename')
    if not filename:
        return jsonify({"success": False, "message": "No filename provided"}), 400
    
    deleted = file_manager.delete_artifacts(filename)
    
    return jsonify({"success": deleted, "message": "Cache cleared" if deleted else "Failed to clear cache"})

@app.route('/api/ollama/models', methods=['GET'])
def get_ollama_models():
    """
    Fetch Ollama models and filter to show only TEXT-based models suitable for translation.
    Excludes: vision models (vl, vision), embedding models, code-only models.
    """
    # Patterns to EXCLUDE (not suitable for text translation)
    EXCLUDE_PATTERNS = [
        'vl',           # Vision-Language models (qwen-vl, llava, etc.)
        'vision',       # Vision models
        'embed',        # Embedding models
        'clip',         # CLIP models
        'nomic-embed',  # Embedding models
        'mxbai-embed',  # Embedding models
        'all-minilm',   # Embedding models
        'snowflake',    # Embedding models
        'coder',        # Code models (not for translation)
        'codellama',    # Code models
        'starcoder',    # Code models
        'deepseek-coder', # Code models
        'mixtral',      # Not optimized for Asian language translation
    ]
    
    # Patterns for RECOMMENDED models (good for Chinese-Vietnamese translation)
    RECOMMENDED_PATTERNS = ['qwen2', 'llama3', 'gemma2', 'phi3', 'yi']
    
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            all_models = data.get("models", [])
            
            # Filter out incompatible models
            filtered_models = []
            for model in all_models:
                name = model.get("name", "").lower()
                
                # Skip if matches any exclude pattern
                should_exclude = any(pattern in name for pattern in EXCLUDE_PATTERNS)
                if should_exclude:
                    continue
                
                # Mark as recommended if matches
                is_recommended = any(pattern in name for pattern in RECOMMENDED_PATTERNS)
                model["recommended"] = is_recommended
                filtered_models.append(model)
            
            # Sort: recommended first, then alphabetically
            filtered_models.sort(key=lambda m: (not m.get("recommended", False), m.get("name", "")))
            
            return jsonify({"models": filtered_models})
        return jsonify({"models": []}), 500
    except Exception as e:
        print(f"Ollama fetch error: {e}")
        return jsonify({"models": []}), 500

@app.route('/api/gemini/test', methods=['POST'])
def test_gemini():
    """Test if Gemini API key is valid"""
    data = request.json or {}
    api_key = data.get('api_key') or GEMINI_API_KEY
    
    if not api_key:
        return jsonify({"success": False, "error": "No API key provided"})
    
    result = test_gemini_connection(api_key)
    return jsonify(result)

@app.route('/api/gemini/status', methods=['GET'])
def gemini_status():
    """Get Gemini availability status"""
    return jsonify({
        "available": GEMINI_AVAILABLE,
        "has_default_key": bool(GEMINI_API_KEY)
    })

@app.route('/api/process', methods=['POST'])
def process():
    data = request.json
    filename = data.get('filename')
    new_name = data.get('rename_to') or filename
    
    # Dubbing specific
    dubbing_enabled = data.get('dubbing', False)
    manual_srt = data.get('manual_srt')
    manual_script = data.get('manual_script')
    skip_transcription = data.get('skip_transcription', False)  # Quick re-render mode
    
    settings = data.get('settings', {})
    target_lang = settings.get('targetLang', 'vi')
    model_size = settings.get('model', 'small')
    translation_engine = settings.get('translationEngine', 'google')
    ollama_model = settings.get('ollamaModel', 'qwen:7b')
    
    # Gemini settings - use provided key or fall back to env var
    gemini_api_key = settings.get('geminiApiKey') or GEMINI_API_KEY
    
    # Dubbing settings
    voice = settings.get('voice', 'vi-VN-HoaiMyNeural')
    audio_merge = settings.get('audioMerge', False) 
    
    # Subtitle styling
    subtitle_color = settings.get('subtitleColor', 'yellow')
    subtitle_position = settings.get('subtitlePosition', 'below')
    subtitle_bg_opacity = settings.get('subtitleBgOpacity', 'solid')  # 'solid' or 'transparent'
    
    task_id = str(uuid.uuid4())
    task_status[task_id] = {"status": "queued", "message": "Queued", "progress": 0, "duration": "..."}
    
    # Start thread (consider using video_executor for better pool management)
    thread = threading.Thread(target=processing_worker, args=(
        task_id, filename, new_name, target_lang, model_size, translation_engine, ollama_model, 
        dubbing_enabled, voice, audio_merge, manual_srt, manual_script, skip_transcription,
        gemini_api_key, subtitle_color, subtitle_position, subtitle_bg_opacity
    ))
    thread.start()
    
    return jsonify({"task_id": task_id})

@app.route('/api/status/<task_id>', methods=['GET'])
def get_status(task_id):
    return jsonify(task_status.get(task_id, {"status": "unknown"}))

@app.route('/api/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """Mark a task as cancelled (note: backend thread may still run, this just resets status)"""
    if task_id in task_status:
        task_status[task_id] = {"status": "cancelled", "message": "Cancelled by user", "progress": 0}
        return jsonify({"success": True, "message": "Task cancelled"})
    return jsonify({"success": False, "message": "Task not found"}), 404



if __name__ == '__main__':
    print("Server starting at http://localhost:5000")
    # IMPORTANT: debug=False to prevent auto-reload killing transcription tasks
    app.run(debug=False, port=5000, threaded=True)
