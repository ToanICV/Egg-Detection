"""Các thực thể liên quan tới kết quả nhận diện."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class BoundingBox:
    """Hình chữ nhật căn chỉnh theo trục với tọa độ điểm ảnh."""

    x1: float
    y1: float
    x2: float
    y2: float

    def width(self) -> float:
        """Chiều rộng theo trục X của bounding box."""
        return max(0.0, self.x2 - self.x1)

    def height(self) -> float:
        """Chiều cao theo trục Y của bounding box."""
        return max(0.0, self.y2 - self.y1)

    def center(self) -> Tuple[float, float]:
        """Tâm hình chữ nhật tính theo tọa độ pixel."""
        return (self.x1 + self.width() / 2.0, self.y1 + self.height() / 2.0)


@dataclass(frozen=True)
class Detection:
    """Một kết quả nhận diện duy nhất do bộ dò trả về."""

    id: int
    label: str
    confidence: float
    bbox: BoundingBox

    def center(self) -> Tuple[float, float]:
        """Trả về tâm của hộp bao quanh đối tượng."""
        return self.bbox.center()
