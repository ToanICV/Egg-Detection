"""Định nghĩa giao diện và cấu trúc dữ liệu cho bộ phát hiện."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from core.entities import Detection, FrameData


@dataclass
class DetectionResult:
    """Gói kết quả suy luận, bao gồm frame gốc và danh sách phát hiện."""

    frame: FrameData
    detections: Sequence[Detection]
    inference_time_ms: float
    annotated_image: Optional[np.ndarray] = None


class DetectorBase(abc.ABC):
    """Lớp cơ sở cho mọi bộ phát hiện đối tượng."""

    @abc.abstractmethod
    def warmup(self) -> None:
        """Khởi động mô hình: nạp trọng số, cấp phát bộ nhớ, chạy thử."""

    @abc.abstractmethod
    def detect(self, frame: FrameData) -> DetectionResult:
        """Chạy suy luận trên khung hình đầu vào và trả về kết quả."""
