"""Cấu trúc chứa khung hình và metadata dùng xuyên suốt pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class FrameData:
    """Gói khung hình cùng thông tin thời gian và nguồn phát."""

    image: np.ndarray
    timestamp: datetime
    frame_id: int
    source: Optional[str] = None

    def copy_with(self, **kwargs) -> "FrameData":
        """Tạo bản sao của khung hình với các trường được ghi đè tùy chọn."""
        values = {
            "image": self.image,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "source": self.source,
        }
        values.update(kwargs)
        return FrameData(**values)
