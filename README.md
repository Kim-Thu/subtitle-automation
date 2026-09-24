# 🎬 Auto Subtitle Pro

Auto Subtitle Pro là công cụ tự động hóa quy trình tạo phụ đề, dịch thuật và lồng tiếng (TTS) cho video. Hỗ trợ nhiều engine dịch thuật (Google, Gemini AI, Ollama) và tích hợp lồng tiếng đa ngôn ngữ.

![Dashboard Preview](https://github.com/Kim-Thu/subtitle-automation/raw/main/static/demo.png)

## 🌟 Tính năng nổi bật

- **Tự động tạo phụ đề:** Sử dụng OpenAI Whisper để chuyển đổi giọng nói thành văn bản.
- **Dịch thuật đa engine:** Hỗ trợ Google Translate, Gemini AI và Ollama chạy local.
- **Lồng tiếng AI (Dubbing):** Tạo giọng đọc bằng Microsoft Edge TTS.
- **Audio Merge:** Khi bật, giọng dub được mix với audio gốc; khi tắt, audio gốc được thay bằng track dub.
- **Chỉnh sửa thủ công:** Cho phép dùng script hoặc SRT có sẵn trước khi render.
- **Quản lý file theo video:** Mỗi video upload được lưu trong workspace riêng bên trong `inputs/`.

## 🛠 Yêu cầu hệ thống

- **Python:** 3.9 trở lên.
- **FFmpeg:** Cần được cài đặt và có trong PATH, hoặc đặt executable phù hợp trong thư mục `bin/`.
- **Ollama (tùy chọn):** Cần khi dùng dịch local.
- **Gemini API Key (tùy chọn):** Cần khi dùng Gemini.
- **Định dạng video hỗ trợ:** `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`.
- **Video codec hỗ trợ:** H.264 (`h264`), H.265/HEVC (`hevc`), MPEG-4 (`mpeg4`), VP8, VP9 và AV1.
- **Giới hạn upload mặc định:** 2048 MB mỗi request. Có thể thay đổi bằng biến môi trường `MAX_UPLOAD_MB`.
- File upload được kiểm tra bằng **FFprobe** trước khi chấp nhận; file hỏng, không có video stream hoặc codec không hỗ trợ sẽ bị từ chối sớm.

## 🚀 Hướng dẫn cài đặt

1. **Clone repository:**
   ```bash
   git clone https://github.com/Kim-Thu/subtitle-automation.git
   cd subtitle-automation
   ```

2. **Khởi tạo môi trường ảo:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/macOS
   ```

3. **Cài đặt dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Chạy ứng dụng:**
   ```bash
   python app.py
   ```

   Truy cập Dashboard tại: `http://localhost:5000`

## 📖 Hướng dẫn sử dụng

1. **Upload video:** Dùng nút **Upload** hoặc đặt video vào thư mục `inputs/`.
2. **Cấu hình:** Chọn target language, translation engine, Whisper model và subtitle style.
3. **Xử lý:** Nhấn **Process** cho từng video hoặc **Process All**.
4. **Dubbing:** Nếu bật dubbing, ứng dụng tạo track dub và dùng **Audio Merge** để quyết định mix với audio gốc hay thay audio gốc.
5. **Kết quả:** Khi dubbing thành công, file dubbed là output cuối; nếu không bật dubbing thì output cuối là video đã burn subtitle.

## 📁 Cấu trúc thư mục

- `inputs/`: Video gốc, theo workspace của từng video.
- `outputs/<video>/subtitled/`: Video đã burn subtitle.
- `outputs/<video>/dubbed/`: Video đã lồng tiếng.
- `outputs/<video>/audios/`: Track audio dub được tạo trong quá trình xử lý.
- `temp/<video>/`: SRT và file tạm.
- `static/`: CSS, JavaScript và assets giao diện.
- `templates/`: Các trang HTML.
- `tests/`: Test cho các thành phần core.

## ⚠️ Trạng thái tính năng

- OCR hiện vẫn là phần **experimental / legacy** và chưa phải flow chính của web app.
- Các job xử lý được giới hạn bởi worker pool thay vì tạo thread không giới hạn.
- Một số tính năng lớn như subtitle timeline editor, dubbing timeline nâng cao và workspace UI mới vẫn đang được phát triển theo các issue mở.

## 🤝 Đóng góp & Công việc có trả phí

Auto Subtitle Pro hiện là **dự án mã nguồn mở cá nhân**, được phát triển phục vụ việc học tập, thử nghiệm và xây dựng portfolio. Dự án **hiện chưa có tài trợ và chưa có vị trí cộng tác có trả phí**.

Mọi đóng góp đều được hoan nghênh nhưng hoàn toàn tự nguyện. Bạn có thể nhận một issue đang mở, đề xuất ý tưởng hoặc tạo pull request.

Nếu muốn phát triển theo hướng riêng, bạn cũng có thể **fork repository và xây dựng phiên bản của riêng mình**, theo giấy phép của dự án.

Nếu bạn đang tìm công việc có trả phí, bạn không cần cảm thấy có nghĩa vụ phải đóng góp. Nếu sau này có cơ hội cộng tác trả phí, thông tin sẽ được ghi rõ trong issue hoặc thông báo của dự án.

### Contributions & Paid Work

Auto Subtitle Pro is currently a **personal open-source project** built for learning, experimentation, and portfolio purposes. It is **not funded, and there are currently no paid roles associated with this repository**.

Contributions are always welcome, but entirely voluntary. You are welcome to pick up an open issue, propose an idea, or open a pull request.

You are also welcome to **fork the repository and build your own version**, in accordance with the project license.

If you are specifically looking for paid work, please do not feel any obligation to contribute. If paid collaboration becomes available in the future, it will be stated explicitly.

---
*Phát triển bởi Kim-Thu. Sử dụng Whisper, Gemini, Ollama, Edge TTS & FFmpeg.*
