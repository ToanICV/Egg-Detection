# Tổng Quan Hệ Thống Nhận Dạng Trứng

Tài liệu này mô tả kiến trúc, các mô-đun chính và luồng xử lý của ứng dụng nhận dạng trứng sử dụng PyQt5 và mô hình YOLOv11 (Ultralytics). Mục tiêu của kiến trúc là tách biệt rõ ràng từng trách nhiệm để dễ dàng bảo trì, mở rộng và thử nghiệm.

## 1. Kiến Trúc Tổng Thể

Ứng dụng được chia thành các tầng chính:

- **Main/Application Layer (`src/main.py`)**: Điểm vào của chương trình, khởi tạo cấu hình, logging, exception hook và dây nối (dependency wiring) giữa các mô-đun.
- **Config Layer (`src/config/`)**: Đọc file cấu hình (YAML/JSON) để xác định tham số camera, YOLO, serial, logging.
- **Infrastructure Layer (`src/infra/`)**:
  - `logging.py`: Thiết lập logging (console + file, rotating, format thống nhất).
  - `exceptions.py`: Định nghĩa global exception hook, ghi log và hiển thị thông báo lỗi (PyQt dialog khi cần).
- **Domain/Core Layer (`src/core/`)**:
  - `camera/`: Interface camera và triển khai USB camera.
  - `detector/`: Interface detector và triển khai YOLOv11 sử dụng Ultralytics.
  - `comm/`: Giao tiếp serial (pyserial) để gửi tọa độ.
  - `entities/`: Định nghĩa data class `Detection`, các cấu trúc dữ liệu dùng chung.
- **UI Layer (`src/ui/`)**:
  - `main_window.py`: Giao diện chính, hiển thị video và bounding box.
  - `controller.py`: Trung tâm điều phối signal giữa camera, detector, serial và UI.
  - `widgets/`: Các widget tùy chỉnh (ví dụ `VideoWidget` để render frame + overlay).

Các mô-đun giao tiếp với nhau thông qua interface rõ ràng, giảm phụ thuộc trực tiếp và giúp mock trong unit test.

## 2. Luồng Hoạt Động Chính

### 2.1 Khởi Động Ứng Dụng
1. `main.py` đọc cấu hình hệ thống.
2. Khởi tạo logging theo cấu hình (mức độ log, file path).
3. Thiết lập global exception hook để bắt toàn bộ lỗi không xử lý.
4. Khởi tạo `QApplication` và các service cốt lõi: `CameraService`, `YoloDetector`, `SerialSender`, `UiController`.
5. `UiController` gắn kết signal/slot, hiển thị `MainWindow` và bắt đầu chu trình đọc camera (khi người dùng nhấn Start hoặc auto-start tùy cấu hình).

### 2.2 Chu Trình Nhận Dạng Trứng
1. **Camera Thread**
   - `UsbCamera` mở camera USB (OpenCV `VideoCapture`) theo cấu hình (độ phân giải, FPS).
   - Một thread riêng đọc frame liên tục và push vào queue hoặc emit signal `frameCaptured`.
   - Nếu camera mất kết nối, camera retry theo chu kỳ và ghi log cảnh báo.
2. **Detection Worker**
   - `UiController` nhận signal frame và chuyển sang worker thread xử lý YOLO (tránh block UI).
   - `YoloDetector` chạy inference trên frame, trả về danh sách `Detection` (bbox, độ tin cậy, tọa độ tâm).
   - Tùy cấu hình, có thể bỏ qua frame (frame skipping) để cân bằng tốc độ vs. latency.
3. **UI Rendering**
   - `MainWindow` nhận frame gốc và danh sách detection, vẽ overlay bounding box bằng `QPainter`.
   - Cập nhật các widget trạng thái (số lượng trứng, FPS, thiết bị kết nối).
4. **Serial Output**
   - `UiController` chuyển đổi danh sách detection thành payload (JSON hoặc CSV).
   - `SerialSender` gửi payload qua COM port cấu hình, kèm theo timestamp hoặc ID frame.
   - Nếu gửi thất bại (port bận/mất kết nối), `SerialSender` log lỗi và cố gắng reconnect với backoff.

