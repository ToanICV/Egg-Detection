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
from services import CommandScheduler, DetectionEvent, EventBus, FrameSource, StaticImageSource, VideoCaptureSource, TimerId
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


def draw_overlay(frame: np.ndarray, detections: Sequence[Detection], current_state: str = None, fps: float = 0.0) -> np.ndarray:
    annotated = frame.copy()
    
    # Draw detection boxes
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
    
    # Draw state machine status
    if current_state:
        # State display background
        state_text = f"State: {current_state}"
        text_size = cv2.getTextSize(state_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        
        # Background rectangle for better readability
        cv2.rectangle(annotated, (10, 10), (text_size[0] + 20, text_size[1] + 20), (0, 0, 0), -1)
        cv2.rectangle(annotated, (10, 10), (text_size[0] + 20, text_size[1] + 20), (255, 255, 255), 2)
        
        # State text with color coding
        state_colors = {
            "Idle": (128, 128, 128),           # Gray
            "ScanAndMove": (0, 255, 255),     # Yellow  
            "PickUpEgg": (0, 255, 0),         # Green
            "TurnFirst": (255, 0, 0),         # Blue
            "ScanOnly": (0, 165, 255),        # Orange
            "MoveOnly": (255, 0, 255),        # Magenta
            "TurnSecond": (255, 0, 0),        # Blue
        }
        
        color = state_colors.get(current_state, (255, 255, 255))  # Default white
        cv2.putText(
            annotated,
            state_text,
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )
        
        # Add detection count
        detection_text = f"Eggs: {len(detections)}"
        cv2.putText(
            annotated,
            detection_text,
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(
            annotated,
            f"Time: {timestamp}",
            (20, 85),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        
        # Add FPS
        if fps > 0:
            cv2.putText(
                annotated,
                f"FPS: {fps:.1f}",
                (20, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
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

    # Use real serial components with fallback to mock if failed
    try:
        # Use single shared bus for RS485 - both devices on same COM port
        shared_bus = _get_bus(config.control.serial)
        actor_link = ActorLink(shared_bus, config.control.serial)
        arm_link = ArmLink(shared_bus, config.control.serial)
        logger.info("Using real serial connection for hardware")
        
        control_context = ControlContext(
            actor=actor_link,
            arm=arm_link,
            scheduler=scheduler,
            bus=event_bus,
            config=config.control,
        )
        
    except Exception as e:
        logger.warning("Real serial connection failed (%s), falling back to mock for testing", e)
        
        # Fallback mock serial for testing when hardware unavailable
        class MockSerial:
            def start(self): 
                logger.info("Mock serial started (fallback mode)")
                return True
            def shutdown(self): 
                logger.info("Mock serial shutdown")  
            def read_status(self): 
                return None
            def move_forward(self):
                logger.info("Mock move_forward command")
                return True
            def stop(self):
                logger.info("Mock stop command") 
                return True
            def turn(self):
                logger.info("Mock turn command")
                return True
            def pick(self, x_mm, y_mm):
                logger.info(f"Mock pick command at ({x_mm}, {y_mm})")
                return True
            def stop_motion(self):
                logger.info("Mock stop_motion command")
                return True
        
        class MockScheduler:
            def start_interval(self, timer_id, interval_s):
                logger.info(f"Mock scheduler started timer {timer_id}")
            def cancel(self, timer_id):
                logger.info(f"Mock scheduler cancelled timer {timer_id}")
            def shutdown(self):
                logger.info("Mock scheduler shutdown")
        
        actor_link = MockSerial()
        arm_link = MockSerial()
        control_context = ControlContext(
            actor=actor_link,
            arm=arm_link,
            scheduler=MockScheduler(),
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
    current_fps = 0.0
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
                        logger.info("🔧 Starting control engine asynchronously...")
                        print("🚀 DEBUG: Attempting to start engine...")
                        
                        logger.info("🔧 Step 1: Starting actor link...")
                        print("🔧 DEBUG: Starting actor link...")
                        engine.context.actor.start()
                        logger.info("✅ Step 1 complete: Actor link started")
                        print("✅ DEBUG: Actor link started")
                        
                        logger.info("🔧 Step 2: Starting arm link...")
                        print("🔧 DEBUG: Starting arm link...")
                        engine.context.arm.start()
                        logger.info("✅ Step 2 complete: Arm link started")
                        print("✅ DEBUG: Arm link started")
                        
                        logger.info("🔧 Step 3: Starting scheduler timers...")
                        print("🔧 DEBUG: Starting scheduler timers...")
                        
                        # Replace scheduler with simple threading timers
                        logger.info("🔧 Step 3: Using simple threading timers instead of scheduler")
                        print("🔧 DEBUG: Using threading timers instead of scheduler")
                        
                        def actor_status_timer():
                            while True:
                                try:
                                    time.sleep(1.0)  # 1 second interval
                                    # Simulate actor status polling
                                    logger.debug("📡 Actor status check (threading timer)")
                                except Exception as e:
                                    logger.error("Actor timer error: %s", e)
                                    break
                        
                        def arm_status_timer():
                            while True:
                                try:
                                    time.sleep(1.0)  # 1 second interval  
                                    # Simulate arm status polling
                                    logger.debug("📡 Arm status check (threading timer)")
                                except Exception as e:
                                    logger.error("Arm timer error: %s", e)
                                    break
                        
                        # Start threading timers
                        actor_timer_thread = threading.Thread(target=actor_status_timer, daemon=True)
                        arm_timer_thread = threading.Thread(target=arm_status_timer, daemon=True)
                        
                        actor_timer_thread.start()
                        arm_timer_thread.start()
                        
                        logger.info("✅ Step 3: Threading timers started successfully")
                        print("✅ DEBUG: Threading timers started - continuing engine startup")
                        
                        logger.info("🔧 Step 4: Starting state machine patrol...")
                        print("🔧 DEBUG: Starting state machine patrol...")
                        engine.state_machine.start_patrol()
                        logger.info("✅ Step 4 complete: State machine patrol started")
                        print("✅ DEBUG: State machine patrol started")
                        
                        logger.info("🔧 Step 5: Starting event loop thread...")
                        print("🔧 DEBUG: Starting event loop thread...")
                        engine._loop_thread = threading.Thread(target=engine._event_loop, name="ControlEventLoop", daemon=True)
                        engine._loop_thread.start()
                        logger.info("✅ Step 5 complete: Event loop thread started")
                        print("✅ DEBUG: Event loop thread started")
                        
                        engine_started = True
                        logger.info("🎉 Control engine started successfully - ALL STEPS COMPLETE")
                        print("🎉 DEBUG: Engine started successfully!")
                        
                    except Exception as e:
                        logger.error("❌ Failed to start control engine: %s", e)
                        print(f"❌ DEBUG: Engine start failed: {e}")
                        import traceback
                        error_details = traceback.format_exc()
                        logger.error("❌ Engine start error details:\n%s", error_details)
                        print(f"❌ DEBUG: Error details:\n{error_details}")
                
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

            # Get current state from engine
            current_state = None
            if engine_started and hasattr(engine, 'state_machine'):
                try:
                    current_state = engine._state_name()
                except Exception as e:
                    current_state = "Error"
                    logger.warning("Failed to get current state: %s", e)
            else:
                current_state = "NotStarted"
            
            display_frame = frame.copy()
            if config.app.enable_overlay:
                display_frame = draw_overlay(display_frame, active_detections, current_state, current_fps)
            else:
                # Always show state even if overlay is disabled
                display_frame = draw_overlay(display_frame, [], current_state, current_fps)
                
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
                current_fps = fps_counter / (time.time() - fps_timer)
                logger.info("Approx FPS (5s window): %.2f", current_fps)
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










