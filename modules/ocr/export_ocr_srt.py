import cv2
import os
import sys
import easyocr
import numpy as np
import re
from difflib import SequenceMatcher

# --- CẤU HÌNH V19: XUẤT SRT TRỰC TIẾP (KHÔNG TẠO FOLDER) ---
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"

# Vùng cắt subtitle
CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.12
CROP_X_END = 0.88

TEXT_SIMILARITY = 0.65
VISUAL_DIFF_THRESHOLD = 0.95
MIN_GROUP_DURATION = 0.5
MIN_TEXT_LEN = 3

def format_srt_time(seconds):
    """Format: 00:01:23,456"""
    millis = int((seconds - int(seconds)) * 1000)
    secs = int(seconds)
    mins = (secs % 3600) // 60
    hrs = secs // 3600
    secs = secs % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def clean_text(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text)

def process_video_to_srt(video_path):
    print("--- V19: OCR TO SRT (No Folders) ---")
    
    reader = easyocr.Reader(['ch_sim'], gpu=True, verbose=False)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_srt = f"{video_name}_ocr.srt"
    
    # Xóa file cũ nếu có
    if os.path.exists(output_srt):
        os.remove(output_srt)
    
    print(f"Video: {video_name} | FPS: {fps}")
    print(f"Output: {output_srt}")
    
    curr_frame = 0
    prev_crop_gray = None
    
    # Group state
    group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}
    srt_counter = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break

        curr_time = curr_frame / fps
        h, w = frame.shape[:2]
        
        crop = frame[int(h*CROP_Y_START):int(h*CROP_Y_END), int(w*CROP_X_START):int(w*CROP_X_END)]
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # Visual diff
        is_same = False
        if prev_crop_gray is not None and crop_gray.shape == prev_crop_gray.shape:
            if np.mean(crop_gray == prev_crop_gray) > VISUAL_DIFF_THRESHOLD:
                is_same = True
        prev_crop_gray = crop_gray.copy()

        # Nếu hình giống -> Kéo dài group
        if is_same and group["active"]:
            group["end_time"] = curr_time
            curr_frame += 1
            continue

        # OCR
        res = reader.readtext(crop_gray, detail=0, paragraph=True)
        detected_text = "".join(res).strip()
        detected_clean = clean_text(detected_text)

        if len(detected_text) >= MIN_TEXT_LEN:
            if not group["active"]:
                # Bắt đầu group mới
                group = {
                    "text_list": [detected_text],
                    "current_text": detected_text,
                    "start_time": curr_time,
                    "end_time": curr_time,
                    "active": True
                }
            else:
                # So sánh với group hiện tại
                ratio = SequenceMatcher(None, clean_text(group["current_text"]), detected_clean).ratio()
                
                if ratio > TEXT_SIMILARITY:
                    # Giống -> Gộp
                    group["end_time"] = curr_time
                    group["text_list"].append(detected_text)
                    if len(detected_text) > len(group["current_text"]):
                        group["current_text"] = detected_text
                else:
                    # Khác -> Lưu group cũ, mở mới
                    if group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                        srt_counter += 1
                        final_text = max(set(group["text_list"]), key=group["text_list"].count)
                        with open(output_srt, "a", encoding="utf-8") as f:
                            f.write(f"{srt_counter}\n")
                            f.write(f"{format_srt_time(group['start_time'])} --> {format_srt_time(group['end_time'])}\n")
                            f.write(f"{final_text}\n\n")
                        print(f"  [{srt_counter}] {format_srt_time(group['start_time'])} : {final_text[:20]}...")
                    
                    group = {
                        "text_list": [detected_text],
                        "current_text": detected_text,
                        "start_time": curr_time,
                        "end_time": curr_time,
                        "active": True
                    }
        else:
            # Không có text -> Lưu group nếu đủ dài
            if group["active"] and group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
                srt_counter += 1
                final_text = max(set(group["text_list"]), key=group["text_list"].count)
                with open(output_srt, "a", encoding="utf-8") as f:
                    f.write(f"{srt_counter}\n")
                    f.write(f"{format_srt_time(group['start_time'])} --> {format_srt_time(group['end_time'])}\n")
                    f.write(f"{final_text}\n\n")
                print(f"  [{srt_counter}] {format_srt_time(group['start_time'])} : {final_text[:20]}...")
            
            group = {"text_list": [], "current_text": "", "start_time": 0, "end_time": 0, "active": False}

        if curr_frame % 30 == 0:
            per = int(curr_frame / total_frames * 100)
            sys.stdout.write(f"\r{per}% | {format_srt_time(curr_time)} | Subs: {srt_counter}")
            sys.stdout.flush()

        curr_frame += 1

    # Lưu group cuối
    if group["active"] and group["end_time"] - group["start_time"] >= MIN_GROUP_DURATION:
        srt_counter += 1
        final_text = max(set(group["text_list"]), key=group["text_list"].count)
        with open(output_srt, "a", encoding="utf-8") as f:
            f.write(f"{srt_counter}\n")
            f.write(f"{format_srt_time(group['start_time'])} --> {format_srt_time(group['end_time'])}\n")
            f.write(f"{final_text}\n\n")

    cap.release()
    print(f"\n--- XONG! Tổng: {srt_counter} subtitles ---")
    print(f"File: {output_srt}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        video_input = VIDEO_PATH

    if os.path.exists(video_input):
        process_video_to_srt(video_input)
    else:
        print("Lỗi: File không tồn tại")
