"""Widget for displaying camera frames and detection overlays."""

from __future__ import annotations

from typing import Sequence, Tuple

import cv2
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from core.entities import Detection, FrameData


class VideoWidget(QWidget):
    """Custom QWidget to render frames and draw detection results."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._frame_size: Tuple[int, int] = (1, 1)
        self._detections: Sequence[Detection] = ()
        self._overlay_enabled = True
        self.setMinimumSize(640, 480)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_overlay_enabled(self, enabled: bool) -> None:
        self._overlay_enabled = enabled
        self.update()

    def update_frame(self, frame: FrameData, detections: Sequence[Detection]) -> None:
        image = frame.image
        if image is None:
            return
        if image.ndim == 2:
            q_image = QImage(image.data, image.shape[1], image.shape[0], image.shape[1], QImage.Format_Grayscale8)
        else:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            q_image = QImage(
                rgb_image.data,
                rgb_image.shape[1],
                rgb_image.shape[0],
                rgb_image.shape[1] * 3,
                QImage.Format_RGB888,
            )
        self._pixmap = QPixmap.fromImage(q_image.copy())
        self._frame_size = (image.shape[1], image.shape[0])
        self._detections = tuple(detections)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        if not self._pixmap:
            painter.end()
            return

        scaled_pixmap = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        target_rect = scaled_pixmap.rect()
        target_rect.moveCenter(self.rect().center())
        painter.drawPixmap(target_rect, scaled_pixmap)

        if self._overlay_enabled:
            self._draw_overlays(painter, target_rect)

        painter.end()

    def _draw_overlays(self, painter: QPainter, target_rect) -> None:
        frame_width, frame_height = self._frame_size
        if frame_width == 0 or frame_height == 0:
            return

        scale_x = target_rect.width() / frame_width
        scale_y = target_rect.height() / frame_height

        pen = QPen(QColor(0, 255, 0))
        pen.setWidth(2)
        painter.setPen(pen)

        for detection in self._detections:
            bbox = detection.bbox
            x1 = target_rect.left() + bbox.x1 * scale_x
            y1 = target_rect.top() + bbox.y1 * scale_y
            width = bbox.width() * scale_x
            height = bbox.height() * scale_y

            rect = QRectF(x1, y1, width, height)
            painter.drawRect(rect)

            label_text = f"{detection.label} {detection.confidence:.2f}"
            painter.drawText(rect.topLeft() + QPointF(4, 14), label_text)
