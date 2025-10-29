"""Application entrypoint for EggDetection (OpenCV UI)."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Tuple

import cv2
import numpy as np

from config import Config, load_config
from core.detector import DetectionResult, YoloDetector
from core.entities import Detection, FrameData
from infra import configure_logging, install_exception_hook
from serial_io import ActorLink, ArmLink, SharedSerialBus
from services import CommandScheduler, DetectionEvent, EventBus, FrameSource, StaticImageSource, VideoCaptureSource
from state_machine import ControlContext, ControlEngine

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


def compute_roi_pixels(config_roi, frame_width: int, frame_height: int) -> Tuple[int, int, int, int]:
    top_left_ratio, bottom_right_ratio = config_roi.as_tuple()
    x1 = int(round(top_left_ratio[0] * frame_width))
    y1 = int(round(top_left_ratio[1] * frame_height))
    x2 = int(round(bottom_right_ratio[0] * frame_width))
    y2 = int(round(bottom_right_ratio[1] * frame_height))

    x1 = max(0, min(frame_width - 1, x1))
    y1 = max(0, min(frame_height - 1, y1))
    x2 = max(0, min(frame_width - 1, x2))
    y2 = max(0, min(frame_height - 1, y2))

    if x1 >= x2 or y1 >= y2:
        logger.warning("ROI configuration invalid after conversion; falling back to full frame.")
        return 0, 0, frame_width - 1, frame_height - 1

    logger.info("ROI active: top-left=(%d,%d), bottom-right=(%d,%d)", x1, y1, x2, y2)
    return x1, y1, x2, y2


def filter_detections_in_roi(
    detections: Sequence[Detection],
    roi: Tuple[int, int, int, int],
) -> list[Detection]:
    x1, y1, x2, y2 = roi
    filtered: list[Detection] = []
    for det in detections:
        cx, cy = det.center()
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            filtered.append(det)
    return filtered


def bootstrap(config: Config, window_name: str, no_window: bool) -> None:
    install_exception_hook()

    width, height = config.camera.resolution

    frame_source, source_label = _initialize_frame_source(config, width, height)
    frame_source.start()
    logger.info("Frame source started for %s", source_label)

    detector = YoloDetector(config.yolo)
    logger.info("Loading YOLO weights...")
    detector.warmup()
    logger.info("YOLO warmup completed.")

    event_bus = EventBus()
    scheduler = CommandScheduler(event_bus)

    bus_registry: dict[str, SharedSerialBus] = {}

    def _get_bus(link_cfg) -> SharedSerialBus:
        bus = bus_registry.get(link_cfg.port)
        if bus is None:
            bus = SharedSerialBus(link_cfg)
            bus_registry[link_cfg.port] = bus
        return bus

    actor_bus = _get_bus(config.control.serial.actor)
    arm_bus = _get_bus(config.control.serial.arm)

    actor_link = ActorLink(actor_bus, config.control.serial.actor)
    arm_link = ArmLink(arm_bus, config.control.serial.arm)
    control_context = ControlContext(
        actor=actor_link,
        arm=arm_link,
        scheduler=scheduler,
        bus=event_bus,
        config=config.control,
    )
    engine = ControlEngine(control_context, event_bus)

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
    roi_pixels: Tuple[int, int, int, int] | None = None

    # Fix for cv2.imshow lag: start engine asynchronously
    engine_started = False
    engine_startup_attempted = False
    
    try:
        while True:
            success, frame = frame_source.read(timeout_s=1.0)
            if not success or frame is None:
                logger.warning("Frame source timeout; no frame received.")
                if display_enabled:
                    cv2.waitKey(1)
                time.sleep(0.05)
                continue

            frame_id += 1
            fps_counter += 1

            # Start engine asynchronously after first few frames to avoid blocking cv2.imshow
            if not engine_startup_attempted and frame_id > 3:
                def start_engine_async():
                    nonlocal engine_started
                    try:
                        logger.info("Starting control engine asynchronously...")
                        engine.start()
                        engine_started = True
                        logger.info("Control engine started successfully.")
                    except Exception as e:
                        logger.error("Failed to start control engine: %s", e)
                
                threading.Thread(target=start_engine_async, daemon=True).start()
                engine_startup_attempted = True

            if roi_pixels is None:
                frame_height, frame_width = frame.shape[:2]
                logger.info("Input frame size: %dx%d", frame_width, frame_height)
                roi_pixels = compute_roi_pixels(config.app.roi, frame_width, frame_height)
                if display_enabled:
                    cv2.resizeWindow(window_name, frame_width, frame_height)

            frame_data = create_frame(frame_id, frame, source=source_label)
            result: DetectionResult = detector.detect(frame_data)
            active_detections = (
                filter_detections_in_roi(result.detections, roi_pixels) if roi_pixels else list(result.detections)
            )

            # Only publish events if engine is started
            if engine_started:
                event_bus.publish(DetectionEvent(detections=active_detections, frame=result.frame))

            display_frame = frame.copy()
            if config.app.enable_overlay:
                display_frame = draw_overlay(display_frame, active_detections)
            if roi_pixels:
                cv2.rectangle(
                    display_frame,
                    (roi_pixels[0], roi_pixels[1]),
                    (roi_pixels[2], roi_pixels[3]),
                    (0, 255, 255),
                    2,
                )
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
        if engine_started:
            engine.stop()
        for bus in bus_registry.values():
            bus.shutdown()
        frame_source.stop()
        if display_enabled:
            cv2.destroyAllWindows()
        logger.info("Shutdown complete.")


def _initialize_frame_source(config: Config, width: int, height: int) -> tuple[FrameSource, str]:
    device = config.camera.device_index
    if isinstance(device, str):
        path = Path(device)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"} and path.exists():
            return StaticImageSource(path), f"image:{path}"
        try:
            device = int(device)
        except ValueError:
            pass
    source = VideoCaptureSource(device, width, height, config.camera.fps)
    return source, f"camera:{device}"


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










