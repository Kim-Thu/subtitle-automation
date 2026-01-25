import cv2
import os
import sys
import shutil
import easyocr
import numpy as np
import re
from difflib import SequenceMatcher

# --- CẤU HÌNH V18: GIẢM NHIỄU, GOM NHÓM TỐT HƠN ---
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"
OUTPUT_ROOT = "frames_grouped_v18_stable"

# Vùng cắt
CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.12
CROP_X_END = 0.88

# === CẢI TIẾN SO VỚI V17 ===
TEXT_SIMILARITY = 0.65       # Tăng từ 0.5 lên 0.65 để gom OCR rung
VISUAL_DIFF_THRESHOLD = 0.95 # Giảm từ 0.98 xuống 0.95 (chấp nhận thay đổi nhỏ trong cảnh)
MIN_GROUP_DURATION = 0.5     # Tăng từ 0.2s lên 0.5s (loại bỏ group rác)
STABILIZATION_FRAMES = 3     # Số frame text phải khác liên tiếp mới tách nhóm mới
MIN_TEXT_LEN = 3 

def format_timestamp(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    minutes = (seconds % 3600) // 60
    hours = seconds // 3600
    seconds = seconds % 60
    return f"{hours:02d}.{minutes:02d}.{seconds:02d}.{millis:03d}"

def clean_text(text):
    """Loại bỏ ký tự đặc biệt, chỉ giữ chữ cái/số để so sánh chính xác hơn"""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text)

