"""Thành phần lấy khung hình phục vụ pipeline nhận diện."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

import logging

logger = logging.getLogger("services.frame_source")


class FrameSource:
    """Giao diện trừu tượng cho mọi nguồn cấp khung hình."""

    def start(self) -> None:
        """Bắt đầu thu nhận dữ liệu hình ảnh."""
        raise NotImplementedError

    def read(self, timeout_s: float = 1.0) -> tuple[bool, Optional[np.ndarray]]:
        """Đọc khung hình tiếp theo với thời gian chờ tùy chọn."""
        raise NotImplementedError

    def stop(self) -> None:
        """Dừng nguồn và giải phóng tài nguyên."""
        raise NotImplementedError


class VideoCaptureSource(FrameSource):
    """Đọc khung hình từ cv2.VideoCapture trên thread nền tránh block giao diện."""

    def __init__(
        self,
        device: Union[int, str],
        width: int,
        height: int,
        fps: int,
        reopen_delay_s: float = 1.0,
    ) -> None:
        """Khởi tạo nguồn camera với thiết bị, độ phân giải và FPS mong muốn."""
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._reopen_delay_s = reopen_delay_s
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=1)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cap: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        """Khởi động thread đọc camera nếu chưa chạy."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="FrameSourceReader", daemon=True)
        self._thread.start()

    def read(self, timeout_s: float = 1.0) -> tuple[bool, Optional[np.ndarray]]:
        """Trả về khung hình mới nhất đã được thread nền thu thập."""
        try:
            frame = self._queue.get(timeout=timeout_s)
            return True, frame
        except queue.Empty:
            return False, None

    def stop(self) -> None:
        """Dừng thread nền và đóng thiết bị camera."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        if self._cap is not None:
            self._cap.release()
        self._cap = None

    # Internal -----------------------------------------------------------------

    def _open_capture(self) -> bool:
        """Mở lại thiết bị camera và thiết lập thông số mong muốn."""
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            logger.error("Unable to open video source %s", self._device)
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_FPS, self._fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        logger.info("FrameSource connected to %s", self._device)
        return True

    def _run(self) -> None:
        """Vòng lặp nền liên tục đọc khung hình và đẩy vào hàng đợi."""
        retry_delay = self._reopen_delay_s
        while not self._stop_event.is_set():
            if self._cap is None:
                if not self._open_capture():
                    if self._stop_event.wait(retry_delay):
                        break
                    continue

            assert self._cap is not None
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.warning("FrameSource: failed to read frame; attempting reopen.")
                self._cap.release()
                self._cap = None
                continue

            if not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put(frame)


class StaticImageSource(FrameSource):
    """Nguồn khung hình cố định phát lặp lại một ảnh duy nhất."""

    def __init__(self, image_path: Path) -> None:
        """Nhận đường dẫn ảnh tĩnh dùng làm nguồn phát lặp lại."""
        self._image_path = image_path
        self._frame: Optional[np.ndarray] = None

    def start(self) -> None:
        """Nạp ảnh tĩnh từ đĩa vào bộ nhớ."""
        frame = cv2.imread(str(self._image_path))
        if frame is None:
            raise FileNotFoundError(f"Unable to load image at {self._image_path}")
        self._frame = frame
        logger.info("StaticImageSource loaded image %s", self._image_path)

    def read(self, timeout_s: float = 1.0) -> tuple[bool, Optional[np.ndarray]]:
        """Trả về bản sao của ảnh đã nạp để tương thích với giao diện FrameSource."""
        if self._frame is None:
            return False, None
        return True, self._frame.copy()

    def stop(self) -> None:
        """Giải phóng bộ nhớ chứa ảnh tĩnh."""
        self._frame = None


