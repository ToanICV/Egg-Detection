"""Detection related entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box with pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    def center(self) -> Tuple[float, float]:
        return (self.x1 + self.width() / 2.0, self.y1 + self.height() / 2.0)


@dataclass(frozen=True)
class Detection:
    """Single detection result produced by detector."""

    id: int
    label: str
    confidence: float
    bbox: BoundingBox

    def center(self) -> Tuple[float, float]:
        return self.bbox.center()
