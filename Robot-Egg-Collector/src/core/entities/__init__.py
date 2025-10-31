"""Định nghĩa các thực thể cốt lõi dùng trong hệ thống."""

from .detection import BoundingBox, Detection
from .frame import FrameData

__all__ = ["BoundingBox", "Detection", "FrameData"]
