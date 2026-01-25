import os
import re
import asyncio
import subprocess
import edge_tts
from .utils import safe_print

class DubbingService:
    @staticmethod
    async def _run_tts(text, voice, output_file, rate="+0%", pitch="+0Hz"):
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_file)

    @staticmethod
    def _parse_srt_time(ts_str):
        parts = ts_str.replace(',', '.').split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    @staticmethod
    def generate_dubbing(srt_path, output_audio_path, voice="vi-VN-HoaiMyNeural", dub_delay=0.0):
        """
        Generates Audio Track from SRT using EdgeTTS.
        """
        # Parse SRT
        blocks = []
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read().strip().split('\n\n')
            for b in content:
                lines = b.split('\n')
                if len(lines) >= 3:
                    ts = lines[1]
                    if '-->' in ts:
                        start = DubbingService._parse_srt_time(ts.split('-->')[0].strip())
                        end = DubbingService._parse_srt_time(ts.split('-->')[1].strip())
                        text = " ".join(lines[2:]).strip()
                        if text: blocks.append({"start": start, "end": end, "text": text})
        
        if not blocks: return False
        
        temp_files = []
        output_dir = os.path.dirname(output_audio_path)
        current_time = 0.0
        
        try:
            for i, block in enumerate(blocks):
                # Simple logic: speaker detection could be enhanced
                current_voice = voice 
                rate = "+0%"
                pitch = "+0Hz"
                
                # Check tags (Example logic simplified)
                text = block["text"]
                # ... (Tag parsing logic could be added here similar to original) ...

                start_time = block["start"] + dub_delay
                gap = start_time - current_time
                
                # Generate Silence
                if gap > 0.05:
                    sil_file = os.path.join(output_dir, f"sil_{i}.mp3")
                    subprocess.run([
                        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", 
                        "-t", str(gap), "-c:a", "libmp3lame", "-q:a", "9", sil_file
                    ], capture_output=True)
                    if os.path.exists(sil_file): temp_files.append(sil_file)
                
                # Generate TTS
                tts_file = os.path.join(output_dir, f"tts_{i}.mp3")
                asyncio.run(DubbingService._run_tts(text, current_voice, tts_file, rate, pitch))
                if os.path.exists(tts_file):
                    temp_files.append(tts_file)
                    current_time = block["end"] + dub_delay # Approximate end
            
            # Concat
            list_path = os.path.join(output_dir, "concat.txt")
            with open(list_path, "w", encoding='utf-8') as f:
                for tf in temp_files:
                    f.write(f"file '{os.path.abspath(tf).replace(os.sep, '/')}'\n")
            
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c:a", "libmp3lame", output_audio_path
            ], capture_output=True)
            
            # Cleanup
            if os.path.exists(list_path): os.remove(list_path)
            for tf in temp_files: 
                if os.path.exists(tf): os.remove(tf)
                
            return os.path.exists(output_audio_path)

        except Exception as e:
            safe_print(f"Dubbing Error: {e}")
            return False
