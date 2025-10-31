"""Các lớp trừu tượng quản lý kết nối nối tiếp tới các thiết bị MCU."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

try:
    import serial
    from serial import SerialException
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError("pyserial is required. Install with `pip install pyserial`.") from exc

from config.models import SerialLinkConfig
from .codec import DecodedFrame, FrameCodec

logger = logging.getLogger("serial.link")


@dataclass
class _PendingWait:
    """Theo dõi yêu cầu chờ phản hồi phù hợp với predicate nhất định."""

    predicate: Callable[[DecodedFrame], bool]
    event: threading.Event = field(default_factory=threading.Event)
    result: DecodedFrame | None = None


class SerialLink:
    """Cung cấp hành vi chung cho liên kết nối tiếp: kết nối, đọc, gửi, chờ phản hồi."""

    def __init__(
        self,
        name: str,
        config: SerialLinkConfig,
        on_frame: Optional[Callable[[DecodedFrame], None]] = None,
    ) -> None:
        """Thiết lập tham số liên kết và callback nhận khung dữ liệu tùy chọn."""
        self._name = name
        self._config = config
        self._external_on_frame = on_frame
        self._serial: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._buffer = bytearray()
        self._pending_lock = threading.Lock()
        self._pending_waits: list[_PendingWait] = []
        self._write_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Cho biết thread đọc dữ liệu đã được khởi động hay chưa."""
        return bool(self._reader_thread and self._reader_thread.is_alive())

    @property
    def config(self) -> SerialLinkConfig:
        """Trả về cấu hình liên kết đang được sử dụng."""
        return self._config

    def start(self) -> None:
        """Khởi động thread đọc nối tiếp nếu chưa chạy."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, name=f"{self._name}-reader", daemon=True)
        self._reader_thread.start()
        logger.info("%s: reader thread started.", self._name)

    def stop(self) -> None:
        """Dừng thread đọc và đóng cổng nối tiếp."""
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None
        self._close_port()
        logger.info("%s: stopped.", self._name)

    def send_payload(self, payload: Sequence[int], length: int | None = None) -> None:
        """Mã hóa chuỗi byte và gửi qua cổng nối tiếp."""
        frame = FrameCodec.encode(payload, length=length)
        self.send_frame(frame)

    def send_frame(self, frame: bytes) -> None:
        """Gửi trực tiếp một khung dữ liệu đã được mã hóa."""
        self._write(frame)

    def request(self, frame: bytes, predicate: Callable[[DecodedFrame], bool], timeout_s: float) -> DecodedFrame | None:
        """Gửi khung dữ liệu và chờ phản hồi thỏa điều kiện trong khoảng thời gian cho trước."""
        waiter = self._register_wait(predicate)
        try:
            self.send_frame(frame)
        except Exception:
            self._cancel_wait(waiter)
            raise
        return self._wait_for(waiter, timeout_s)

    def _register_wait(self, predicate: Callable[[DecodedFrame], bool]) -> _PendingWait:
        """Đăng ký một yêu cầu chờ phản hồi tương ứng với predicate."""
        wait = _PendingWait(predicate=predicate)
        with self._pending_lock:
            self._pending_waits.append(wait)
        return wait

    def _cancel_wait(self, waiter: _PendingWait) -> None:
        """Hủy yêu cầu chờ nếu frame mong đợi không đến."""
        with self._pending_lock:
            if waiter in self._pending_waits:
                self._pending_waits.remove(waiter)

    def _wait_for(self, waiter: _PendingWait, timeout_s: float) -> DecodedFrame | None:
        """Chờ tới khi predicate thỏa hoặc hết thời gian timeout."""
        triggered = waiter.event.wait(timeout_s)
        if not triggered:
            self._cancel_wait(waiter)
            return None
        return waiter.result

    def _reader_loop(self) -> None:
        """Vòng lặp nền đọc dữ liệu, giải mã và phân phối khung cho các bộ xử lý."""
        buffer = self._buffer
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0
        chunk_size = max(1, self._config.read_chunk_size)
        while not self._stop_event.is_set():
            if not self._ensure_port():
                time.sleep(reconnect_delay)
                continue
            assert self._serial is not None
            try:
                data = self._serial.read(chunk_size)
            except SerialException as exc:
                logger.error("%s: serial read error: %s", self._name, exc)
                self._close_port()
                time.sleep(reconnect_delay)
                continue

            if not data:
                continue

            buffer.extend(data)
            frames = FrameCodec.extract_frames(buffer)
            for frame in frames:
                self._dispatch_frame(frame)

        logger.debug("%s: reader loop exiting.", self._name)

    def _dispatch_frame(self, frame: DecodedFrame) -> None:
        """Đánh thức các bộ chờ tương ứng và chuyển khung tới callback bên ngoài."""
        handled = False
        with self._pending_lock:
            for wait in list(self._pending_waits):
                try:
                    if wait.predicate(frame):
                        wait.result = frame
                        wait.event.set()
                        self._pending_waits.remove(wait)
                        handled = True
                        break
                except Exception:  # pragma: no cover - defensive
                    logger.exception("%s: waiter predicate raised exception.", self._name)
        self._on_frame(frame, handled)

    def _on_frame(self, frame: DecodedFrame, handled: bool) -> None:  # pragma: no cover - simple delegation
        """Chuyển tiếp khung tới callback người dùng, ghi log nếu có lỗi."""
        if self._external_on_frame:
            try:
                self._external_on_frame(frame)
            except Exception:
                logger.exception("%s: frame callback failed.", self._name)

    def _write(self, frame: bytes) -> None:
        """Đảm bảo cổng mở và ghi khung dữ liệu xuống thiết bị."""
        if not self._ensure_port():
            raise SerialException(f"{self._name}: unable to open serial port {self._config.port}")
        assert self._serial is not None
        with self._write_lock:
            try:
                self._serial.write(frame)
                self._serial.flush()
                logger.debug("%s: sent %d bytes -> %s", self._name, len(frame), frame.hex(" "))
            except SerialException as exc:
                logger.error("%s: write failed: %s", self._name, exc)
                self._close_port()
                raise

    def _ensure_port(self) -> bool:
        """Mở cổng nối tiếp nếu cần và trả về trạng thái mở thành công."""
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
            logger.info("%s: opened port %s", self._name, self._config.port)
            return True
        except SerialException as exc:
            logger.warning("%s: cannot open port %s (%s)", self._name, self._config.port, exc)
            self._serial = None
            return False

    def _close_port(self) -> None:
        """Đóng cổng nối tiếp đang mở và đưa liên kết về trạng thái rảnh."""
        if self._serial and self._serial.is_open:
            logger.info("%s: closing port %s", self._name, self._config.port)
            self._serial.close()
        self._serial = None
