"""Abstractions for managing serial connections to MCU endpoints."""

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
    predicate: Callable[[DecodedFrame], bool]
    event: threading.Event = field(default_factory=threading.Event)
    result: DecodedFrame | None = None


class SerialLink:
    """Common serial link behaviours (connect, read loop, request/response)."""

    def __init__(
        self,
        name: str,
        config: SerialLinkConfig,
        on_frame: Optional[Callable[[DecodedFrame], None]] = None,
    ) -> None:
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
        return bool(self._reader_thread and self._reader_thread.is_alive())

    @property
    def config(self) -> SerialLinkConfig:
        return self._config

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, name=f"{self._name}-reader", daemon=True)
        self._reader_thread.start()
        logger.info("%s: reader thread started.", self._name)

    def stop(self) -> None:
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None
        self._close_port()
        logger.info("%s: stopped.", self._name)

    def send_payload(self, payload: Sequence[int], length: int | None = None) -> None:
        frame = FrameCodec.encode(payload, length=length)
        self.send_frame(frame)

    def send_frame(self, frame: bytes) -> None:
        self._write(frame)

    def request(self, frame: bytes, predicate: Callable[[DecodedFrame], bool], timeout_s: float) -> DecodedFrame | None:
        waiter = self._register_wait(predicate)
        try:
            self.send_frame(frame)
        except Exception:
            self._cancel_wait(waiter)
            raise
        return self._wait_for(waiter, timeout_s)

    def _register_wait(self, predicate: Callable[[DecodedFrame], bool]) -> _PendingWait:
        wait = _PendingWait(predicate=predicate)
        with self._pending_lock:
            self._pending_waits.append(wait)
        return wait

    def _cancel_wait(self, waiter: _PendingWait) -> None:
        with self._pending_lock:
            if waiter in self._pending_waits:
                self._pending_waits.remove(waiter)

    def _wait_for(self, waiter: _PendingWait, timeout_s: float) -> DecodedFrame | None:
        triggered = waiter.event.wait(timeout_s)
        if not triggered:
            self._cancel_wait(waiter)
            return None
        return waiter.result

    def _reader_loop(self) -> None:
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
        if self._external_on_frame:
            try:
                self._external_on_frame(frame)
            except Exception:
                logger.exception("%s: frame callback failed.", self._name)

    def _write(self, frame: bytes) -> None:
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
        if self._serial and self._serial.is_open:
            logger.info("%s: closing port %s", self._name, self._config.port)
            self._serial.close()
        self._serial = None
