# Robot-SM/detect

Chương trình nhận dạng bằng Ultralytics YOLO (kiến trúc 2 luồng: capture + infer/display).

## Cấu trúc
- `capture.py`: CaptureWorker đọc khung hình từ camera/video trên thread nền, đẩy vào queue (mặc định giữ khung mới nhất).
- `detector.py`: YoloRunner chạy YOLO, vẽ bbox, overlay FPS, hiển thị.
- `utils.py`: Tiện ích `open_source`, `should_quit`.
- `main_cam.py`: Entry point CLI.

## Cách chạy
- Camera:
  - `python -m Robot-SM.detect.main_cam --model yolov8n.pt --source 0`
- Video:
  - `python -m Robot-SM.detect.main_cam --model yolov8n.pt --source path/to/video.mp4`
- Ảnh tĩnh:
  - `python -m Robot-SM.detect.main_cam --model yolov8n.pt --source path/to/image.jpg --image`
- Chỉ hiển thị nhãn cụ thể (ví dụ: `egg`):
  - `python -m Robot-SM.detect.main_cam --model yolov8n.pt --source 0 --class-name egg`

## Tham số quan trọng
- `--imgsz`: kích thước ảnh đầu vào (mặc định 640).
- `--conf`, `--iou`: ngưỡng confidence/IoU.
- `--device`: `auto`/`cpu`/`0`/`1`... để chọn thiết bị.
- `--half`: dùng FP16 nếu GPU hỗ trợ.
- `--queue-size`: kích thước hàng đợi khung hình (nên 1 để giảm độ trễ).

## Ghi chú
- Đã loại bỏ `yolo_cam.py`. Vui lòng sử dụng `main_cam.py`.
- Cài đặt phụ thuộc: `pip install -r requirements.txt`.
