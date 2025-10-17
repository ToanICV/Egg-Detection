"""Detector abstractions."""

from .base import DetectionResult, DetectorBase
from .yolo_detector import YoloDetector

__all__ = ["DetectionResult", "DetectorBase", "YoloDetector"]
