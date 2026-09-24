import os
import sys
import re
import ffmpeg
from .utils import safe_print

class FFmpegUtils:
    @staticmethod
    def burn_subtitles(video_path, srt_path, output_path, subtitle_color="yellow", subtitle_position="below", subtitle_bg_opacity="solid"):
        """
        Burn subtitles into video with customizable styling.
        """
        safe_print(f"Burning subtitles into video (color={subtitle_color}, position={subtitle_position}, bg={subtitle_bg_opacity})...")
        
        # Color mapping (FFmpeg uses AABBGGRR format)
        color_map = {
            "white": "&H00FFFFFF",
            "yellow": "&H0000FFFF",    # Yellow (AABBGGRR: 00 00 FF FF)
            "green": "&H0000FF00",
            "cyan": "&H00FFFF00",
            "red": "&H000000FF",
            "orange": "&H0000A5FF",
        }
        
        # Convert hex color to FFmpeg format if provided
        if subtitle_color.startswith("#"):
            # #RRGGBB -> &H00BBGGRR
            hex_color = subtitle_color[1:]
            if len(hex_color) == 6:
                r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
                primary_color = f"&H00{b}{g}{r}"
            else:
                primary_color = "&H0000FFFF"
        else:
            primary_color = color_map.get(subtitle_color.lower(), "&H0000FFFF")  # Default yellow
        
        # Position: below = higher MarginV to avoid hardsub, normal = standard
        margin_v = 50 if subtitle_position == "below" else 20
        
        # Create a clean version of SRT without [Speaker:Tag] for visual display
        clean_srt_path = srt_path.replace(".srt", "_clean.srt")
        try:
            with open(srt_path, "r", encoding="utf-8") as f_in:
                lines = f_in.readlines()
                clean_lines = []
                for line in lines:
                    l = line.strip()
                    # If it's not a sequence number and not a timestamp line
                    if not re.match(r'^\d+$', l) and '-->' not in l:
                        # Remove [Speaker:...] tags
                        l = re.sub(r'\[Speaker:[^\]]+\]', '', l)
                        # Aggressively strip whitespace (including non-breaking spaces)
                        l = l.strip()
                    
                    # Keep the original line ending if it's the number or timestamp
                    # or the stripped version if it's text
                    if re.match(r'^\d+$', line.strip()) or '-->' in line:
                        clean_lines.append(line.strip())
                    else:
                        clean_lines.append(l)
                
                with open(clean_srt_path, "w", encoding="utf-8") as f_out:
                    f_out.write("\n".join(clean_lines))
        except Exception as e:
            safe_print(f"Error cleaning SRT: {e}")
            clean_srt_path = srt_path # Fallback to original if cleaning fails
        
        # Escape path for FFmpeg
        # On Windows, path must be escaped carefully for filter_complex
        srt_path_escaped = clean_srt_path.replace("\\", "/").replace(":", "\\:")
        
        # Background opacity: solid = fully opaque (FF), transparent = 50% (80)
        # FFmpeg AABBGGRR format: AA = alpha (FF = opaque, 80 = semi-transparent, 00 = fully transparent)
        bg_color = "&HFF000000" if subtitle_bg_opacity == "solid" else "&H80000000"
        border_style = 3 if subtitle_bg_opacity == "solid" else 4  # 3 = Opaque box, 4 = Shadow+outline
        
        # FFmpeg style configuration
        style = (
            f"Fontname=Arial,"
            f"FontSize=26,"
            f"PrimaryColour={primary_color},"      # Custom text color
            f"OutlineColour=&H00000000,"            # Black outline
            f"BackColour={bg_color},"              # Background (solid or transparent)
            f"BorderStyle={border_style},"          # 3 = Opaque box, 4 = Shadow+outline
            f"Outline=2,"                            # Outline thickness
            f"Shadow=1,"                             # Slight shadow
            f"MarginV={margin_v},"                   # Position above hardsub
            f"Alignment=2"                           # Bottom Center
        )
        
        try:
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(
                stream, 
                output_path, 
                vf=f"subtitles='{srt_path_escaped}':force_style='{style}'",
                acodec='copy',
                vcodec='libx264',
                preset='fast'
            )
            ffmpeg.run(stream, overwrite_output=True, quiet=True) # Quiet to reduce log noise
            safe_print(f"Done! Output saved to: {output_path}")
            
        except ffmpeg.Error as e:
            safe_print("FFmpeg Error:", file=sys.stderr)
            # safe_print(e.stderr.decode() if e.stderr else str(e))
            raise e 
        finally:
            # Cleanup clean SRT
            if os.path.exists(clean_srt_path) and clean_srt_path != srt_path:
                try:
                    os.remove(clean_srt_path)
                except:
                    pass

    @staticmethod
    def replace_audio(video_path, dub_audio_path, output_path):
        """
        Replaces the video's audio track with the generated dub track.
        """
        try:
            input_video = ffmpeg.input(video_path)
            input_dub = ffmpeg.input(dub_audio_path)

            stream = ffmpeg.output(
                input_video.video,
                input_dub.audio,
                output_path,
                vcodec='copy',
                acodec='aac',
                shortest=None
            )
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            return True
        except ffmpeg.Error as e:
            safe_print(f"Audio replacement error: {e}")
            return False

    @staticmethod
    def mix_audio(video_path, dub_audio_path, output_path, original_volume=0.02):
        """
        Mixes dub audio with original video audio (ducking original heavily).
        """
        try:
            # Input 0: Video
            input_video = ffmpeg.input(video_path)
            # Input 1: Dub Audio
            input_dub = ffmpeg.input(dub_audio_path)
            
            # Setup Audio Mix:
            original_audio = input_video.audio.filter('volume', original_volume)  # Nearly mute original
            dub_audio = input_dub.filter('volume', 2.0)  # Boost dub audio
            
            # Use 'first' duration to match video length
            mixed_audio = ffmpeg.filter([original_audio, dub_audio], 'amix', inputs=2, duration='first')
            
            stream = ffmpeg.output(
                input_video.video,
                mixed_audio,
                output_path,
                vcodec='copy',
                acodec='aac',
                strict='experimental'
            )
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            return True
        except ffmpeg.Error as e:
            safe_print(f"Mixing Error: {e}")
            return False
