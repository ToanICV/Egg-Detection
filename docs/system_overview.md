# System Overview (OpenCV Edition)

This document describes the architecture and runtime flow of the egg detection application after replacing the PyQt5 UI with an OpenCV window.

## 1. Architecture Layers

- **Application (`src/main.py`)** – Loads configuration, prepares logging/exception hooks, starts the camera loop, runs YOLO inference, displays frames, and pushes detection coordinates to the serial line.
- **Config (`src/config/`)** – Dataclasses that hold strongly-typed configuration plus a YAML/JSON loader that normalises relative paths.
- **Infra (`src/infra/`)** – Logging setup (`logging.py`) and a lightweight global exception hook (`exceptions.py`) that just logs fatal errors.
- **Core (`src/core/`)**
  - `detector/`: `YoloDetector` (Ultralytics YOLOv11) returning `DetectionResult` objects that include bounding boxes and optional annotated frames.
  - `comm/serial_sender.py`: Background thread that serialises detections to JSON/CSV and writes them to a COM port with automatic retry.
  - `entities/`: Common data containers (`FrameData`, `Detection`, `BoundingBox`).

All PyQt dependencies have been removed; OpenCV handles the window and keyboard events.

## 2. Runtime Flow

1. Read configuration from `config/app.yaml`, configure logging, install the exception hook.
2. Open the USB camera through `cv2.VideoCapture`, apply resolution/FPS if the device supports it.
3. Load the YOLO model once via `YoloDetector.warmup`.
4. Start the `SerialSender` thread to keep the COM port alive.
5. **Main loop**
   - Capture a frame; if capture fails, log and retry.
   - Wrap the frame in `FrameData` (UTC timestamp, running `frame_id`, source tag).
   - Call `detector.detect(frame_data)` to obtain `DetectionResult`.
   - When detections exist, queue them for serial transmission.
   - Pick the frame to show: use the model’s annotated frame if available, otherwise draw the boxes locally with OpenCV.
   - Display via `cv2.imshow` (if GUI support is available); compute a rolling FPS metric every 5 seconds.
   - Leave the loop when the user presses `Esc` or `q`, or on `Ctrl+C`.
6. Shut down gracefully: stop the serial thread, release the camera, destroy the OpenCV window (if it was opened).

## 3. Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `src/main.py` | Sequential capture → inference → display loop, serial delivery, FPS logging. |
| `config/models.py` | Dataclasses for camera, detector, serial, logging, and app display toggles. |
| `config/loader.py` | Reads YAML/JSON, expands relative paths for weights/logs, instantiates dataclasses. |
| `core/detector/yolo_detector.py` | Wraps Ultralytics YOLO, parses detections, builds annotated frames. |
| `core/comm/serial_sender.py` | Queued writer to the COM port with reconnect and backoff logic. |
| `core/entities` | Shared domain objects (`FrameData`, `Detection`, `BoundingBox`). |
| `infra/logging.py` | Configurable console + rotating file logging. |
| `infra/exceptions.py` | Logs uncaught exceptions from main and worker threads. |

## 4. Data Pipeline

```text
cv2.VideoCapture -- FrameData --> YoloDetector.detect
                                      |
                                      +--> SerialSender (COM payload)
                                      |
                                 annotated frame / draw_overlay
                                      |
                                 cv2.imshow window
```

- **Input**: `numpy.ndarray` in BGR format.
- **Processing**: YOLO returns bounding boxes with class IDs and confidences. When the model does not produce an annotated frame, the application draws rectangles and labels itself.
- **Output**: Live OpenCV window plus serial payload (JSON or CSV lines) for downstream hardware.

## 5. Sample Configuration (`config/app.yaml`)

```yaml
camera:
  device_index: 0
  resolution: [640, 480]
  fps: 25
  reconnect_delay_ms: 2000

yolo:
  weights_path: "../weights/brown-egg.pt"
  confidence_threshold: 0.4
  iou_threshold: 0.5
  device: "cpu"
  max_det: 50

serial:
  port: "COM15"
  baudrate: 115200
  payload_format: "json"
  reconnect_delay_ms: 2000

logging:
  level: "INFO"
  filepath: "../logs/app.log"
  max_bytes: 5242880
  backup_count: 5
  console: true

app:
  enable_overlay: true
```

## 6. Operating Notes

- Run `python src/main.py --config config/app.yaml`; press `q` or `Esc` to exit (when a window is shown).
- Use `--no-window` if OpenCV was built without GUI backends or you are running headless; the pipeline still executes and serial payloads are produced.
- When GUI support is missing, the program automatically falls back to headless mode and logs a warning.
- Serial status and errors are logged under the `serial.sender` namespace. Check `logs/app.log` to confirm port activity.
- If the frame rate is too low, consider lowering the camera resolution, switching to a lighter YOLO model, or turning off overlay (`enable_overlay=false`).

## 7. Future Extensions

- Split capture/inference into separate processes communicating over a queue to exploit concurrency on multi-core systems.
- Add optional recording of annotated frames or video clips when detections occur.
- Provide HTTP/WebSocket output beside COM payloads.
- Instrument detailed latency metrics (capture time, inference time, serial throughput).
