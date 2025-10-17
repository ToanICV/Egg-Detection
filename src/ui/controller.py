"""UI controller orchestrating camera, detector, and serial services."""

from __future__ import annotations

import logging
from typing import Sequence

from PyQt5.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal, pyqtSlot

from config.models import AppConfig, Config
from core.camera import CameraBase
from core.comm import SerialSender
from core.detector import DetectionResult, DetectorBase
from core.entities import Detection, FrameData

logger = logging.getLogger("ui.controller")


class UiController(QObject):
    """Application layer tying services to the UI."""

    frame_ready = pyqtSignal(object, object)  # FrameData, Sequence[Detection]
    detection_stats = pyqtSignal(int, float)
    serial_status = pyqtSignal(bool)
    status_message = pyqtSignal(str)
    log_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        camera: CameraBase,
        detector: DetectorBase,
        serial_sender: SerialSender,
        config: Config,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._detector = detector
        self._serial = serial_sender
        self._app_config: AppConfig = config.app
        self._running = False
        self._latest_detections: Sequence[Detection] = ()
        self._latest_detection_frame_id: int | None = None
        self._last_annotated_frame: FrameData | None = None

        self._detection_thread = QThread()
        self._worker = _DetectionWorker(detector, frame_skip=self._app_config.frame_skip)
        self._worker.moveToThread(self._detection_thread)
        self._detection_thread.finished.connect(self._worker.deleteLater)
        self._detection_thread.start()
        self._worker.result_ready.connect(self._on_detection_result)
        self._worker.error_occurred.connect(self._handle_error)

        self._camera.frame_captured.connect(self._on_frame_captured, Qt.QueuedConnection)
        self._camera.frame_captured.connect(self._worker.process_frame, Qt.QueuedConnection)
        self._camera.error_occurred.connect(self._handle_error)

        self._serial.error_occurred.connect(self._handle_error)
        self._serial.status_changed.connect(self.serial_status.emit)
        self._serial.sent.connect(self._on_serial_sent)

        self._log_handler = _QtSignalLogHandler(self.log_message)
        logging.getLogger().addHandler(self._log_handler)

    def start(self) -> None:
        if self._running:
            return
        self._serial.start()
        self._camera.start()
        self._running = True
        self.status_message.emit("System started.")
        logger.info("Application pipeline started.")

    def stop(self) -> None:
        if not self._running:
            return
        self._camera.stop()
        self._serial.stop()
        self._running = False
        self.status_message.emit("System stopped.")
        logger.info("Application pipeline stopped.")

    def shutdown(self) -> None:
        logger.debug("Shutting down UI controller")
        self.stop()
        self._detection_thread.quit()
        self._detection_thread.wait(2000)
        logging.getLogger().removeHandler(self._log_handler)

    @pyqtSlot(object)
    def _on_frame_captured(self, frame: FrameData) -> None:
        # Frames are forwarded to detector only; UI displays annotated results produced later.
        pass

    @pyqtSlot(object)
    def _on_detection_result(self, result: DetectionResult) -> None:
        self._latest_detections = list(result.detections)
        self._latest_detection_frame_id = result.frame.frame_id
        logger.debug(
            "Detections received: %d (frame_id=%s, annotated=%s)",
            len(self._latest_detections),
            self._latest_detection_frame_id,
            result.annotated_image is not None,
        )

        if self._latest_detections:
            try:
                self._serial.send_detections(self._latest_detections, result.frame)
            except Exception as exc:  # pragma: no cover - runtime safety
                self._handle_error(f"Serial send error: {exc}")

        self.detection_stats.emit(len(self._latest_detections), result.inference_time_ms)

        if result.annotated_image is not None:
            annotated_frame = result.frame.copy_with(image=result.annotated_image)
        else:
            annotated_frame = result.frame

        self._last_annotated_frame = annotated_frame
        self.frame_ready.emit(annotated_frame, ())

    @pyqtSlot(str)
    def _handle_error(self, message: str) -> None:
        logger.error(message)
        self.error_occurred.emit(message)
        self.status_message.emit(message)

    @pyqtSlot(str)
    def _on_serial_sent(self, payload: str) -> None:
        self.status_message.emit("Coordinate payload sent.")
        logger.debug("Payload delivered: %s", payload.strip())

    def last_annotated_frame(self) -> FrameData | None:
        return self._last_annotated_frame


class _DetectionWorker(QObject):
    """Runs detector inference on a background thread."""

    result_ready = pyqtSignal(object)  # DetectionResult
    error_occurred = pyqtSignal(str)

    def __init__(self, detector: DetectorBase, frame_skip: int = 0) -> None:
        super().__init__()
        self._detector = detector
        self._frame_skip = frame_skip
        self._skip_counter = 0
        self._busy = False
        self._pending_frame: FrameData | None = None

    @pyqtSlot(object)
    def process_frame(self, frame: FrameData) -> None:
        if self._busy:
            self._pending_frame = frame
            return
        if self._should_skip():
            return

        self._busy = True
        try:
            result = self._detector.detect(frame)
            self.result_ready.emit(result)
        except Exception as exc:  # pragma: no cover - runtime safety
            self.error_occurred.emit(str(exc))
        finally:
            self._busy = False
            if self._pending_frame is not None:
                next_frame = self._pending_frame
                self._pending_frame = None
                QTimer.singleShot(0, lambda f=next_frame: self.process_frame(f))

    def _should_skip(self) -> bool:
        if self._frame_skip <= 0:
            return False

        if self._skip_counter < self._frame_skip:
            self._skip_counter += 1
            return True

        self._skip_counter = 0
        return False


class _QtSignalLogHandler(logging.Handler):
    """Logging handler forwarding records to a Qt signal."""

    def __init__(self, signal: pyqtSignal) -> None:
        super().__init__(level=logging.INFO)
        self._signal = signal
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - UI side-effect
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover
            message = record.getMessage()
        self._signal.emit(message)
