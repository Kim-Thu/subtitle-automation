"""
HYBRID SUBTITLE EXTRACTION V1
- OCR: Detect timing (when subtitle appears/disappears)
- Whisper: Recognize accurate text from audio

Flow:
1. OCR scan video -> Get time ranges where subtitle exists
2. For each time range, extract audio segment
3. Whisper transcribe that audio segment -> Accurate text
4. Combine timing + text -> SRT output
"""

import cv2
import os
import sys
import numpy as np
import whisper
import subprocess
import tempfile

# === CẤU HÌNH ===
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"

# Vùng crop subtitle (bottom 15%)
CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.12
CROP_X_END = 0.88

# Ngưỡng detect có chữ hay không (dựa trên độ sáng vùng crop)
BRIGHTNESS_THRESHOLD = 30  # Nếu mean brightness > này thì có thể có text
VISUAL_DIFF_THRESHOLD = 0.95
MIN_SEGMENT_DURATION = 0.3  # Tối thiểu 0.3s mới tính là 1 segment

def format_srt_time(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    secs = int(seconds)
    mins = (secs % 3600) // 60
    hrs = secs // 3600
    secs = secs % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

import re
def clean_whisper_text(text):
    """Remove Whisper hallucination artifacts"""
    # Remove trailing numbers/symbols like "8 「", "0 ~(", "80 巨"
    text = re.sub(r'[\d]+\s*[「」『』【】\[\]~～()（）巨]+\s*$', '', text)
    text = re.sub(r'\s*[\d]+\s*$', '', text)  # Trailing numbers
    # Remove repeated punctuation
    text = re.sub(r'[。！？,.!?]{2,}', '。', text)
    # Remove music notes and symbols
    text = re.sub(r'[♪♫♬♩🎵🎶]+', '', text)
    # Remove "字幕by" watermarks (various formats)
    text = re.sub(r'字幕\s*[bB][yY]\s*[\w\u4e00-\u9fff]+', '', text)
    text = re.sub(r'字幕\s*[:：]?\s*[\w\u4e00-\u9fff]+', '', text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_watermark(text):
    """Check if text is just a watermark/credit"""
    watermarks = ['字幕', '翻译', '校对', '制作', 'by', 'BY']
    clean = text.strip()
    if len(clean) < 3:
        return True
    for w in watermarks:
        if clean.startswith(w) or clean.endswith(w):
            return True
    return False

def deduplicate_results(results, time_threshold=0.5, text_similarity=0.8):
    """Remove duplicate/overlapping subtitles"""
    from difflib import SequenceMatcher
    
    if not results:
        return results
    
    deduped = [results[0]]
    for start, end, text in results[1:]:
        prev_start, prev_end, prev_text = deduped[-1]
        
        # Check if times overlap or are very close
        time_gap = start - prev_end
        
        # Check text similarity
        ratio = SequenceMatcher(None, prev_text, text).ratio()
        
        if time_gap < time_threshold and ratio > text_similarity:
            # Similar content, extend previous subtitle
            if end > prev_end:
                deduped[-1] = (prev_start, end, prev_text if len(prev_text) >= len(text) else text)
        else:
            deduped.append((start, end, text))
    
    return deduped

def split_long_segments(results, max_chars=30):
    """Split long segments by punctuation and estimate timing"""
    split_results = []
    
    for start, end, text in results:
        # Split by Chinese punctuation
        sentences = re.split(r'([。！？,，])', text)
        
        # Recombine: "A" + "。" + "B" -> ["A。", "B"]
        combined = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                combined.append(sentences[i] + sentences[i+1])
            else:
                combined.append(sentences[i])
        # Add last part if odd
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            combined.append(sentences[-1])
        
        # Filter empty
        combined = [s.strip() for s in combined if s.strip() and len(s.strip()) >= 2]
        
        if len(combined) <= 1:
            # No split needed
            split_results.append((start, end, text))
        else:
            # Split timing proportionally by text length
            total_len = sum(len(s) for s in combined)
            duration = end - start
            
            current_time = start
            for sentence in combined:
                ratio = len(sentence) / total_len
                seg_duration = duration * ratio
                seg_end = min(current_time + seg_duration, end)
                
                split_results.append((current_time, seg_end, sentence))
                current_time = seg_end
    
    return split_results

def detect_subtitle_timings(video_path):
    """
    Phase 1: OCR-less visual detection
    Chỉ detect khi nào có chữ xuất hiện (không cần đọc nội dung)
    Returns: List of (start_time, end_time) tuples
    """
    print("[Phase 1] Detecting subtitle timings from video...")
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    segments = []
    current_segment = None
    prev_crop_gray = None
    frame_idx = 0
    
    # Sample every 3 frames for speed
    SAMPLE_RATE = 3
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % SAMPLE_RATE != 0:
            frame_idx += 1
            continue
            
        curr_time = frame_idx / fps
        h, w = frame.shape[:2]
        
        # Crop subtitle region
        crop = frame[int(h*CROP_Y_START):int(h*CROP_Y_END), 
                     int(w*CROP_X_START):int(w*CROP_X_END)]
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # Binary threshold to isolate white text
        _, binary = cv2.threshold(crop_gray, 200, 255, cv2.THRESH_BINARY)
        white_ratio = np.mean(binary) / 255.0  # 0-1, higher = more white pixels
        
        # Detect if there's text (white pixels > threshold)
        has_text = white_ratio > 0.01  # At least 1% white pixels
        
        # Visual diff to detect change
        is_same = False
        if prev_crop_gray is not None and crop_gray.shape == prev_crop_gray.shape:
            diff_ratio = np.mean(crop_gray == prev_crop_gray)
            is_same = diff_ratio > VISUAL_DIFF_THRESHOLD
        prev_crop_gray = crop_gray.copy()
        
        if has_text:
            if current_segment is None:
                # Start new segment
                current_segment = {"start": curr_time, "end": curr_time}
            else:
                # Extend current segment
                current_segment["end"] = curr_time
        else:
            if current_segment is not None:
                # End current segment
                duration = current_segment["end"] - current_segment["start"]
                if duration >= MIN_SEGMENT_DURATION:
                    segments.append((current_segment["start"], current_segment["end"]))
                current_segment = None
        
        if frame_idx % 90 == 0:
            pct = int(frame_idx / total_frames * 100)
            sys.stdout.write(f"\r  Scanning: {pct}% | Segments: {len(segments)}")
            sys.stdout.flush()
        
        frame_idx += 1
    
    # Don't forget last segment
    if current_segment is not None:
        duration = current_segment["end"] - current_segment["start"]
        if duration >= MIN_SEGMENT_DURATION:
            segments.append((current_segment["start"], current_segment["end"]))
    
    cap.release()
    print(f"\n  Found {len(segments)} subtitle segments")
    return segments

def extract_audio_segment(video_path, start_time, end_time, output_path):
    """Extract audio from video for a specific time range"""
    duration = end_time - start_time
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-ss", str(start_time), "-t", str(duration),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    return os.path.exists(output_path)

def transcribe_segments(video_path, segments, model_size="small"):
    """
    Phase 2: Whisper transcription for each segment
    Uses segment-level output from Whisper for individual sentence timing
    Returns: List of (start, end, text) tuples
    """
    print(f"\n[Phase 2] Transcribing {len(segments)} segments with Whisper ({model_size})...")
    
    # Load Whisper model
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = whisper.load_model(model_size)
    
    results = []
    temp_dir = tempfile.mkdtemp()
    
    for i, (seg_start, seg_end) in enumerate(segments):
        # Extract audio segment
        temp_audio = os.path.join(temp_dir, f"seg_{i}.wav")
        
        if not extract_audio_segment(video_path, seg_start, seg_end, temp_audio):
            continue
        
        # Transcribe với segment output
        try:
            result = model.transcribe(
                temp_audio,
                language="zh",
                task="transcribe",
                verbose=False,
                word_timestamps=False  # Segment level is enough
            )
            
            # Dùng từng segment của Whisper (mỗi câu riêng biệt)
            for seg in result.get("segments", []):
                # Adjust timing relative to video (add segment start offset)
                start = seg_start + seg["start"]
                end = seg_start + seg["end"]
                text = clean_whisper_text(seg["text"].strip())
                
                if text and len(text) >= 2:
                    results.append((start, end, text))
                    
            print(f"  [{i+1}/{len(segments)}] {len(result.get('segments', []))} sentences detected")
            
        except Exception as e:
            print(f"  [{i+1}] Error: {e}")
        finally:
            if os.path.exists(temp_audio):
                os.remove(temp_audio)
    
    # Cleanup
    try:
        os.rmdir(temp_dir)
    except:
        pass
    
    # Sort by start time
    results.sort(key=lambda x: x[0])
    return results

def save_srt(results, output_path):
    """Save results to SRT file"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(results, 1):
            f.write(f"{i}\n")
            f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
            f.write(f"{text}\n\n")
    print(f"\nSaved: {output_path}")

def process_hybrid(video_path, model_size="small"):
    """
    Main hybrid processing pipeline
    Strategy: Whisper for accurate timing + OCR visual windows for filtering
    """
    print("=" * 60)
    print("HYBRID SUBTITLE EXTRACTION V2")
    print("  Whisper → Timing + Text | OCR → Filter")
    print("=" * 60)
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_srt = f"{video_name}_hybrid.srt"
    
    # Phase 1: Get visual windows (when subtitle is visible)
    visual_segments = detect_subtitle_timings(video_path)
    
    if not visual_segments:
        print("No subtitle segments detected!")
        return
    
    # Phase 2: Run Whisper on FULL audio for precise timing
    print(f"\n[Phase 2] Running Whisper on full audio ({model_size})...")
    
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = whisper.load_model(model_size)
    
    # Extract full audio
    temp_audio = f"{video_name}_temp.wav"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        temp_audio
    ]
    subprocess.run(cmd, capture_output=True)
    
    result = model.transcribe(
        temp_audio,
        language="zh",
        task="transcribe",
        verbose=False
    )
    
    # Cleanup temp audio
    if os.path.exists(temp_audio):
        os.remove(temp_audio)
    
    whisper_segments = result.get("segments", [])
    print(f"  Whisper found {len(whisper_segments)} segments")
    
    # Phase 3: Filter - keep only Whisper segments that overlap with visual windows
    print("\n[Phase 3] Filtering by visual presence...")
    
    def overlaps_visual(seg_start, seg_end):
        """Check if whisper segment overlaps any visual window"""
        for vis_start, vis_end in visual_segments:
            # Allow some tolerance (0.3s)
            if seg_start < vis_end + 0.3 and seg_end > vis_start - 0.3:
                return True
        return False
    
    results = []
    for seg in whisper_segments:
        start = seg["start"]
        end = seg["end"]
        text = clean_whisper_text(seg["text"].strip())
        
        if text and len(text) >= 2 and not is_watermark(text):
            if overlaps_visual(start, end):
                results.append((start, end, text))
    
    print(f"  After visual filter: {len(results)} subtitles")
    
    # Phase 4: Deduplicate
    results = deduplicate_results(results)
    print(f"  After deduplication: {len(results)} subtitles")
    
    # Phase 5: Save SRT
    if results:
        save_srt(results, output_srt)
        print(f"\n✓ Done! Total: {len(results)} subtitles")
    else:
        print("\nNo transcription results")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        video_input = VIDEO_PATH
    
    model = "small"  # Use 'medium' for better accuracy
    if len(sys.argv) > 2:
        model = sys.argv[2]
    
    if os.path.exists(video_input):
        process_hybrid(video_input, model)
    else:
        print(f"Error: File not found - {video_input}")
