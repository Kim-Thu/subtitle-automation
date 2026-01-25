import os
import sys
import argparse
import warnings
import whisper
import concurrent.futures
import threading

# Import Core Modules
from modules.utils import safe_print, format_timestamp
from modules.translation import GeminiTranslatorWrapper, OllamaTranslator, GoogleTranslatorWrapper
from modules.subtitle import SubtitleService
from modules.dubbing import DubbingService
from modules.ffmpeg_utils import FFmpegUtils
from modules.transcription import TranscriptionService

# Import Legacy/Optional Modules (Keep as is strictly for now if they exist)
try:
    from modules.ocr.video_ocr import extract_hardsub, VideoOCR
    from modules.ocr.audio_sync import detect_voice_segments, sync_ocr_with_audio, AudioSync
    OCR_SYNC_AVAILABLE = True
except ImportError:
    OCR_SYNC_AVAILABLE = False
    extract_hardsub = None
    sync_ocr_with_audio = None

def process_single_video(video_path, output_dir, temp_dir, model, target_lang, 
                         rename_map=None, translation_engine="google", ollama_model="qwen:7b",
                         dubbing=False, voice="vi-VN-HoaiMyNeural", audio_merge=False, progress_callback=None,
                         manual_srt_path=None, manual_script=None, skip_transcription=False,
                         gemini_api_key=None, pipeline_mode="whisper",
                         subtitle_color="yellow", subtitle_position="below", subtitle_bg_opacity="solid"):
    """
    Process a single video: transcribe, translate, burn subtitles, optionally dub.
    Refactored to use modular architecture.
    """
    try:
        filename = os.path.basename(video_path)
        base_name = os.path.splitext(filename)[0]
        
        # Output handling
        output_name = f"{base_name}_subtitled.mp4"
        subtitled_dir = os.path.join(output_dir, "subtitled")
        os.makedirs(subtitled_dir, exist_ok=True)
        burned_video_path = os.path.join(subtitled_dir, output_name)
        
        if progress_callback: progress_callback(5, "Starting...")
        safe_print(f"[{base_name}] Starting processing...")

        srt_target_path = os.path.join(temp_dir, f"{base_name}_{target_lang}.srt")

        # 1. SRT Generation Strategy
        segments = []
        
        # Strategy A: Manual SRT
        if manual_srt_path and os.path.exists(manual_srt_path):
            if progress_callback: progress_callback(10, "Using Manual SRT...")
            import shutil
            shutil.copy(manual_srt_path, srt_target_path)
            # Proceed to burning
            
        # Strategy B: Existing SRT (Skip Transcribe)
        elif skip_transcription and os.path.exists(srt_target_path):
            if progress_callback: progress_callback(30, "Using existing SRT...")
            safe_print(f"[{base_name}] Skipping transcription, using existing SRT...")
            # Proceed to burning
            
        # Strategy C: OCR Pipeline (Legacy Support)
        elif pipeline_mode == "ocr_sync" and OCR_SYNC_AVAILABLE:
             if progress_callback: progress_callback(10, "Extracting Hardsub (OCR)...")
             safe_print(f"[{base_name}] Using OCR + Voice Sync pipeline...")
             ocr_segments = extract_hardsub(video_path)
             if not ocr_segments:
                 safe_print(f"[{base_name}] OCR failed, fallback to Whisper")
                 pipeline_mode = "whisper"
             else:
                 # Logic OCR cũ khá phức tạp, để đảm bảo tính toàn vẹn, 
                 # nếu user chọn OCR mode, ta fallback về cách gọi cũ hoặc implement lại sau.
                 # Hiện tại code này chưa cover hết logic OCR cũ phức tạp (sync audio).
                 # Tạm thời để Whisper fallback để tránh crash.
                 safe_print(f"[{base_name}] OCR Refactor in progress -> Fallback to Whisper for stability")
                 pipeline_mode = "whisper"
        
        # Strategy D: Whisper (Default)
        if pipeline_mode == "whisper" and not (manual_srt_path and os.path.exists(manual_srt_path)) and not (skip_transcription and os.path.exists(srt_target_path)):
             if progress_callback: progress_callback(10, "Transcribing...")
             
             # Use injected model or load new
             result = model.transcribe(video_path, verbose=False)
             detected_lang = result.get("language", "unknown")
             safe_print(f"[{base_name}] Detected language: {detected_lang}")
             segments = result["segments"]
             
             # Setup Translator
             translator = None
             if manual_script:
                 # Script mapping logic
                 if progress_callback: progress_callback(30, "Mapping Manual Script...")
                 for i, seg in enumerate(segments):
                     if i < len(manual_script): seg["text"] = manual_script[i]
             else:
                 # Translation
                 if progress_callback: progress_callback(30, f"Translating ({translation_engine})...")
                 if translation_engine == "gemini":
                     translator = GeminiTranslatorWrapper(api_key=gemini_api_key, target_lang=target_lang)
                 elif translation_engine == "ollama":
                     translator = OllamaTranslator(model=ollama_model, target_lang=target_lang)
                 else:
                     translator = GoogleTranslatorWrapper(target_lang=target_lang)
            
             # Create SRT
             SubtitleService.create_srt(segments, srt_target_path, translator=translator, progress_callback=progress_callback)

        # 2. Burn Subtitles
        if os.path.exists(srt_target_path):
            if progress_callback: progress_callback(60, "Burning Subtitles...")
            FFmpegUtils.burn_subtitles(video_path, srt_target_path, burned_video_path, 
                                       subtitle_color=subtitle_color, subtitle_position=subtitle_position,
                                       subtitle_bg_opacity=subtitle_bg_opacity)
        else:
            safe_print(f"[{base_name}] Critical: SRT file not found {srt_target_path}")
            return

        # 3. Dubbing
        if dubbing:
            if progress_callback: progress_callback(70, f"Generating Dubbing ({voice})...")
            audios_dir = os.path.join(output_dir, "audios")
            os.makedirs(audios_dir, exist_ok=True)
            dub_audio_path = os.path.join(audios_dir, f"{base_name}_dub.mp3")
            
            success = DubbingService.generate_dubbing(srt_target_path, dub_audio_path, voice=voice)
            
            if success:
                dubbed_dir = os.path.join(output_dir, "dubbed")
                os.makedirs(dubbed_dir, exist_ok=True)
                dubbed_video_path = os.path.join(dubbed_dir, f"{base_name}_dubbed.mp4")
                
                if progress_callback: progress_callback(85, "Mixing Audio...")
                FFmpegUtils.mix_audio(burned_video_path, dub_audio_path, dubbed_video_path)
                safe_print(f"[{base_name}] Dubbing Complete: {dubbed_video_path}")
            else:
                safe_print(f"[{base_name}] Dubbing generation failed.")

        if progress_callback: progress_callback(100, "Finished!")
        safe_print(f"[{base_name}] Finished! Subtitled: {burned_video_path}")

    except Exception as e:
        safe_print(f"[{base_name}] ERROR: {e}")
        if progress_callback: progress_callback(0, f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default="inputs")
    parser.add_argument("--output_dir", default="outputs")
    parser.add_argument("--temp_dir", default="temp")
    parser.add_argument("--model", default="small")
    parser.add_argument("--target_lang", default="vi")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    
    if os.path.isfile(args.input_dir):
        files = [args.input_dir]
    else:
        files = [os.path.join(args.input_dir, f) for f in os.listdir(args.input_dir) if f.endswith(".mp4")]
    
    model = whisper.load_model(args.model)
    
    for f in files:
        process_single_video(f, args.output_dir, args.temp_dir, model, args.target_lang)

if __name__ == "__main__":
    main()
