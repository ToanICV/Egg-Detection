from __future__ import annotations

import queue
import time
from typing import Optional

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    raise ImportError("Ultralytics package is required. Install with `pip install ultralytics`.")


class YoloRunner:
    """Chạy YOLO trên khung hình lấy từ frame_queue và hiển thị kết quả.

    Tham số:
    - model_path: đường dẫn/định danh model YOLO
    - class_name: nếu đặt, chỉ vẽ các bbox có nhãn trùng tên này
    - window_name: tên cửa sổ hiển thị
    - on_detections: callback(list[dict]) nhận danh sách phát hiện mỗi khung hình
    - yolo_params: dict các tham số (imgsz, conf, iou, device, max_det, half)
    """

    def __init__(self, model_path: str, class_name: Optional[str], window_name: str,
                 on_detections: Optional[callable] = None, **yolo_params) -> None:
        # Chuẩn hóa device và half để tránh lỗi khi không có CUDA
        import torch

        device = yolo_params.get("device", "auto")
        if isinstance(device, str):
            dev_lower = device.lower()
        else:
            dev_lower = device

        use_cuda = torch.cuda.is_available()
        # 'auto' hoặc None -> nếu không có CUDA thì về 'cpu'
        if dev_lower in (None, "auto"):
            yolo_params["device"] = "cuda:0" if use_cuda else "cpu"
        # Nếu người dùng chỉ định GPU nhưng không có CUDA thì fallback CPU
        elif isinstance(dev_lower, str) and dev_lower not in ("cpu",) and not use_cuda:
            yolo_params["device"] = "cpu"

        # Nếu đang chạy CPU thì tắt half để tránh lỗi
        if str(yolo_params.get("device")).startswith("cpu"):
            if yolo_params.get("half", False):
                yolo_params["half"] = False

        self._model = YOLO(model_path)
        self._names = getattr(self._model, "names", None)
        self._class_name = class_name
        self._window = window_name
        self._on_detections = on_detections
        self._params = yolo_params
        self._fps_avg: Optional[float] = None

    def process_once(self, frame: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        results = self._model.predict(source=frame, verbose=False, **self._params)
        result = results[0]
        canvas = result.plot()

        # Chuẩn bị danh sách phát hiện dạng chuẩn cho FSM
        det_list = []
        if hasattr(result, "boxes") and result.boxes is not None:
            boxes = result.boxes
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            classes = boxes.cls.cpu().numpy().astype(int)
            h, w = frame.shape[:2]
            for (x1, y1, x2, y2), conf, cls_id in zip(xyxy, confs, classes):
                if isinstance(self._names, dict):
                    label = self._names.get(cls_id, f"class_{cls_id}")
                else:
                    label = str(cls_id)
                # Lọc theo class_name nếu chỉ định
                if self._class_name is not None and label != self._class_name:
                    continue
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                det_list.append({
                    "label": label,
                    "conf": float(conf),
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    "x_px": float(cx),
                    "y_px": float(cy),
                    "x_norm": float(cx / max(1.0, w)),
                    "y_norm": float(cy / max(1.0, h)),
                })

        # Nếu có callback detections, gọi để phát sự kiện cho FSM
        if self._on_detections is not None:
            try:
                self._on_detections(det_list)
            except Exception:
                pass

        # Vẽ lại nếu cần lọc theo class_name
        if self._class_name is not None and hasattr(result, "boxes") and result.boxes is not None:
            filtered = canvas.copy()
            for det in det_list:
                x1, y1, x2, y2 = det["bbox"]
                label = det["label"]
                conf = det["conf"]
                cv2.rectangle(filtered, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(filtered, f"{label} {conf:.2f}", (int(x1), max(0, int(y1) - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
            canvas = filtered

        dt = time.perf_counter() - t0
        fps = 1.0 / dt if dt > 0 else 0.0
        self._fps_avg = fps if self._fps_avg is None else self._fps_avg * 0.9 + fps * 0.1
        cv2.putText(canvas, f"FPS: {self._fps_avg:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (50, 220, 50), 2, cv2.LINE_AA)
        return canvas

    def run_loop(self, frame_queue: "queue.Queue[np.ndarray]") -> None:
        while True:
            try:
                frame = frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            canvas = self.process_once(frame)
            cv2.imshow(self._window, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
        cv2.destroyAllWindows()
