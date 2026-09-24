import json
import os
import shutil
import subprocess
from werkzeug.utils import secure_filename
from .utils import safe_print, normalize_relative_path, resolve_managed_path

class VideoFileManager:
    """
    Handles file operations for video inputs following SOLID principles.
    Responsible for validating, sanitizing, and storing uploaded video files
    in a structured format.
    """
    
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    SUPPORTED_VIDEO_CODECS = {'h264', 'hevc', 'mpeg4', 'vp8', 'vp9', 'av1'}

    def __init__(self, base_input_dir: str, output_dir: str = None, temp_dir: str = None,
                 max_upload_bytes: int = None, ffprobe_path: str = None):
        self.base_input_dir = base_input_dir
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.max_upload_bytes = max_upload_bytes
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe")
        
    def _allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS


    def validate_media(self, file_path: str) -> dict:
        """Validate file size and probe media content before expensive processing."""
        if not os.path.isfile(file_path):
            return {"success": False, "error": "Video file does not exist"}

        if self.max_upload_bytes is not None:
            file_size = os.path.getsize(file_path)
            if file_size > self.max_upload_bytes:
                limit_mb = round(self.max_upload_bytes / (1024 * 1024))
                return {
                    "success": False,
                    "error": f"Video exceeds the configured {limit_mb} MB size limit"
                }

        if not self.ffprobe_path:
            return {
                "success": False,
                "error": "FFprobe is required to validate uploaded media but was not found"
            }

        try:
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=format_name,duration:stream=index,codec_type,codec_name",
                    "-of", "json",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"success": False, "error": f"Unable to inspect media: {exc}"}

        if result.returncode != 0:
            detail = (result.stderr or "").strip()
            return {
                "success": False,
                "error": "Invalid or corrupt media file" + (f": {detail}" if detail else "")
            }

        try:
            metadata = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return {"success": False, "error": "FFprobe returned invalid media metadata"}

        video_streams = [
            stream for stream in metadata.get("streams", [])
            if stream.get("codec_type") == "video"
        ]
        if not video_streams:
            return {"success": False, "error": "Uploaded media does not contain a video stream"}

        codec = (video_streams[0].get("codec_name") or "").lower()
        if codec not in self.SUPPORTED_VIDEO_CODECS:
            supported = ", ".join(sorted(self.SUPPORTED_VIDEO_CODECS))
            return {
                "success": False,
                "error": f"Unsupported video codec '{codec or 'unknown'}'. Supported codecs: {supported}"
            }

        format_name = metadata.get("format", {}).get("format_name", "")
        duration_raw = metadata.get("format", {}).get("duration")
        try:
            duration = float(duration_raw) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration = None

        return {
            "success": True,
            "codec": codec,
            "format": format_name,
            "duration": duration,
        }

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
            
            # 4. Save file, then validate actual media content with FFprobe.
            file_storage.save(save_path)

            validation = self.validate_media(save_path)
            if not validation["success"]:
                if os.path.exists(save_path):
                    os.remove(save_path)
                if os.path.isdir(target_dir) and not os.listdir(target_dir):
                    os.rmdir(target_dir)
                return validation

            safe_print(f"File uploaded successfully: {save_path}")
            
            return {
                "success": True, 
                "message": "File uploaded successfully",
                "path": save_path,
                "directory": target_dir,
                "media": {
                    "codec": validation.get("codec"),
                    "format": validation.get("format"),
                    "duration": validation.get("duration"),
                }
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
                                
                    # Check generated output using the same nested structure as the pipeline:
                    # outputs/<rel_dir>/subtitled/<name>_subtitled.mp4
                    # outputs/<rel_dir>/dubbed/<name>_dubbed.mp4
                    if self.output_dir:
                         dubbed_rel = os.path.join(rel_dir, "dubbed", f"{base_name}_dubbed.mp4")
                         subtitled_rel = os.path.join(rel_dir, "subtitled", f"{base_name}_subtitled.mp4")

                         # Prefer dubbed output when both artifacts exist.
                         for candidate_rel in (dubbed_rel, subtitled_rel):
                             candidate_full = os.path.join(self.output_dir, candidate_rel)
                             if os.path.exists(candidate_full):
                                 has_output = True
                                 output_file = candidate_rel.replace("\\", "/")
                                 break

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

            safe_filename = normalize_relative_path(filename)
            # Validate the referenced input location as well, even if the file no longer exists.
            resolve_managed_path(self.base_input_dir, safe_filename)

            rel_dir = os.path.dirname(safe_filename)
            base_name = os.path.splitext(os.path.basename(safe_filename))[0]
            
            # 1. Delete SRTs in temp
            target_temp_dir = resolve_managed_path(self.temp_dir, rel_dir or base_name)
            if not rel_dir:
                target_temp_dir = os.path.abspath(self.temp_dir)
            if os.path.exists(target_temp_dir):
                for f in os.listdir(target_temp_dir):
                    if f.startswith(base_name) and f.endswith(('.srt', '.ass', '.txt')):
                        os.remove(os.path.join(target_temp_dir, f))
                        
            # 2. Delete generated output artifacts using the pipeline's nested layout.
            if self.output_dir:
                 artifact_paths = [
                     resolve_managed_path(self.output_dir, os.path.join(rel_dir, "subtitled", f"{base_name}_subtitled.mp4")),
                     resolve_managed_path(self.output_dir, os.path.join(rel_dir, "dubbed", f"{base_name}_dubbed.mp4")),
                     resolve_managed_path(self.output_dir, os.path.join(rel_dir, "audios", f"{base_name}_dub.mp3")),
                 ]
                 for artifact_path in artifact_paths:
                     if os.path.exists(artifact_path):
                         os.remove(artifact_path)
                     
            return True
        except Exception as e:
            safe_print(f"Error deleting artifacts: {e}")
            return False
