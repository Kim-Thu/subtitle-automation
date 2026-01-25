import whisper
from .utils import safe_print

class TranscriptionService:
    def __init__(self, model_size="small"):
        self.model = whisper.load_model(model_size)
    
    def transcribe(self, video_path):
        safe_print(f"Transcribing {video_path}...")
        result = self.model.transcribe(video_path, verbose=False)
        return result
