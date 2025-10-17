"""Detector interface definitions."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from core.entities import Detection, FrameData


@dataclass
class DetectionResult:
    """Container for detector outputs."""

    frame: FrameData
    detections: Sequence[Detection]
    inference_time_ms: float
    annotated_image: Optional[np.ndarray] = None


class DetectorBase(abc.ABC):
    """Interface for detection engines."""

    @abc.abstractmethod
    def warmup(self) -> None:
        """Prepare model (load weights, allocate resources)."""

    @abc.abstractmethod
    def detect(self, frame: FrameData) -> DetectionResult:
        """Run detection on provided frame."""
