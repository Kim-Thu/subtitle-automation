import cv2
import os
import sys
import easyocr
import shutil
import numpy as np
import warnings
from difflib import SequenceMatcher

# Chặn cảnh báo hệ thống
warnings.filterwarnings("ignore")
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# --- CẤU HÌNH ---
VIDEO_PATH = r"D:\www\site-video-faceless\inputs\quy-luat-sinh-tu-i-tap-9-thot-tim.mp4"
OUTPUT_FILE = "ket_qua_v21_precision.srt"

CROP_Y_START = 0.82
CROP_Y_END = 0.98
CROP_X_START = 0.15 
CROP_X_END = 0.85
TEXT_SIMILARITY = 0.5

def format_timestamp(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    minutes = (seconds % 3600) // 60
    hours = seconds // 3600
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

def process_video_v21():
    import torch
    print(f"--- V21: PHÂN TÍCH CHUẨN XÁC (STREAM MODE) ---")
    
    # Kiểm tra và kích hoạt GPU NVIDIA
    use_gpu = torch.cuda.is_available()
    print(f"Sử dụng Card đồ họa (GPU): {'CÓ' if use_gpu else 'KHÔNG (Chạy bằng CPU)'}")
    if use_gpu:
        print(f"Thiết bị: {torch.cuda.get_device_name(0)}")

    reader = easyocr.Reader(['ch_sim'], gpu=use_gpu, verbose=False)

    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    video_name = os.path.splitext(os.path.basename(VIDEO_PATH))[0]
    if os.path.exists(OUTPUT_FILE): os.remove(OUTPUT_FILE)

    curr_idx = 0
    srt_cnt = 1
    
    # Biến lưu trữ sub đang diễn ra
    active_sub = {"text": "", "start_time": 0, "last_frame_time": 0, "text_list": []}
    prev_crop_gray = None

    print(f"\nBắt đầu quét video: {video_name}")
    print("-" * 70)

    while True:
        ret, frame = cap.read()
        if not ret: break

        curr_time = curr_idx / fps
        h, w = frame.shape[:2]
        
        # 1. Cắt vùng sub
        y1, y2 = int(h*CROP_Y_START), int(h*CROP_Y_END)
        x1, x2 = int(w*CROP_X_START), int(w*CROP_X_END)
        crop = frame[y1:y2, x1:x2]
        
        # 2. Xử lý ảnh xám để so sánh nhanh
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # 3. So sánh Visual (Nếu ảnh không đổi, không cần chạy OCR)
        is_same_image = False
        if prev_crop_gray is not None:
            # So sánh độ tương đồng pixel
            diff = cv2.absdiff(crop_gray, prev_crop_gray)
            if np.mean(diff) < 2.0: # Ngưỡng thay đổi rất nhỏ (dưới 2 đơn vị pixel)
                is_same_image = True
        
        prev_crop_gray = crop_gray.copy()

        # --- LOGIC XỬ LÝ ---
        detected_text = ""
        
        if is_same_image and active_sub["text"] != "":
            # Ảnh giống hệt frame trước -> Kéo dài thời gian, không cần chạy OCR lại
            active_sub["last_frame_time"] = curr_time
        else:
            # Ảnh đã thay đổi hoặc là frame đầu -> Chạy OCR
            # Chỉ chạy OCR nếu vùng này có đủ độ sáng (có khả năng có chữ)
            if np.mean(crop_gray) > 30: 
                res = reader.readtext(crop_gray, detail=0, paragraph=True)
                detected_text = "".join(res).strip()

            if len(detected_text) >= 2:
                # Nếu chưa có sub nào active -> Bắt đầu sub mới
                if active_sub["text"] == "":
                    active_sub = {
                        "text": detected_text,
                        "start_time": curr_time,
                        "last_frame_time": curr_time,
                        "text_list": [detected_text]
                    }
                else:
                    # Đã có sub active, kiểm tra xem có phải câu cũ không
                    ratio = SequenceMatcher(None, active_sub["text"], detected_text).ratio()
                    if ratio > TEXT_SIMILARITY:
                        active_sub["last_frame_time"] = curr_time
                        active_sub["text_list"].append(detected_text)
                        if len(detected_text) > len(active_sub["text"]):
                            active_sub["text"] = detected_text
                    else:
                        # Câu mới khác hoàn toàn -> Lưu câu cũ
                        write_srt(active_sub, srt_cnt)
                        srt_cnt += 1
                        # Reset cho câu mới
                        active_sub = {
                            "text": detected_text,
                            "start_time": curr_time,
                            "last_frame_time": curr_time,
                            "text_list": [detected_text]
                        }
            else:
                # Không có chữ -> Kết thúc sub đang active
                if active_sub["text"] != "":
                    write_srt(active_sub, srt_cnt)
                    srt_cnt += 1
                    active_sub = {"text": "", "start_time": 0, "last_frame_time": 0, "text_list": []}

        # Hiển thị tiến độ frame-by-frame
        if curr_idx % 15 == 0:
            per = (curr_idx / total_frames) * 100
            sys.stdout.write(f"\rProgress: {per:.1f}% | Time: {format_timestamp(curr_time)} | Capturing: {active_sub['text'][:15]}...")
            sys.stdout.flush()

        curr_idx += 1

    cap.release()
    print(f"\n" + "-" * 70)
    print(f"--- HOÀN TẤT! File: {OUTPUT_FILE} ---")

def write_srt(sub, counter):
    """Ghi dữ liệu vào file và in log ra màn hình"""
    if not sub["text_list"]: return
    
    # Lấy text phổ biến nhất trong đợt quét
    final_text = max(set(sub["text_list"]), key=sub["text_list"].count)
    
    # Lọc bỏ sub rác quá ngắn
    if sub["last_frame_time"] - sub["start_time"] < 0.2: return

    s_str = format_timestamp(sub["start_time"])
    e_str = format_timestamp(sub["last_frame_time"])

    # Ghi file
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{counter}\n{s_str} --> {e_str}\n{final_text}\n\n")

    # XUẤT LOG NHƯ BẢN 18
    print(f"\n[STT: {counter}] [{s_str} --> {e_str}] {final_text}")

if __name__ == "__main__":
    process_video_v21()