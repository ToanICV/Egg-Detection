"""Serial communication service built on pyserial."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Iterable, Optional

try:
    import serial
except ImportError as exc:  # pragma: no cover - dependency check
    raise ImportError("pyserial package is required for SerialSender. Install via `pip install pyserial`.") from exc

from config.models import SerialConfig
from core.entities import Detection, FrameData

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger("serial.sender")


class SerialSender(QObject):
    """Asynchronous serial sender for detection coordinates."""

    sent = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(bool)

    def __init__(self, config: SerialConfig) -> None:
        super().__init__()
        self._config = config
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=64)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._serial: Optional[serial.Serial] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.debug("Serial sender already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, name="SerialSenderThread", daemon=True)
        self._thread.start()
        logger.info("Serial sender thread started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._close_port()

    def send_detections(self, detections: Iterable[Detection], frame: FrameData) -> None:
        payload = self._format_payload(detections, frame)
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            message = "Serial queue full; payload dropped."
            logger.warning(message)
            self.error_occurred.emit(message)

    def _worker(self) -> None:
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._ensure_port():
                logger.error("Serial port unavailable; retrying in %.2f seconds", reconnect_delay)
                self.error_occurred.emit("Cổng COM không khả dụng. Đang thử lại...")
                time.sleep(reconnect_delay)
                self._requeue_payload(payload)
                continue

            assert self._serial is not None
            try:
                self._serial.write(payload.encode("utf-8"))
                self._serial.flush()
                logger.debug("Sent payload: %s", payload.strip())
                self.sent.emit(payload)
            except serial.SerialException as exc:
                logger.error("Failed to write to serial port: %s", exc)
                self.error_occurred.emit(f"Gửi dữ liệu thất bại: {exc}")
                self._close_port()
                time.sleep(reconnect_delay)
                self._requeue_payload(payload)

    def _requeue_payload(self, payload: str) -> None:
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            message = "Serial queue full; payload dropped."
            logger.warning(message)
            self.error_occurred.emit(message)

    def _ensure_port(self) -> bool:
        if self._serial and self._serial.is_open:
            return True
        try:
            self._serial = serial.Serial(
                port=self._config.port,
                baudrate=self._config.baudrate,
                bytesize=self._config.bytesize,
                parity=self._config.parity,
                stopbits=self._config.stopbits,
                timeout=self._config.timeout,
            )
            logger.info("Serial port %s opened", self._config.port)
            self.status_changed.emit(True)
            return True
        except serial.SerialException as exc:
            logger.error("Unable to open serial port %s: %s", self._config.port, exc)
            self.status_changed.emit(False)
            return False

    def _close_port(self) -> None:
        if self._serial and self._serial.is_open:
            logger.info("Closing serial port %s", self._config.port)
            self._serial.close()
        self._serial = None
        self.status_changed.emit(False)

    def _format_payload(self, detections: Iterable[Detection], frame: FrameData) -> str:
        detections_list = list(detections)
        timestamp = frame.timestamp.isoformat()

        if self._config.payload_format == "csv":
            rows = [
                f"{frame.frame_id},{timestamp},{det.id},{det.label},{det.confidence:.3f},{det.bbox.x1:.1f},{det.bbox.y1:.1f},{det.bbox.x2:.1f},{det.bbox.y2:.1f}"
                for det in detections_list
            ]
            payload = "\n".join(rows) + ("\n" if rows else "")
        else:
            payload_dict = {
                "frame_id": frame.frame_id,
                "timestamp": timestamp,
                "detections": [
                    {
                        "id": det.id,
                        "label": det.label,
                        "confidence": det.confidence,
                        "center": {
                            "x": det.center()[0],
                            "y": det.center()[1],
                        },
                        "bbox": {
                            "x1": det.bbox.x1,
                            "y1": det.bbox.y1,
                            "x2": det.bbox.x2,
                            "y2": det.bbox.y2,
                        },
                    }
                    for det in detections_list
                ],
            }
            payload = json.dumps(payload_dict, separators=(",", ":")) + "\n"
        return payload