### 2.3 Logging & Giám Sát
- Mỗi mô-đun log với namespace riêng (`camera`, `detector`, `serial`, `ui`).
- Logging mức `DEBUG` dùng trong phát triển, `INFO`/`WARNING` trong môi trường triển khai.
- Có thể thêm `QtLogHandler` để hiển thị log mới nhất trong UI (ví dụ panel trạng thái).

### 2.4 Xử Lý Ngoại Lệ
- Global `ExceptionHook` ghi log `CRITICAL`, hiển thị dialog thân thiện (khi chạy UI).
- Các thread background chuyển exception về main thread bằng signal `errorOccurred`.
- Các lỗi phổ biến (không mở được camera, fail load model, COM port bận) được catch cụ thể để show hướng dẫn khắc phục.

## 3. Chi Tiết Mô-đun

| Mô-đun | Trách nhiệm chính | Ghi chú |
| --- | --- | --- |
| `CameraConfig`, `YoloConfig`, `SerialConfig` | Đóng gói thông tin cấu hình, dùng dataclass bất biến | Cho phép validate tham số ngay khi load |
| `UsbCamera` | Điều khiển thiết bị camera USB, quản lý thread đọc frame | Hỗ trợ reconnect, emit signal PyQt (`frameCaptured`) |
| `YoloDetector` | Load weights YOLOv11 từ `weights/`, chạy inference | Cho phép chọn device: CPU/GPU; cấu hình confidence, IoU |
| `SerialSender` | Mở COM port, định dạng payload, gửi dữ liệu | Sử dụng queue để không block UI, có cơ chế retry |
| `UiController` | Kết nối các service, điều phối start/stop, nhận signal lỗi | Là lớp Application Service chính |
| `MainWindow` & `VideoWidget` | Render giao diện, overlay bounding box, hiển thị log | Hỗ trợ toggle hiển thị thông tin detection |

## 4. Luồng Dữ Liệu Chi Tiết

```text
Camera Thread -> Frame Queue -> Detection Worker -> UI Render
                                  |
                                  V
                           SerialSender Queue -> COM Port
```

- **Input**: Frame từ camera USB (BGR `numpy.ndarray`).
- **Processing**:
  - Tiền xử lý (nếu cần): resize, normalize.
  - YOLO inference trả về bounding box (x1, y1, x2, y2), độ tin cậy.
  - Chuyển đổi tọa độ sang trung tâm (x_center, y_center) và chuẩn hóa theo kích thước frame nếu thiết bị cần.
- **Output**: Payload (JSON/CSV) chứa ID quả trứng, tọa độ, độ tin cậy; được gửi tuần tự theo mỗi frame hoặc theo batch.

## 5. Cấu Hình & Tham Số

Ví dụ cấu hình YAML:

```yaml
camera:
  device_index: 0
  resolution: [1280, 720]
  fps: 30
  reconnect_delay_ms: 2000

yolo:
  weights_path: "weights/egg_detector.pt"
  confidence_threshold: 0.4
  iou_threshold: 0.5
  device: "cuda"  # hoặc "cpu"

serial:
  port: "COM3"
  baudrate: 115200
  payload_format: "json"  # hoặc "csv"

app:
  auto_start: true
  ui_language: "vi"
```

## 6. Kiểm Thử & Giám Sát

- **Unit test** cho từng mô-đun core (`camera`, `detector`, `serial`) bằng mock.
- **Integration test**: script nhỏ chạy pipeline trên video mẫu hoặc camera ảo.
- **Monitoring runtime**: log file, UI status panel, có thể thêm metric đơn giản (FPS, latency).

## 7. Hướng Mở Rộng

- Hỗ trợ nhiều camera hoặc nhiều model detector.
- Thêm module tracking (ID quả trứng giữa các frame).
- Thêm REST API hoặc WebSocket để truyền dữ liệu thay vì COM port.
- Bổ sung dashboard hiển thị thống kê (số trứng/phút, phân loại theo kích thước).

---

Tài liệu này sẽ được cập nhật khi có thay đổi lớn trong kiến trúc hoặc yêu cầu hệ thống.
