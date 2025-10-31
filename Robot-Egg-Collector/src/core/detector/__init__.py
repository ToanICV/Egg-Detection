"""Các lớp trừu tượng và triển khai cho bộ phát hiện."""

from .base import DetectionResult, DetectorBase
from .yolo_detector import YoloDetector

__all__ = ["DetectionResult", "DetectorBase", "YoloDetector"]
