"""Application entrypoint for EggDetection (OpenCV UI)."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from config import Config, load_config
from core.comm import SerialSender
from core.detector import DetectionResult, YoloDetector
from core.entities import Detection, FrameData
from infra import configure_logging, install_exception_hook

logger = logging.getLogger("app.main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Egg detection console interface (cv2).")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/app.yaml"),
        help="Đường dẫn tới file cấu hình YAML/JSON.",
    )
    parser.add_argument(
        "--window",
        type=str,
        default="Egg Detection",
        help="Tên cửa sổ hiển thị OpenCV.",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Chạy ở chế độ headless, không mở cửa sổ OpenCV.",
    )
    return parser.parse_args()


def draw_overlay(frame: np.ndarray, detections: Sequence[Detection]) -> np.ndarray:
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = map(int, (det.bbox.x1, det.bbox.y1, det.bbox.x2, det.bbox.y2))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{det.label} {det.confidence:.2f}"
        cv2.putText(
            annotated,
            label,
            (x1, max(0, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return annotated


def create_frame(frame_id: int, image: np.ndarray, source: str) -> FrameData:
    return FrameData(
        image=image,
        timestamp=datetime.now(timezone.utc),
        frame_id=frame_id,
        source=source,
    )


def bootstrap(config: Config, window_name: str, no_window: bool) -> None:
    install_exception_hook()

    cap = cv2.VideoCapture(config.camera.device_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError(f"Không thể mở camera index {config.camera.device_index}")

    width, height = config.camera.resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, config.camera.fps)
    logger.info("Camera opened at resolution %dx%d", width, height)

    detector = YoloDetector(config.yolo)
    logger.info("Loading YOLO weights...")
    detector.warmup()
    logger.info("YOLO warmup completed.")

    serial_sender = SerialSender(config.serial)
    serial_sender.start()

    display_enabled = not no_window
    if display_enabled:
        try:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, width, height)
        except cv2.error as exc:
            logger.warning("OpenCV GUI unavailable (%s). Falling back to headless mode.", exc)
            display_enabled = False

    frame_id = 0
    fps_counter = 0
    fps_timer = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Không đọc được khung hình từ camera.")
                time.sleep(0.1)
                continue

            frame_id += 1
            fps_counter += 1

            frame_data = create_frame(frame_id, frame, source=f"camera:{config.camera.device_index}")
            result: DetectionResult = detector.detect(frame_data)

            if result.detections:
                serial_sender.send_detections(result.detections, result.frame)

            display_frame = frame
            if config.app.enable_overlay:
                if result.annotated_image is not None:
                    display_frame = result.annotated_image
                else:
                    display_frame = draw_overlay(frame, result.detections)
            if display_enabled:
                cv2.imshow(window_name, display_frame)

            if time.time() - fps_timer >= 5.0:
                fps = fps_counter / (time.time() - fps_timer)
                logger.info("Approx FPS (5s window): %.2f", fps)
                fps_counter = 0
                fps_timer = time.time()

            if display_enabled:
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    logger.info("Exit requested by user input.")
                    break
            else:
                time.sleep(0.001)
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C).")
    finally:
        serial_sender.stop()
        cap.release()
        if display_enabled:
            cv2.destroyAllWindows()
        logger.info("Shutdown complete.")


def main() -> None:
    args = parse_args()
    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Không thể đọc cấu hình: {exc}", file=sys.stderr)
        sys.exit(1)

    configure_logging(config.logging)
    logger.info("Configuration loaded from %s", args.config)
    bootstrap(config, window_name=args.window, no_window=args.no_window)


if __name__ == "__main__":
    main()
