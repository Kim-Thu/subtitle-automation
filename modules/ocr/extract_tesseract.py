"""
TESSERACT OCR SUBTITLE EXTRACTION
Traditional approach - fast and reliable
- Image preprocessing (binarization, contrast)
- Tesseract OCR for Chinese
- Visual timing detection
"""

import cv2
import os
import sys
import numpy as np
import re
from difflib import SequenceMatcher
import pytesseract

# === CONFIG ===
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"

# Set Tesseract path if needed (Windows)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Subtitle crop region
CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.10
CROP_X_END = 0.90

TEXT_SIMILARITY = 0.60
VISUAL_DIFF_THRESHOLD = 0.95
MIN_GROUP_DURATION = 0.4
MIN_TEXT_LEN = 2

def format_srt_time(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    secs = int(seconds)
    mins = (secs % 3600) // 60
    hrs = secs // 3600
    secs = secs % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def preprocess_for_ocr(crop):
    """
    Traditional image preprocessing for OCR
    - Convert to grayscale
    - Increase contrast
    - Binarization (white text on black bg -> black text on white bg)
    - Denoise
    """
    # Grayscale
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Increase contrast with CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    # Binarization - invert so text is black on white (better for Tesseract)
    _, binary = cv2.threshold(enhanced, 180, 255, cv2.THRESH_BINARY)
    
    # If mostly black (subtitle is white), invert
    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)
    
    # Denoise
    denoised = cv2.medianBlur(binary, 3)
    
    # Scale up 2x for better OCR
    scaled = cv2.resize(denoised, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    return scaled

def clean_text(text):
    """Clean OCR noise"""
    text = re.sub(r'字幕\s*[bB][yY]\s*[\w\u4e00-\u9fff]+', '', text)
    text = re.sub(r'[|｜\[\]【】「」『』]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_watermark(text):
    watermarks = ['字幕', '翻译', '校对', '制作', 'by', 'BY', 'http', 'www']
    clean = text.strip()
    if len(clean) < 2:
        return True
    for w in watermarks:
        if w in clean:
            return True
    return False

def process_video_tesseract(video_path):
    """Extract subtitles using Tesseract OCR"""
    print("=" * 60)
    print("TESSERACT OCR SUBTITLE EXTRACTION")
    print("  Traditional approach - fast & reliable")
    print("=" * 60)
    
    # Test Tesseract
    try:
        pytesseract.get_tesseract_version()
        print("Tesseract OK")
    except Exception as e:
        print(f"ERROR: Tesseract not found! {e}")
        print("Install: https://github.com/tesseract-ocr/tesseract")
        return
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_srt = f"{video_name}_tesseract.srt"
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Video: {video_name} | FPS: {fps} | Frames: {total_frames}")
    
    results = []
    prev_crop_gray = None
    group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}
    
    frame_idx = 0
    SAMPLE_RATE = 5  # Sample every N frames
    
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
        
        # Visual diff check - skip if same
        is_same = False
        if prev_crop_gray is not None and crop_gray.shape == prev_crop_gray.shape:
            if np.mean(crop_gray == prev_crop_gray) > VISUAL_DIFF_THRESHOLD:
                is_same = True
        prev_crop_gray = crop_gray.copy()
        
        if is_same and group["active"]:
            group["end_time"] = curr_time
            frame_idx += 1
            continue
        
        # Preprocess and OCR
        processed = preprocess_for_ocr(crop)
        
        # Tesseract OCR - Chinese simplified
        try:
            detected_text = pytesseract.image_to_string(
                processed, 
                lang='chi_sim',  # Chinese simplified
                config='--psm 7 --oem 3'  # Single line mode
            )
        except:
            detected_text = ""
        
        detected_text = clean_text(detected_text)
        
        # Progress
        if frame_idx % 30 == 0:
            pct = int(frame_idx / total_frames * 100)
            print(f"\r{pct}% | {format_srt_time(curr_time)} | Subs: {len(results)} | {detected_text[:12]}...", end="", flush=True)
        
        if len(detected_text) >= MIN_TEXT_LEN and not is_watermark(detected_text):
            if not group["active"]:
                group = {
                    "text_list": [detected_text],
                    "current_text": detected_text,
                    "start_time": curr_time,
                    "end_time": curr_time,
                    "active": True
                }
            else:
                clean_curr = re.sub(r'\W', '', group["current_text"])
                clean_new = re.sub(r'\W', '', detected_text)
                ratio = SequenceMatcher(None, clean_curr, clean_new).ratio()
                
                if ratio > TEXT_SIMILARITY:
                    group["end_time"] = curr_time
                    group["text_list"].append(detected_text)
                    if len(detected_text) > len(group["current_text"]):
                        group["current_text"] = detected_text
                else:
                    if group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                        final_text = max(set(group["text_list"]), key=group["text_list"].count)
                        results.append((group["start_time"], group["end_time"], final_text))
                    
                    group = {
                        "text_list": [detected_text],
                        "current_text": detected_text,
                        "start_time": curr_time,
                        "end_time": curr_time,
                        "active": True
                    }
        else:
            if group["active"] and group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                final_text = max(set(group["text_list"]), key=group["text_list"].count)
                results.append((group["start_time"], group["end_time"], final_text))
            
            group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}
        
        frame_idx += 1
    
    # Last group
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
    
    print(f"\n\n✓ Done! {len(results)} subtitles")
    print(f"Saved: {output_srt}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        video_input = VIDEO_PATH
    
    if os.path.exists(video_input):
        process_video_tesseract(video_input)
    else:
        print(f"Error: File not found - {video_input}")
