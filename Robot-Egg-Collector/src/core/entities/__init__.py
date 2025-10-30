"""Entity definitions for domain objects."""

from .detection import BoundingBox, Detection
from .frame import FrameData

__all__ = ["BoundingBox", "Detection", "FrameData"]
