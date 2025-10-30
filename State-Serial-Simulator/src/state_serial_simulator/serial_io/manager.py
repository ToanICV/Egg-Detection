"""Serial port management for the simulator."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from PyQt5 import QtCore

try:
    import serial  # type: ignore
    from serial import Serial, SerialException
except ImportError:  # pragma: no cover - pyserial may be missing in CI
    serial = None
    Serial = object  # type: ignore
    SerialException = Exception  # type: ignore


@dataclass(slots=True)
class SerialConfig:
    """Serial port configuration."""

    port: str
    baudrate: int
    timeout: float


class SerialWorker(QtCore.QObject):
    """Background worker that manages a serial connection."""

    message_received = QtCore.pyqtSignal(str)
    status_changed = QtCore.pyqtSignal(bool, str)

    def __init__(self, config: SerialConfig) -> None:
        super().__init__()
        self._config = config
        self._serial: Optional[Serial] = None
        self._lock = threading.Lock()
        self._running = False

    @QtCore.pyqtSlot()
    def start(self) -> None:
        """Open the serial port and start reading loop."""
        if serial is None:
            self.status_changed.emit(False, "pyserial chua duoc cai dat.")
            return

        try:
            self._serial = serial.Serial(
                port=self._config.port,
                baudrate=self._config.baudrate,
                timeout=self._config.timeout,
            )
            self._running = True
            self.status_changed.emit(True, f"Da ket noi {self._config.port}.")
            self._read_loop()
        except SerialException as exc:
            self.status_changed.emit(
                False,
                f"Khong the mo {self._config.port}: {exc}. Chay o che do offline.",
            )
            self._running = False

    def _read_loop(self) -> None:
        """Continuously read lines from the serial port."""
        if not self._serial:
            return

        while self._running:
            try:
                if not self._serial.in_waiting:
                    QtCore.QThread.msleep(50)
                    continue
                payload = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if payload:
                    self.message_received.emit(payload)
            except SerialException as exc:
                self.status_changed.emit(False, f"Loi serial: {exc}")
                self._running = False
                break

        if self._serial and self._serial.is_open:
            self._serial.close()
            self.status_changed.emit(False, f"Da ngat ket noi {self._config.port}.")

    @QtCore.pyqtSlot()
    def stop(self) -> None:
        """Stop reading and close the port."""
        self._running = False

    @QtCore.pyqtSlot(str)
    def send(self, payload: str) -> None:
        """Send a payload over the serial port."""
        with self._lock:
            if not self._serial or not self._serial.is_open:
                return
            try:
                self._serial.write((payload + "\n").encode("utf-8"))
            except SerialException as exc:
                self.status_changed.emit(False, f"Gui serial that bai: {exc}")


class SerialManager(QtCore.QObject):
    """Public facade managing worker lifetime and Qt signal wiring."""

    def __init__(self, config: SerialConfig, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._thread = QtCore.QThread(self)
        self._worker = SerialWorker(config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start)
        self._thread.finished.connect(self._worker.deleteLater)

    def start(self) -> None:
        """Start the worker thread."""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self) -> None:
        """Stop the worker thread."""
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(500)

    def send(self, payload: str) -> None:
        """Forward payload to worker."""
        QtCore.QMetaObject.invokeMethod(
            self._worker,
            "send",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, payload),
        )

    @property
    def signals(self) -> SerialWorker:
        """Expose the worker for signal connections."""
        return self._worker
