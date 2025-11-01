from __future__ import annotations

import argparse
import queue
import threading
from typing import Optional

import numpy as np

from .capture import CaptureWorker
from .detector import YoloRunner
from .utils import open_source


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLO detection (2-thread) entry point")
    parser.add_argument("--model", type=str, default="Robot-SM/detect/weights/brown-egg.pt", help="Đường dẫn trọng số YOLO (vd: yolov8n.pt, yolov11n.pt)")
    parser.add_argument("--source", type=str, default="0", help="Nguồn video: camera index (0,1,...) hoặc đường dẫn video/ảnh")
    parser.add_argument("--image", action="store_true", help="Nếu đặt, coi source là ảnh tĩnh")
    parser.add_argument("--imgsz", type=int, default=640, help="Kích thước ảnh đầu vào cho YOLO")
    parser.add_argument("--conf", type=float, default=0.25, help="Ngưỡng confidence")
    parser.add_argument("--iou", type=float, default=0.45, help="Ngưỡng IoU")
    parser.add_argument("--device", type=str, default="auto", help="Thiết bị: auto/cpu/0/1 ...")
    parser.add_argument("--max-det", type=int, default=300, help="Số lượng đối tượng tối đa / khung hình")
    parser.add_argument("--half", action="store_true", help="Dùng half precision nếu GPU hỗ trợ")
    parser.add_argument("--class-name", type=str, default=None, help="Chỉ hiển thị lớp có tên này (vd: egg), bỏ qua nếu None")
    parser.add_argument("--window", type=str, default="YOLO Detect", help="Tên cửa sổ hiển thị")
    parser.add_argument("--queue-size", type=int, default=1, help="Kích thước hàng đợi khung hình (nên 1 để giảm trễ)")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    src = open_source(args.source, args.image)

    # Ảnh tĩnh: xử lý một lần bằng YoloRunner trực tiếp
    if isinstance(src, np.ndarray):
        runner = YoloRunner(
            model_path=args.model,
            class_name=args.class_name,
            window_name=args.window,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=args.device,
            max_det=args.max_det,
            half=args.half,
        )
        import cv2

        out = runner.process_once(src)
        cv2.imshow(args.window, out)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        return 0

    # Video/camera: capture thread + infer loop
    frame_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=max(1, args.queue_size))
    stop_event = threading.Event()

    capture = CaptureWorker(source=src, frame_queue=frame_queue, stop_event=stop_event)
    capture.start()

    try:
        runner = YoloRunner(
            model_path=args.model,
            class_name=args.class_name,
            window_name=args.window,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=args.device,
            max_det=args.max_det,
            half=args.half,
        )
        runner.run_loop(frame_queue)
    finally:
        stop_event.set()
        capture.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
