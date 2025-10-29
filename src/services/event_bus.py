"""Thread-safe event bus for control system communication."""

from __future__ import annotations

import logging
import queue
from typing import Optional

from .events import StopEvent

logger = logging.getLogger("services.event_bus")


class EventBus:
    """Simple publish/consume event bus."""

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: "queue.Queue[object]" = queue.Queue(maxsize=maxsize)

    def publish(self, event: object) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("Event bus queue full; dropping event %s", event)

    def get(self, timeout: Optional[float] = None) -> object:
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> object:
        return self._queue.get_nowait()

    def stop(self, reason: str | None = None) -> None:
        self.publish(StopEvent(reason=reason))
