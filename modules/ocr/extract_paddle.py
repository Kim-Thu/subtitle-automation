"""
PADDLEOCR SUBTITLE EXTRACTION
- PaddleOCR: More accurate Chinese text recognition
- Visual detection: Precise timing

Output: SRT file with accurate text and timing
"""

import cv2
import os
import sys
import numpy as np
import re
from difflib import SequenceMatcher

# === CONFIG ===
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"

# Subtitle crop region
CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.12
CROP_X_END = 0.88

TEXT_SIMILARITY = 0.65
VISUAL_DIFF_THRESHOLD = 0.95
MIN_GROUP_DURATION = 0.5
MIN_TEXT_LEN = 3

def format_srt_time(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    secs = int(seconds)
    mins = (secs % 3600) // 60
    hrs = secs // 3600
    secs = secs % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def clean_text(text):
    """Remove noise from OCR result"""
    # Remove watermarks
    text = re.sub(r'字幕\s*[bB][yY]\s*[\w\u4e00-\u9fff]+', '', text)
    text = re.sub(r'字幕\s*[:：]?\s*[\w\u4e00-\u9fff]+', '', text)
    # Remove special chars at end
    text = re.sub(r'[\d]+\s*[「」『』【】\[\]~～()（）]+\s*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_watermark(text):
    """Check if text is just watermark"""
    watermarks = ['字幕', '翻译', '校对', '制作', 'by', 'BY']
    clean = text.strip()
    if len(clean) < 3:
        return True
    for w in watermarks:
        if w in clean:
            return True
    return False

def process_video_paddle(video_path):
    """Extract subtitles using PaddleOCR with visual timing"""
    print("=" * 60)
    print("PADDLEOCR SUBTITLE EXTRACTION")
    print("  PaddleOCR → Text | Visual → Timing")
    print("=" * 60)
    
    # Initialize PaddleOCR
    try:
        from paddleocr import PaddleOCR
        import os
        os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        ocr = PaddleOCR(lang='ch')
        print("PaddleOCR initialized successfully")
    except ImportError:
        print("ERROR: PaddleOCR not installed!")
        print("Run: pip install paddlepaddle paddleocr")
        return
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_srt = f"{video_name}_paddle.srt"
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Video: {video_name} | FPS: {fps}")
    
    results = []
    prev_crop_gray = None
    
    # Group state
    group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}
    
    frame_idx = 0
    SAMPLE_RATE = 3  # Sample every N frames for speed
    
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
        
        # Visual diff check
        is_same = False
        if prev_crop_gray is not None and crop_gray.shape == prev_crop_gray.shape:
            if np.mean(crop_gray == prev_crop_gray) > VISUAL_DIFF_THRESHOLD:
                is_same = True
        prev_crop_gray = crop_gray.copy()
        
        # If same visual, extend current group
        if is_same and group["active"]:
            group["end_time"] = curr_time
            frame_idx += 1
            continue
        
        # OCR with PaddleOCR
        try:
            result = ocr.predict(crop)
        except:
            result = None
        
        # Extract text from PaddleOCR result
        # Structure: result[0] = dict with 'rec_texts' and 'rec_scores'
        detected_text = ""
        try:
            if result and len(result) > 0 and isinstance(result[0], dict):
                texts = result[0].get('rec_texts', [])
                scores = result[0].get('rec_scores', [])
                # Filter by confidence > 0.7
                good_texts = [t for t, s in zip(texts, scores) if s > 0.7]
                detected_text = " ".join(good_texts)
        except:
            pass
        
        detected_text = clean_text(detected_text)
        
        # Progress log every 30 frames
        if frame_idx % 30 == 0:
            pct = int(frame_idx / total_frames * 100)
            print(f"\r{pct}% | {format_srt_time(curr_time)} | Subs: {len(results)} | Text: {detected_text[:15]}...", end="", flush=True)
        
        if len(detected_text) >= MIN_TEXT_LEN and not is_watermark(detected_text):
            if not group["active"]:
                # Start new group
                group = {
                    "text_list": [detected_text],
                    "current_text": detected_text,
                    "start_time": curr_time,
                    "end_time": curr_time,
                    "active": True
                }
            else:
                # Compare with current group
                clean_curr = re.sub(r'\W', '', group["current_text"])
                clean_new = re.sub(r'\W', '', detected_text)
                ratio = SequenceMatcher(None, clean_curr, clean_new).ratio()
                
                if ratio > TEXT_SIMILARITY:
                    # Same text, extend
                    group["end_time"] = curr_time
                    group["text_list"].append(detected_text)
                    if len(detected_text) > len(group["current_text"]):
                        group["current_text"] = detected_text
                else:
                    # Different text, save current and start new
                    if group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                        final_text = max(set(group["text_list"]), key=group["text_list"].count)
                        results.append((group["start_time"], group["end_time"], final_text))
                        print(f"  [{len(results)}] {format_srt_time(group['start_time'])} : {final_text[:25]}...")
                    
                    group = {
                        "text_list": [detected_text],
                        "current_text": detected_text,
                        "start_time": curr_time,
                        "end_time": curr_time,
                        "active": True
                    }
        else:
            # No text, save current group
            if group["active"] and group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                final_text = max(set(group["text_list"]), key=group["text_list"].count)
                results.append((group["start_time"], group["end_time"], final_text))
                print(f"  [{len(results)}] {format_srt_time(group['start_time'])} : {final_text[:25]}...")
            
            group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}
        
        if frame_idx % 90 == 0:
            pct = int(frame_idx / total_frames * 100)
            sys.stdout.write(f"\r{pct}% | {format_srt_time(curr_time)} | Subs: {len(results)}")
            sys.stdout.flush()
        
        frame_idx += 1
    
    # Save last group
    if group["active"] and group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
        final_text = max(set(group["text_list"]), key=group["text_list"].count)
        results.append((group["start_time"], group["end_time"], final_text))
    
    cap.release()
    
    # Save SRT
    with open(output_srt, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(results, 1):
            f.write(f"{i}\n")
            f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
            f.write(f"{text}\n\n")
    
    print(f"\n\n✓ Done! Total: {len(results)} subtitles")
    print(f"Saved: {output_srt}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        video_input = VIDEO_PATH
    
    if os.path.exists(video_input):
        process_video_paddle(video_input)
    else:
        print(f"Error: File not found - {video_input}")
