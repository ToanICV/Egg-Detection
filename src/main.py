"""Application entrypoint for EggDetection."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Import detector first to ensure torch DLLs load before PyQt initialization (avoids WinError 1114).
from core.detector import YoloDetector

from PyQt5.QtWidgets import QApplication, QMessageBox

from config import Config, load_config
from core.camera import UsbCamera
from core.comm import SerialSender
from infra import configure_logging, install_exception_hook
from ui import MainWindow, UiController

logger = logging.getLogger("app.main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Egg detection console interface.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/app.yaml"),
        help="Đường dẫn tới file cấu hình YAML/JSON.",
    )
    return parser.parse_args()


def bootstrap(config: Config) -> None:
    app = QApplication(sys.argv)
    install_exception_hook(show_dialog=True)

    camera = UsbCamera(config.camera)
    detector = YoloDetector(config.yolo)
    serial_sender = SerialSender(config.serial)

    try:
        detector.warmup()
    except Exception as exc:
        QMessageBox.critical(None, "Không thể tải mô hình", f"Chi tiết: {exc}")
        raise

    controller = UiController(camera, detector, serial_sender, config)
    window = MainWindow()

    controller.frame_ready.connect(window.display_frame)
    controller.detection_stats.connect(window.update_detection_stats)
    controller.serial_status.connect(window.update_serial_status)
    controller.log_message.connect(window.append_log)
    controller.status_message.connect(window.show_status_message)
    controller.error_occurred.connect(window.append_log)

    window.start_requested.connect(controller.start)
    window.stop_requested.connect(controller.stop)
    window.overlay_toggled.connect(window.video_widget.set_overlay_enabled)

    app.aboutToQuit.connect(controller.shutdown)

    window.set_overlay_state(config.app.enable_overlay)

    window.show()

    if config.app.auto_start:
        controller.start()

    logger.info("GUI initialized. Entering event loop.")
    sys.exit(app.exec_())


def main() -> None:
    args = parse_args()
    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Không thể đọc cấu hình: {exc}", file=sys.stderr)
        sys.exit(1)

    configure_logging(config.logging)
    logger.info("Configuration loaded from %s", args.config)
    bootstrap(config)


if __name__ == "__main__":
    main()
