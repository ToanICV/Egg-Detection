"""Frame container used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class FrameData:
    """Encapsulates a frame along with metadata."""

    image: np.ndarray
    timestamp: datetime
    frame_id: int
    source: Optional[str] = None

    def copy_with(self, **kwargs) -> "FrameData":
        values = {
            "image": self.image,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "source": self.source,
        }
        values.update(kwargs)
        return FrameData(**values)
