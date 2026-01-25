import os
import shutil
from werkzeug.utils import secure_filename
from .utils import safe_print

class VideoFileManager:
    """
    Handles file operations for video inputs following SOLID principles.
    Responsible for validating, sanitizing, and storing uploaded video files
    in a structured format.
    """
    
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    
    def __init__(self, base_input_dir: str, output_dir: str = None, temp_dir: str = None):
        self.base_input_dir = base_input_dir
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        
    def _allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def save_uploaded_video(self, file_storage) -> dict:
        """
        Process and save the uploaded file.
        
        Args:
            file_storage: Werkzeug FileStorage object.
            
        Returns:
            dict: Result containing success status, message, and file path.
        """
        if not file_storage or file_storage.filename == '':
            return {"success": False, "error": "No file selected"}
            
        if not self._allowed_file(file_storage.filename):
            return {"success": False, "error": f"File type not allowed. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"}
            
        try:
            # 1. Sanitize filename
            original_filename = secure_filename(file_storage.filename)
            video_name_stem = os.path.splitext(original_filename)[0]
            
            # 2. Create directory structure: inputs/{video_name}/
            # This ensures each video has its own sandboxed workspace
            target_dir = os.path.join(self.base_input_dir, video_name_stem)
            os.makedirs(target_dir, exist_ok=True)
            
            # 3. Define full save path
            save_path = os.path.join(target_dir, original_filename)
            
            # 4. Save file
            file_storage.save(save_path)
            safe_print(f"File uploaded successfully: {save_path}")
            
            return {
                "success": True, 
                "message": "File uploaded successfully",
                "path": save_path,
                "directory": target_dir
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_videos(self) -> list:
        """
        Scan input directory for videos, handling the nested structure.
        Returns list of video info objects, including processing status.
        """
        videos = []
        
        for root, dirs, files in os.walk(self.base_input_dir):
            for file in files:
                if self._allowed_file(file):
                    # Compute relative path for display/ID
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.base_input_dir)
                    rel_path_web = rel_path.replace("\\", "/")
                    
                    # Basic metadata
                    size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 2)
                    
                    # Check Artifacts
                    has_srt = False
                    has_output = False
                    output_file = None
                    srt_content = None

                    # Deduce temp/output paths
                    # Temp: temp/{subfolder}/{filename_no_ext}.srt
                    # We need to map relative structure to temp/output
                    
                    # Structure: inputs/Folder/Video.mp4 -> temp/Folder/Video.srt
                    rel_dir = os.path.dirname(rel_path)
                    base_name = os.path.splitext(file)[0]
                    
                    # Check SRT
                    if self.temp_dir:
                        target_temp = os.path.join(self.temp_dir, rel_dir)
                        if os.path.exists(target_temp):
                             # Find any SRT file that starts with the basename
                             # Prioritize: {basename}.srt, then {basename}_vi.srt, then any
                             candidates = []
                             for f in os.listdir(target_temp):
                                 if f.lower().endswith('.srt') and f.startswith(base_name):
                                     candidates.append(f)
                             
                             if candidates:
                                 # Logic: prefer shortest name (original srt) or specific one?
                                 # Usually we want the one used for generation. Let's pick the first one found or exact match
                                 chosen_srt = candidates[0]
                                 if f"{base_name}.srt" in candidates:
                                     chosen_srt = f"{base_name}.srt"
                                 elif f"{base_name}_vi.srt" in candidates:
                                     chosen_srt = f"{base_name}_vi.srt"
                                 
                                 srt_path = os.path.join(target_temp, chosen_srt)
                                 has_srt = True
                                 try:
                                     with open(srt_path, 'r', encoding='utf-8') as f:
                                         srt_content = f.read()
                                 except:
                                     pass
                                
                    # Check Output Video
                    # Output: outputs/{filename} (flattens usually?) or outputs/{rel_path}? 
                    # Let's assume standard behavior: outputs/{subtitled_name}
                    if self.output_dir:
                         # Preserve directory structure for output checking
                         # rel_path is "Folder/Video.mp4"
                         # output should be "Folder/Video_subtitled.mp4"
                         
                         potential_output_rel = os.path.join(rel_dir, f"{base_name}_subtitled.mp4")
                         output_full = os.path.join(self.output_dir, potential_output_rel)
                         
                         if os.path.exists(output_full):
                             has_output = True
                             output_file = potential_output_rel.replace("\\", "/")

                    videos.append({
                        "filename": rel_path_web,
                        "size": f"{size_mb} MB",
                        "full_path": full_path,
                        "has_srt": has_srt,
                        "srt_content": srt_content, # Send content to pre-fill manual script
                        "has_output": has_output,
                        "output_file": output_file
                    })
        return videos

    def delete_artifacts(self, filename: str) -> bool:
        """
        Delete collected artifacts (SRT, output video) for a given input filename.
        Reset to fresh state.
        """
        try:
            # Filename is relative path: Folder/Video.mp4
            if not self.temp_dir: return False
            
            rel_dir = os.path.dirname(filename)
            base_name = os.path.splitext(os.path.basename(filename))[0]
            
            # 1. Delete SRTs in temp
            target_temp_dir = os.path.join(self.temp_dir, rel_dir)
            if os.path.exists(target_temp_dir):
                for f in os.listdir(target_temp_dir):
                    if f.startswith(base_name) and f.endswith(('.srt', '.ass', '.txt')):
                        os.remove(os.path.join(target_temp_dir, f))
                        
            # 2. Delete Output Video
            # We guess the output name
            if self.output_dir:
                 potential_output = f"{base_name}_subtitled.mp4"
                 out_path = os.path.join(self.output_dir, potential_output)
                 if os.path.exists(out_path):
                     os.remove(out_path)
                     
            return True
        except Exception as e:
            safe_print(f"Error deleting artifacts: {e}")
            return False
