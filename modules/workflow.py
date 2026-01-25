import os
from .utils import safe_print
from .transcription import TranscriptionService
from .translation import GeminiTranslatorWrapper, GoogleTranslatorWrapper, OllamaTranslator
from .subtitle import SubtitleService
from .ffmpeg_utils import FFmpegUtils
from .dubbing import DubbingService

# Global model cache to avoid reloading per request if using threads
_whisper_model = None

def get_whisper_model(size="small"):
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = TranscriptionService(size)
    return _whisper_model

def process_video_pipeline(video_path, output_dir, temp_dir, target_lang="vi", 
                           translation_engine="google", gemini_api_key=None,
                           dubbing=False, voice="vi-VN-HoaiMyNeural",
                           model_size="small", progress_callback=None,
                           skip_transcription=False, manual_srt_path=None, manual_script=None,
                           ollama_model=None, audio_merge=False,
                           subtitle_color="yellow", subtitle_position="below", subtitle_bg_opacity="solid"):
    
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    safe_print(f"[{base_name}] Starting Pipeline...")
    if progress_callback: progress_callback(5, "Initializing...")

    # Ensure dirs
    subtitled_dir = os.path.join(output_dir, "subtitled")
    os.makedirs(subtitled_dir, exist_ok=True)
    
    srt_target_path = os.path.join(temp_dir, f"{base_name}_{target_lang}.srt")
    
    # 1. Transcribe
    segments = None
    if manual_srt_path and os.path.exists(manual_srt_path):
        safe_print(f"[{base_name}] Using Manual SRT")
        import shutil
        shutil.copy(manual_srt_path, srt_target_path)
    elif skip_transcription and os.path.exists(srt_target_path):
        safe_print(f"[{base_name}] Using Existing SRT")
    else:
        if progress_callback: progress_callback(10, "Transcribing...")
        # Load model lazy
        transcriber = get_whisper_model(model_size)
        result = transcriber.transcribe(video_path)
        segments = result["segments"]
        
        if manual_script:
            # Script mapping logic
            if progress_callback: progress_callback(30, "Mapping Manual Script...")
            # Override segment text with manual script lines
            for i, seg in enumerate(segments):
                if i < len(manual_script): seg["text"] = manual_script[i]
            
            # If using script, we might still want to translate if target != script language
            # But typically manual script implies it's the target content.
            # Assuming if manual_script is passed, we skip translation or translate normally?
            # Original auto_subtitle logic: "Mapping Manual Script..." then immediately "Translating" logic ran if not skipped.
            # However, usually manual script IS the prepared subtitle text.
            # Let's check original logic: It replaced text, then potentially translated if engine was active.
            # We will follow suit: Replace text, then proceed to translation block logic.
        
        # 2. Translate
        if not manual_script or (manual_script and translation_engine != "none"):
            if progress_callback: progress_callback(30, f"Translating ({translation_engine})...")
            translator = None
            if translation_engine == "gemini":
                translator = GeminiTranslatorWrapper(api_key=gemini_api_key, target_lang=target_lang)
            elif translation_engine == "ollama":
                translator = OllamaTranslator(model=ollama_model, target_lang=target_lang)
            else:
                translator = GoogleTranslatorWrapper(target_lang=target_lang)
                
            SubtitleService.create_srt(segments, srt_target_path, translator=translator, progress_callback=progress_callback)
        else:
            SubtitleService.create_srt(segments, srt_target_path, translator=None, progress_callback=progress_callback)

    # 3. Burn Subtitles
    if progress_callback: progress_callback(60, "Burning Subtitles...")
    output_video = os.path.join(subtitled_dir, f"{base_name}_subtitled.mp4")
    FFmpegUtils.burn_subtitles(video_path, srt_target_path, output_video, 
                               subtitle_color=subtitle_color, subtitle_position=subtitle_position, 
                               subtitle_bg_opacity=subtitle_bg_opacity)
    
    # 4. Dubbing
    if dubbing:
        if progress_callback: progress_callback(80, "Dubbing...")
        dub_dir = os.path.join(output_dir, "dubbed")
        os.makedirs(dub_dir, exist_ok=True)
        audio_path = os.path.join(output_dir, "audios", f"{base_name}_dub.mp3")
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        success = DubbingService.generate_dubbing(srt_target_path, audio_path, voice=voice)
        if success:
            dubbed_video = os.path.join(dub_dir, f"{base_name}_dubbed.mp4")
            FFmpegUtils.mix_audio(output_video, audio_path, dubbed_video)
            safe_print(f"Dubbed Video: {dubbed_video}")
            
    safe_print(f"[{base_name}] Pipeline Finished.")
    if progress_callback: progress_callback(100, "Done")
    return output_video
