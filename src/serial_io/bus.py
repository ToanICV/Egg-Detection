"""Shared serial bus supporting multi-drop devices on a single COM port."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

try:
    import serial
    from serial import SerialException
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError("pyserial is required. Install with `pip install pyserial`.") from exc

from config.models import SerialLinkConfig
from .codec import DecodedFrame, FrameCodec

logger = logging.getLogger("serial.bus")


@dataclass
class _PendingWait:
    predicate: Callable[[DecodedFrame], bool]
    event: threading.Event = field(default_factory=threading.Event)
    result: DecodedFrame | None = None


class SharedSerialBus:
    """Manages a single serial port with shared read loop and request support."""

    def __init__(self, config: SerialLinkConfig) -> None:
        self._config = config
        self._serial: Optional[serial.Serial] = None
        self._serial_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._buffer = bytearray()

        self._pending_lock = threading.Lock()
        self._pending_waits: List[_PendingWait] = []

        self._listeners_lock = threading.Lock()
        self._listeners: Dict[int, Callable[[DecodedFrame], None]] = {}
        self._next_listener_id = 0

        self._usage_lock = threading.Lock()
        self._usage_count = 0

    # Lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        with self._usage_lock:
            self._usage_count += 1
            if self._usage_count > 1:
                return
            logger.info("Starting shared serial bus on %s", self._config.port)
            self._stop_event = threading.Event()
            self._start_reader_thread()

    def stop(self) -> None:
        with self._usage_lock:
            if self._usage_count == 0:
                return
            self._usage_count -= 1
            if self._usage_count > 0:
                return

        if self._stop_event:
            self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None
        self._stop_event = None
        self._close_serial()
        self._buffer.clear()
        self._buffer.clear()
        logger.info("Shared serial bus on %s stopped", self._config.port)

    def shutdown(self) -> None:
        with self._usage_lock:
            self._usage_count = 0
        if self._stop_event:
            self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None
        self._stop_event = None
        self._close_serial()
        self._buffer.clear()

    # Listener management --------------------------------------------------------

    def register_listener(self, callback: Callable[[DecodedFrame], None]) -> int:
        with self._listeners_lock:
            listener_id = self._next_listener_id
            self._next_listener_id += 1
            self._listeners[listener_id] = callback
            return listener_id

    def unregister_listener(self, listener_id: int) -> None:
        with self._listeners_lock:
            self._listeners.pop(listener_id, None)

    # Request/response -----------------------------------------------------------

    def request(self, frame: bytes, predicate: Callable[[DecodedFrame], bool], timeout_s: float) -> DecodedFrame | None:
        waiter = self._register_wait(predicate)
        try:
            self.send_frame(frame)
        except Exception:
            self._cancel_wait(waiter)
            raise
        return self._wait_for(waiter, timeout_s)

    def send_frame(self, frame: bytes) -> None:
        if not self._ensure_serial():
            raise SerialException(f"Unable to open serial port {self._config.port}")
        assert self._serial is not None
        with self._serial_lock:
            try:
                self._serial.write(frame)
                self._serial.flush()
                logger.debug("Bus %s: sent %d bytes -> %s", self._config.port, len(frame), frame.hex(" "))
            except SerialException as exc:
                logger.error("Bus %s write failed: %s", self._config.port, exc)
                self._close_serial()
                raise

    # Internal helpers -----------------------------------------------------------

    def _start_reader_thread(self) -> None:
        if not self._ensure_serial():
            logger.warning("Bus %s: initial open failed; reader thread will retry.", self._config.port)
        self._reader_thread = threading.Thread(target=self._reader_loop, name=f"SerialBus-{self._config.port}", daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        assert self._stop_event is not None
        stop_event = self._stop_event
        buffer = self._buffer
        reconnect_delay = self._config.reconnect_delay_ms / 1000.0

        while not stop_event.is_set():
            if not self._ensure_serial():
                if stop_event.wait(reconnect_delay):
                    break
                continue

            assert self._serial is not None
            try:
                chunk = self._serial.read(self._config.read_chunk_size or 1)
            except SerialException as exc:
                logger.error("Bus %s read failed: %s", self._config.port, exc)
                self._close_serial()
                if stop_event.wait(reconnect_delay):
                    break
                continue

            if not chunk:
                continue

            buffer.extend(chunk)
            frames = FrameCodec.extract_frames(buffer)
            for frame in frames:
                self._dispatch_frame(frame)

        logger.debug("Serial bus reader for %s exiting.", self._config.port)

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
                    logger.exception("Bus %s waiter predicate raised exception.", self._config.port)

        if not handled:
            with self._listeners_lock:
                listeners = list(self._listeners.values())

            for callback in listeners:
                try:
                    callback(frame)
                except Exception:  # pragma: no cover - consumer errors should not kill loop
                    logger.exception("Bus listener error on %s.", self._config.port)

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

    def _ensure_serial(self) -> bool:
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
            logger.info("Bus %s opened.", self._config.port)
            return True
        except SerialException as exc:
            logger.warning("Bus %s open failed: %s", self._config.port, exc)
            self._serial = None
            return False

    def _close_serial(self) -> None:
        if self._serial and self._serial.is_open:
            logger.info("Bus %s closing serial port.", self._config.port)
            self._serial.close()
        self._serial = None
