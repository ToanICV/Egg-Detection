"""Bus sự kiện an toàn đa luồng phục vụ trao đổi trong hệ thống điều khiển."""

from __future__ import annotations

import logging
import queue
from typing import Optional

from .events import StopEvent

logger = logging.getLogger("services.event_bus")


class EventBus:
    """Bus sự kiện đơn giản hỗ trợ phát và lấy thông điệp giữa các thành phần."""

    def __init__(self, maxsize: int = 256) -> None:
        """Khởi tạo hàng đợi giới hạn kích thước để chứa các sự kiện."""
        self._queue: "queue.Queue[object]" = queue.Queue(maxsize=maxsize)

    def publish(self, event: object) -> None:
        """Đưa sự kiện vào hàng đợi; cảnh báo khi hàng đợi bị đầy."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("Event bus queue full; dropping event %s", event)

    def get(self, timeout: Optional[float] = None) -> object:
        """Lấy sự kiện tiếp theo, có thể chờ tối đa một khoảng thời gian."""
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> object:
        """Lấy sự kiện tức thời, ném lỗi nếu hàng đợi trống."""
        return self._queue.get_nowait()

    def stop(self, reason: str | None = None) -> None:
        """Phát StopEvent để thông báo toàn bộ hệ thống kết thúc làm việc."""
        self.publish(StopEvent(reason=reason))
