from __future__ import annotations

import threading
import queue
from typing import Optional, Union

import cv2
import numpy as np


class CaptureWorker:
    """Luồng chỉ chuyên đọc khung hình và đẩy vào queue (chỉ giữ khung mới nhất).

    - source: camera index (int) hoặc đường dẫn video (str)
    - frame_queue: hàng đợi đầu ra (nên size=1 để giảm latency)
    - stop_event: sự kiện dừng thread an toàn
    """

    def __init__(self, source: Union[int, str], frame_queue: "queue.Queue[np.ndarray]", stop_event: threading.Event) -> None:
        self._source = source
        self._frame_queue = frame_queue
        self._stop_event = stop_event
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="CaptureWorker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        if self._cap is not None:
            self._cap.release()
        self._cap = None

    def _open_capture(self) -> bool:
        cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            return False
        # Giảm buffer nội bộ của OpenCV để giảm trễ
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        return True

    def _run(self) -> None:
        retry_delay = 0.5
        while not self._stop_event.is_set():
            if self._cap is None:
                if not self._open_capture():
                    if self._stop_event.wait(retry_delay):
                        break
                    continue

            assert self._cap is not None
            ok, frame = self._cap.read()
            if not ok or frame is None:
                # Thử mở lại
                self._cap.release()
                self._cap = None
                continue

            # Giữ khung mới nhất – nếu queue đầy, bỏ khung cũ
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass
