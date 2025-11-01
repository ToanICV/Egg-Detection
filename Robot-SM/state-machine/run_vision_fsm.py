"""
Runner hợp nhất FSM + YOLO:
- Khởi động FSM (StateController + RobotContext phần cứng) và dispatch sự kiện 'eggs_detected' từ YOLO vào FSM.
- Dòng xử lý ảnh hiển thị cửa sổ và vẫn tương thích tham số của YoloRunner.

Cách chạy:
    python -m Robot-SM.state-machine.run_vision_fsm --model yolov8n.pt --source 0 --class-name egg --port COM14 --baud 9600
"""
from __future__ import annotations

import argparse
import queue
import threading
from typing import Optional

import numpy as np

from .controller import StateController, Event
from .context import RobotContext
from . import states as sm_states
from ..detect.detector import YoloRunner
from ..detect.utils import open_source
from ..detect.capture import CaptureWorker


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FSM + YOLO unified runner")
    # YOLO params
    parser.add_argument("--source", type=str, default="0", help="Camera index or video/image path")
    parser.add_argument("--image", action="store_true", help="Treat source as an image")
    parser.add_argument("--half", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    # Init FSM controller first (ctx needs controller reference)
    fsm = StateController(ctx=None)  # type: ignore[arg-type]
    ctx = RobotContext(controller=fsm, port="COM14", baudrate=115200)
    fsm.ctx = ctx

    # Start FSM at Idle -> then send 'start' to begin ScanAndMove
    fsm.start(sm_states.IdleState())

    # Prepare YOLO source
    src = open_source(args.source, args.image)

    # Callback to feed detections into FSM
    def on_detections(det_list):
        # Optional: filter only target class
        if args.class_name:
            det_list = [d for d in det_list if d.get("label") == args.class_name]
        fsm.dispatch(Event(type="eggs_detected", payload=det_list))

    # Video/camera: capture thread + infer loop
    frame_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)
    stop_event = threading.Event()

    capture = CaptureWorker(source=src, frame_queue=frame_queue, stop_event=stop_event)
    capture.start()

    try:
        runner = YoloRunner(
            model_path='Robot-SM/detect/weights/brown-egg.pt',
            class_name=None,
            window_name='YOLO + FSM',
            on_detections=on_detections,
            imgsz=640,
            conf=0.25,
            iou=0.45,
            device='auto',
            max_det=300,
            half=args.half,
        )
        # Start FSM scanning
        print("Starting FSM...")
        fsm.dispatch(Event(type="start"))
        runner.run_loop(frame_queue)
    finally:
        stop_event.set()
        capture.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
