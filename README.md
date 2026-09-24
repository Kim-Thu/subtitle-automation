# 🎬 Auto Subtitle Pro

Auto Subtitle Pro là công cụ tự động hóa quy trình tạo phụ đề, dịch thuật và lồng tiếng (TTS) cho video. Hỗ trợ nhiều engine dịch thuật (Google, Gemini AI, Ollama) và tích hợp lồng tiếng đa ngôn ngữ.

![Dashboard Preview](https://github.com/Kim-Thu/subtitle-automation/raw/main/static/demo.png)

## 🌟 Tính năng nổi bật

- **Tự động tạo phụ đề:** Sử dụng OpenAI Whisper để chuyển đổi giọng nói thành văn bản chính xác.
- **Dịch thuật đa năng:** Hỗ trợ Google Translate, Gemini AI (chất lượng cao) và Ollama (chạy local bảo mật).
- **Lồng tiếng AI (Dubbing):** Tự động tạo giọng đọc AI bằng Microsoft Edge TTS.
- **Trộn âm thanh (Audio Merge):** Tự động mix giọng lồng tiếng với nhạc nền của video gốc.
- **Chỉnh sửa thủ công:** Cho phép sửa lại kịch bản (Script) hoặc upload file SRT có sẵn.
- **Quản lý file thông minh:** Mỗi video upload lên được lưu trong một thư mục riêng biệt tại `inputs/`.

## 🛠 Yêu cầu hệ thống

- **Python:** 3.9 trở lên.
- **FFmpeg:** Phải được cài đặt và thêm vào PATH hệ thống để xử lý video/audio.
- **Ollama (Tùy chọn):** Nếu muốn sử dụng dịch thuật local.
- **Gemini API Key (Tùy chọn):** Nếu muốn sử dụng AI của Google.

## 🚀 Hướng dẫn cài đặt

1. **Clone repository:**
   ```bash
   git clone https://github.com/Kim-Thu/subtitle-automation.git
   cd subtitle-automation
   ```

2. **Khởi tạo môi trường ảo (Virtual Env):**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Trên Windows
   # source .venv/bin/activate # Trên Linux/Mac
   ```

3. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Chạy ứng dụng:**
   ```bash
   python app.py
   ```
   Truy cập Dashboard tại: `http://localhost:5000`

## 📖 Hướng dẫn sử dụng

1. **Upload Video:** Bấm nút **Upload** trên Sidebar hoặc copy video vào thư mục `inputs/`.
2. **Cấu hình:**
   - Chọn **Target Language** (Ngôn ngữ muốn dịch sang).
   - Chọn **Translation Engine** (Nên dùng Gemini AI nếu có API Key).
   - Chọn kiểu hiển thị phụ đề (Màu sắc, Vị trí).
3. **Xử lý:**
   - Bấm **Process** cho từng video hoặc **Process All** để chạy hàng loạt.
   - Theo dõi tiến độ (0% -> 100%) tại cột Metrics.
4. **Kết quả:**
   - Sau khi hoàn thành, trạng thái sẽ là **Done**.
   - Bấm biểu tượng **✅** để xem Preview kết quả.
   - Bấm nút **⬇️** để tải video đã gắn sub/lồng tiếng.

## 📁 Cấu trúc thư mục

- `inputs/`: Chứa video gốc (mỗi video một thư mục).
- `outputs/`: Chứa video thành phẩm đã xử lý.
- `temp/`: Chứa các file phụ đề tạm thời (.srt).
- `static/`: Chứa CSS, JS và hình ảnh giao diện.
- `templates/`: Chứa các trang HTML.

## Contributions & Paid Work

Auto Subtitle Pro is currently a **personal open-source project** that I build for learning, experimentation, and portfolio purposes. It is **not funded, and there are currently no paid roles associated with this repository**.

Contributions are always welcome, but they are entirely voluntary. You are welcome to pick up an open issue, propose an idea, or open a pull request.

If you prefer to develop the project independently, you are also welcome to **fork the repository and build your own version**, in accordance with the project license.

If you are specifically looking for paid work, please do not feel any obligation to contribute. If paid collaboration becomes available in the future, it will be stated explicitly in the relevant issue or project announcement.

---
*Phát triển bởi Kim-Thu. Sử dụng công nghệ Whisper, Gemini & FFmpeg.*
