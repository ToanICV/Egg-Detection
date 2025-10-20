"""Serial communication service built on pyserial."""

from __future__ import annotations

import json
import logging
import queue
import struct
import threading
import time
from typing import Callable, Iterable, Optional, Sequence

try:
    import serial
except ImportError as exc:  # pragma: no cover - dependency check
    raise ImportError("pyserial package is required for SerialSender. Install via `pip install pyserial`.") from exc

from config.models import SerialConfig
from core.entities import Detection, FrameData

logger = logging.getLogger("serial.sender")


class SerialSender:
    """Asynchronous serial sender for detection coordinates."""

    _BINARY_HEADER = 0x2424
    _BINARY_FOOTER = 0x2323
    _BINARY_DATA_TYPE = 0x01

    def __init__(
        self,
        config: SerialConfig,
        on_error: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._config = config
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._send_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._serial: Optional[serial.Serial] = None
        self._on_error = on_error
        self._on_status_change = on_status_change
        self._send_enabled = threading.Event()
        self._send_enabled.set()

    def start(self) -> None:
        if self._send_thread and self._send_thread.is_alive():
            logger.debug("Serial sender already running")
            return

        self._stop_event.clear()
        self._send_thread = threading.Thread(target=self._send_worker, name="SerialSenderThread", daemon=True)
        self._send_thread.start()
        self._recv_thread = threading.Thread(target=self._receive_worker, name="SerialReceiveThread", daemon=True)
        self._recv_thread.start()
        logger.info("Serial sender threads started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._send_thread:
            self._send_thread.join(timeout=2.0)
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
        self._send_thread = None
        self._recv_thread = None
        self._close_port()

    def send_detections(self, detections: Iterable[Detection], frame: FrameData) -> None:
        if not self._send_enabled.is_set():
            logger.debug("Sending disabled by MCU command; detections dropped.")
            return
        payload = self._format_payload(detections, frame)
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            message = "Serial queue full; payload dropped."
            logger.warning(message)
            self._notify_error(message)

    def _send_worker(self) -> None:
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._ensure_port():
                logger.error("Serial port unavailable; retrying in %.2f seconds", reconnect_delay)
                self._notify_error("Serial port unavailable. Retrying...")
                time.sleep(reconnect_delay)
                self._requeue_payload(payload)
                continue

            assert self._serial is not None
            try:
                self._serial.write(payload)
                self._serial.flush()
                logger.debug("Sent payload (%d bytes)", len(payload))
            except serial.SerialException as exc:
                logger.error("Failed to write to serial port: %s", exc)
                self._notify_error(f"Failed to send serial payload: {exc}")
                self._close_port()
                time.sleep(reconnect_delay)
                self._requeue_payload(payload)

    def _requeue_payload(self, payload: bytes) -> None:
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            message = "Serial queue full; payload dropped."
            logger.warning(message)
            self._notify_error(message)

    def _receive_worker(self) -> None:
        buffer = bytearray()
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0
        while not self._stop_event.is_set():
            if not self._ensure_port():
                time.sleep(reconnect_delay)
                continue
            assert self._serial is not None
            try:
                data = self._serial.read(1)
            except serial.SerialException as exc:
                logger.error("Serial read failed: %s", exc)
                self._notify_error(f"Serial read failed: {exc}")
                self._close_port()
                time.sleep(reconnect_delay)
                continue

            if not data:
                continue

            buffer.extend(data)
            self._parse_commands(buffer)

    def _parse_commands(self, buffer: bytearray) -> None:
        minimum_length = 7  # header (2) + command (1) + value (1) + CRC (1) + footer (2)
        while True:
            if len(buffer) < minimum_length:
                return
            header_index = buffer.find(struct.pack(">H", self._BINARY_HEADER))
            if header_index == -1:
                buffer.clear()
                return
            if header_index > 0:
                del buffer[:header_index]
            if len(buffer) < minimum_length:
                return

            frame = buffer[:minimum_length]
            header = struct.unpack(">H", frame[0:2])[0]
            command = frame[2]
            value = frame[3]
            crc = frame[4]
            footer = struct.unpack(">H", frame[5:7])[0]

            if header != self._BINARY_HEADER or footer != self._BINARY_FOOTER:
                del buffer[0]
                continue

            calculated_crc = 0
            for byte in frame[:4]:
                calculated_crc ^= byte
            calculated_crc &= 0xFF

            if crc != calculated_crc:
                logger.warning("Discarding command frame with invalid CRC (expected 0x%02X, got 0x%02X).", calculated_crc, crc)
                del buffer[0]
                continue

            del buffer[:minimum_length]
            self._handle_command(command, value)

    def _handle_command(self, command: int, value: int) -> None:
        if command != 0x02:
            logger.debug("Unknown command 0x%02X (value 0x%02X) ignored.", command, value)
            return

        if value == 0x00:
            if self._send_enabled.is_set():
                self._send_enabled.clear()
                self._clear_queue()
                logger.info("MCU command: disable coordinate transmission.")
        elif value == 0x01:
            if not self._send_enabled.is_set():
                self._send_enabled.set()
                logger.info("MCU command: enable coordinate transmission.")
        else:
            logger.debug("Unsupported command value 0x%02X.", value)

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
            self._notify_status(True)
            return True
        except serial.SerialException as exc:
            logger.error("Unable to open serial port %s: %s", self._config.port, exc)
            self._notify_status(False)
            return False

    def _close_port(self) -> None:
        if self._serial and self._serial.is_open:
            logger.info("Closing serial port %s", self._config.port)
            self._serial.close()
        self._serial = None
        self._notify_status(False)

    def _format_payload(self, detections: Iterable[Detection], frame: FrameData) -> bytes:
        detections_list = list(detections)
        if self._config.payload_format == "csv":
            rows = [
                f"{frame.frame_id},{int(det.center()[0])},{int(det.center()[1])}"
                for det in detections_list
            ]
            text = "|".join(rows) + ("\n" if rows else "")
            return text.encode("utf-8")

        if self._config.payload_format == "json":
            payload_dict = {
                "frame_id": frame.frame_id,
                "timestamp": frame.timestamp.isoformat(),
                "detections": [
                    {
                        "id": det.id,
                        "label": det.label,
                        "confidence": det.confidence,
                        "center": {"x": det.center()[0], "y": det.center()[1]},
                    }
                    for det in detections_list
                ],
            }
            return (json.dumps(payload_dict, separators=(",", ":")) + "\n").encode("utf-8")

        # Binary frame format tailored for MCU consumption.
        return self._build_binary_frame(detections_list)

    def _build_binary_frame(self, detections: Sequence[Detection]) -> bytes:
        frame_bytes = bytearray()
        frame_bytes.extend(struct.pack(">H", self._BINARY_HEADER))
        frame_bytes.append(self._BINARY_DATA_TYPE & 0xFF)

        words: list[int] = []
        for det in detections:
            cx, cy = det.center()
            words.append(self._to_uint16(cx))
            words.append(self._to_uint16(cy))

        data_len = len(words)
        if data_len > 0xFF:
            logger.warning("Binary payload truncated to first %d coordinates.", 0xFF // 2)
            words = words[:0xFF]
            data_len = len(words)

        frame_bytes.append(data_len & 0xFF)
        for word in words:
            frame_bytes.extend(struct.pack(">H", word))

        crc = 0
        for byte in frame_bytes:
            crc ^= byte
        crc &= 0xFF
        frame_bytes.append(crc)
        frame_bytes.extend(struct.pack(">H", self._BINARY_FOOTER))
        return bytes(frame_bytes)

    @staticmethod
    def _to_uint16(value: float) -> int:
        int_value = int(round(value))
        if int_value < 0:
            int_value = 0
        elif int_value > 0xFFFF:
            int_value = 0xFFFF
        return int_value

    def _clear_queue(self) -> None:
        with self._queue.mutex:
            self._queue.queue.clear()

    def _notify_error(self, message: str) -> None:
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:  # pragma: no cover - user callback
                logger.exception("Serial error callback failed.")

    def _notify_status(self, status: bool) -> None:
        if self._on_status_change:
            try:
                self._on_status_change(status)
            except Exception:  # pragma: no cover - user callback
                logger.exception("Serial status callback failed.")
