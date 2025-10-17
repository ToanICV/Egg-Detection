"""Main window for EggDetection application."""

from __future__ import annotations

from typing import Sequence

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.entities import Detection, FrameData
from ui.widgets import VideoWidget


class MainWindow(QMainWindow):
    """PyQt5 main window containing the live view and controls."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    overlay_toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Egg Detection Console")
        self.video_widget = VideoWidget()
        self._start_button = QPushButton("Bắt đầu")
        self._stop_button = QPushButton("Dừng")
        self._overlay_checkbox = QCheckBox("Hiển thị khung")
        self._overlay_checkbox.setChecked(True)
        self._detection_label = QLabel("Số lượng: 0 | Thời gian: 0 ms")
        self._serial_label = QLabel("Serial: ngắt kết nối")
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(1000)
        self._status_bar = QStatusBar()
        self._setup_ui()
        self._wire_events()

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.video_widget, stretch=1)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._start_button)
        controls_layout.addWidget(self._stop_button)
        controls_layout.addWidget(self._overlay_checkbox)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self._detection_label)
        controls_layout.addWidget(self._serial_label)
        main_layout.addLayout(controls_layout)

        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self._log_view, stretch=1)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        self.setStatusBar(self._status_bar)

    def _wire_events(self) -> None:
        self._start_button.clicked.connect(self.start_requested.emit)
        self._stop_button.clicked.connect(self.stop_requested.emit)
        self._overlay_checkbox.stateChanged.connect(
            lambda state: self.overlay_toggled.emit(state == 2)
        )

    def display_frame(self, frame: FrameData, detections: Sequence[Detection]) -> None:
        self.video_widget.update_frame(frame, detections)

    def update_detection_stats(self, count: int, inference_ms: float) -> None:
        self._detection_label.setText(f"Số lượng: {count} | Thời gian: {inference_ms:.1f} ms")

    def update_serial_status(self, connected: bool) -> None:
        text = "kết nối" if connected else "ngắt kết nối"
        self._serial_label.setText(f"Serial: {text}")

    def append_log(self, message: str) -> None:
        self._log_view.appendPlainText(message)
        self._log_view.verticalScrollBar().setValue(self._log_view.verticalScrollBar().maximum())

    def show_status_message(self, message: str, timeout_ms: int = 5000) -> None:
        self._status_bar.showMessage(message, timeout_ms)

    def set_overlay_state(self, enabled: bool) -> None:
        self._overlay_checkbox.setChecked(enabled)
