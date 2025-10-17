"""USB camera implementation using OpenCV."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import cv2

from config.models import CameraConfig
from core.entities import FrameData

from .base import CameraBase

logger = logging.getLogger("camera.usb")


class UsbCamera(CameraBase):
    """Camera implementation backed by OpenCV's VideoCapture."""

    def __init__(self, config: CameraConfig) -> None:
        super().__init__()
        self._config = config
        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_id = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.debug("Camera already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="UsbCameraThread", daemon=True)
        self._thread.start()
        self._running = True
        self.started.emit()
        logger.info("USB camera started")

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        self._running = False
        self.stopped.emit()
        logger.info("USB camera stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def close(self) -> None:
        self.stop()
        self._release_capture()

    def _capture_loop(self) -> None:
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0
        logger.debug("Starting capture loop")
        while not self._stop_event.is_set():
            if not self._ensure_capture():
                logger.warning("Unable to open camera. Retrying in %.2f seconds", reconnect_delay)
                self.error_occurred.emit("Không thể kết nối camera. Đang thử lại...")
                time.sleep(reconnect_delay)
                continue

            ret, frame = self._capture.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                self.error_occurred.emit("Đọc khung hình thất bại.")
                self._release_capture()
                time.sleep(0.2)
                continue

            self._frame_id += 1
            frame_data = FrameData(
                image=frame,
                timestamp=datetime.now(timezone.utc),
                frame_id=self._frame_id,
                source=f"camera:{self._config.device_index}",
            )
            self.frame_captured.emit(frame_data)
        logger.debug("Stopping capture loop")

    def _ensure_capture(self) -> bool:
        if self._capture is not None and self._capture.isOpened():
            return True
        return self._open_capture()

    def _open_capture(self) -> bool:
        logger.debug("Opening camera index %s", self._config.device_index)
        capture = cv2.VideoCapture(self._config.device_index, cv2.CAP_DSHOW)

        if not capture.isOpened():
            logger.error("VideoCapture could not be opened for index %s", self._config.device_index)
            capture.release()
            return False

        width, height = self._config.resolution
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, self._config.fps)

        self._capture = capture
        logger.info("Camera connected at resolution %sx%s", width, height)
        return True

    def _release_capture(self) -> None:
        if self._capture is not None:
            logger.debug("Releasing camera resource")
            self._capture.release()
            self._capture = None