def finalize_group(base_folder, temp_folder, text_list, start_t, end_t):
    if not temp_folder or not os.path.exists(temp_folder): return
    if not text_list: 
        shutil.rmtree(temp_folder)
        return

    # Chọn text xuất hiện nhiều nhất
    final_text = max(set(text_list), key=text_list.count)
    safe_text = "".join([c for c in final_text if c.isalnum() or c in " _-"])[:30]
    
    # Bỏ qua group quá ngắn
    if end_t - start_t < MIN_GROUP_DURATION:
        shutil.rmtree(temp_folder)
        return

    folder_name = f"{format_timestamp(start_t)}__TO__{format_timestamp(end_t)}"
    target_path = os.path.join(base_folder, folder_name)

    if os.path.exists(target_path): shutil.rmtree(target_path)
    
    try:
        os.rename(temp_folder, target_path)
        with open(os.path.join(target_path, "content.txt"), "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"  [SUB] {folder_name} : {safe_text}")
    except: pass

def process_video_stable(video_path):
    print("--- V18: STABLE GROUPING (Giảm Nhiễu) ---")
    print(f"Cấu hình: TEXT_SIMILARITY={TEXT_SIMILARITY}, VISUAL_DIFF={VISUAL_DIFF_THRESHOLD}, MIN_DURATION={MIN_GROUP_DURATION}s")
    
    reader = easyocr.Reader(['ch_sim'], gpu=True, verbose=False)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(OUTPUT_ROOT, video_name)
    if os.path.exists(out_dir): shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    print(f"Video: {video_name} | FPS: {fps}")
    
    curr_frame = 0
    group = {"text_list": [], "current_text": "", "start_time": 0, "last_frame_time": 0, "temp_folder": None}
    
    prev_crop_gray = None
    
    # === STABILIZATION BUFFER ===
    # Chỉ tách nhóm khi text khác liên tục N frame (tránh OCR rung)
    diff_buffer = []  # Lưu các text khác biệt gần đây

    while True:
        ret, frame = cap.read()
        if not ret: break

        curr_time = curr_frame / fps
        h, w = frame.shape[:2]
        
        crop = frame[int(h*CROP_Y_START):int(h*CROP_Y_END), int(w*CROP_X_START):int(w*CROP_X_END)]
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # Visual diff check (giảm ngưỡng để chấp nhận thay đổi nhỏ)
        is_same_visual = False
        if prev_crop_gray is not None and crop_gray.shape == prev_crop_gray.shape:
            score = np.mean(crop_gray == prev_crop_gray)
            if score > VISUAL_DIFF_THRESHOLD: 
                is_same_visual = True
        
        prev_crop_gray = crop_gray.copy()

        # Nếu hình giống -> Kéo dài group hiện tại, skip OCR
        if is_same_visual and group["temp_folder"]:
            group["last_frame_time"] = curr_time
            diff_buffer = []  # Reset buffer khi ổn định
            curr_frame += 1
            continue

        # OCR
        res = reader.readtext(crop_gray, detail=0, paragraph=True) 
        detected_text = "".join(res).strip()
        detected_clean = clean_text(detected_text)

        if len(detected_text) >= MIN_TEXT_LEN:
            if not group["temp_folder"]:
                # Bắt đầu nhóm MỚI - NGAY LẬP TỨC (không cần đợi stabilization)
                temp_dir = os.path.join(out_dir, f"temp_{curr_frame}")
                os.makedirs(temp_dir, exist_ok=True)
                group = {
                    "text_list": [detected_text],
                    "current_text": detected_text,
                    "start_time": curr_time,
                    "last_frame_time": curr_time,
                    "temp_folder": temp_dir
                }
                cv2.imwrite(f"{temp_dir}/key.jpg", crop)
                diff_buffer = []
                print(f"  [START] Group at {format_timestamp(curr_time)}")
            else:
                # So sánh với nhóm hiện tại (dùng clean text)
                current_clean = clean_text(group["current_text"])
                ratio = SequenceMatcher(None, current_clean, detected_clean).ratio()
                
                if ratio > TEXT_SIMILARITY:
                    # Giống -> Gộp vào nhóm
                    group["last_frame_time"] = curr_time
                    group["text_list"].append(detected_text)
                    if len(detected_text) > len(group["current_text"]):
                        group["current_text"] = detected_text
                    diff_buffer = []  # Reset buffer
                else:
                    # Khác -> Thêm vào buffer
                    diff_buffer.append(detected_text)
                    
                    # Chỉ tách nhóm mới khi khác liên tục N frame
                    if len(diff_buffer) >= STABILIZATION_FRAMES:
                        # Xác nhận đây là text mới thực sự
                        finalize_group(out_dir, group["temp_folder"], group["text_list"], 
                                      group["start_time"], group["last_frame_time"])
                        
                        # Mở nhóm mới với text ổn định nhất từ buffer
                        stable_text = max(set(diff_buffer), key=diff_buffer.count)
                        temp_dir = os.path.join(out_dir, f"temp_{curr_frame}")
                        os.makedirs(temp_dir, exist_ok=True)
                        group = {
                            "text_list": [stable_text],
                            "current_text": stable_text,
                            "start_time": curr_time - len(diff_buffer)/fps,  # Bắt đầu từ frame đầu tiên khác
                            "last_frame_time": curr_time,
                            "temp_folder": temp_dir
                        }
                        cv2.imwrite(f"{temp_dir}/key.jpg", crop)
                        diff_buffer = []
        else:
            # Không có chữ -> Chốt nhóm
            if group["temp_folder"]:
                finalize_group(out_dir, group["temp_folder"], group["text_list"], 
                              group["start_time"], group["last_frame_time"])
                group = {"text_list": [], "current_text": "", "start_time": 0, "last_frame_time": 0, "temp_folder": None}
            diff_buffer = []

        if curr_frame % 30 == 0:
            per = int(curr_frame / total_frames * 100)
            sys.stdout.write(f"\r{per}% | Time: {format_timestamp(curr_time)} | Groups: {len(os.listdir(out_dir))}...")
            sys.stdout.flush()

        curr_frame += 1

    if group["temp_folder"]:
        finalize_group(out_dir, group["temp_folder"], group["text_list"], 
                      group["start_time"], group["last_frame_time"])

    cap.release()
    
    # Thống kê kết quả
    final_groups = len([d for d in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, d))])
    print(f"\n--- XONG V18 ---")
    print(f"Tổng số nhóm: {final_groups}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_input = sys.argv[1]
    else:
        video_input = VIDEO_PATH

    if os.path.exists(video_input):
        process_video_stable(video_input)
    else:
        print("Lỗi file.")