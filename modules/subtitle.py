from .utils import safe_print, format_timestamp
from .translation import BaseTranslator

class SubtitleService:
    @staticmethod
    def create_srt(segments, srt_path, translator: BaseTranslator = None, min_length=50, progress_callback=None):
        """
        Creates an SRT file from whisper segments.
        Transcribes -> (Optional) Translates -> Formatting -> Write File
        """
        total = len(segments)
        texts = [seg["text"].strip() for seg in segments]
        
        translated_texts = None
        if translator:
            safe_print(f"Translating {len(texts)} segments...")
            if progress_callback: progress_callback(5)
            translated_texts = translator.translate_batch(texts)
            if progress_callback: progress_callback(90)
        
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, start=1):
                start = format_timestamp(segment["start"])
                end = format_timestamp(segment["end"])
                
                text = translated_texts[i-1] if translated_texts else segment["text"].strip()
                
                # Masking / Padding logic
                if len(text) < min_length:
                    pad_total = min_length - len(text)
                    pad_left = pad_total // 2
                    pad_right = pad_total - pad_left
                    text = f"{'\u00A0' * pad_left}{text}{'\u00A0' * pad_right}"

                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        
        safe_print(f"Subtitle created: {srt_path}")
