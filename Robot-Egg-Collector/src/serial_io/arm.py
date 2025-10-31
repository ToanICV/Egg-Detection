"""Bao bọc giao tiếp nối tiếp với cánh tay robot."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from config.models import SerialLinkConfig

from .bus import SharedSerialBus
from .codec import DecodedFrame
from .protocol import (
    ARM_GROUP_COMMAND,
    ARM_GROUP_STATUS,
    ArmCommand,
    ArmStatus,
    build_arm_pick_command,
    build_arm_status_request,
    parse_arm_status,
)

logger = logging.getLogger("serial.arm")


class ArmLink:
    """Lớp bao bọc cấp cao để gửi lệnh và nhận trạng thái từ cánh tay."""

    def __init__(
        self,
        bus: SharedSerialBus,
        config: SerialLinkConfig,
        on_status: Optional[Callable[[ArmStatus], None]] = None,
    ) -> None:
        """Thiết lập liên kết với bus nối tiếp và callback trạng thái tùy chọn."""
        self._bus = bus
        self.config = config
        self._status_callback = on_status
        self._last_status: ArmStatus | None = None
        self._listener_id = self._bus.register_listener(self._handle_frame)

    def start(self) -> None:
        """Bắt đầu giao tiếp nối tiếp với cánh tay."""
        self._bus.start()

    def shutdown(self) -> None:
        """Tắt bus nối tiếp khi không cần điều khiển cánh tay."""
        self._bus.stop()

    def pick(self, x_mm: int, y_mm: int) -> bool:
        """Gửi lệnh gắp trứng tại tọa độ đã quy đổi sang milimet."""
        frame = build_arm_pick_command(x_mm, y_mm)
        timeout = self.config.ack_timeout_ms / 1000.0
        frame_hex = frame.hex().upper()
        logger.info("📤 ARM CMD: PICK (%d, %d)mm → COM%s [%s]", x_mm, y_mm, self.config.port, frame_hex)
        ack = self._bus.request(
            frame,
            predicate=lambda f: f.group == ARM_GROUP_COMMAND
            and len(f.payload_as_ints()) >= 1
            and f.payload_as_ints()[0] == ArmCommand.ACK,
            timeout_s=timeout,
        )
        if ack is None:
            logger.warning("❌ ARM CMD: PICK timeout (no ACK after %.1fs)", timeout)
            return False
        if not ack.crc_ok:
            logger.warning("❌ ARM CMD: PICK ACK failed CRC validation")
            return False
        logger.info("✅ ARM CMD: PICK acknowledged")
        return True

    def read_status(self, timeout_s: Optional[float] = None) -> Optional[ArmStatus]:
        """Gửi yêu cầu trạng thái hiện tại và chờ phản hồi trong giới hạn thời gian."""
        frame = build_arm_status_request()
        timeout = timeout_s if timeout_s is not None else self.config.response_timeout_ms / 1000.0
        logger.debug("📤 ARM STATUS: requesting → COM%s", self.config.port)
        response = self._bus.request(
            frame,
            predicate=lambda f: f.group == ARM_GROUP_STATUS,
            timeout_s=timeout,
        )
        if response is None:
            logger.warning("❌ ARM STATUS: timeout (%.1fs)", timeout)
            return None
        if not response.crc_ok:
            logger.warning("❌ ARM STATUS: invalid CRC")
            return None
        status = parse_arm_status(response)
        logger.debug("📥 ARM STATUS: busy=%s", status.is_busy)
        self._update_status(status)
        return status

    def wait_until_idle(self, timeout_s: float, poll_interval_s: float) -> bool:
        """Thăm dò trạng thái cho tới khi cánh tay rảnh hoặc hết thời gian chờ."""
        end_time = time.monotonic() + timeout_s
        while time.monotonic() < end_time:
            status = self.read_status(timeout_s=poll_interval_s)
            if status and not status.is_busy:
                return True
            time.sleep(poll_interval_s)
        return False

    def last_status(self) -> Optional[ArmStatus]:
        """Trả về bản trạng thái mới nhất được ghi nhận."""
        return self._last_status

    def _handle_frame(self, frame: DecodedFrame) -> None:
        """Lọc các khung trạng thái và chuyển thành đối tượng ArmStatus."""
        if frame.group != ARM_GROUP_STATUS:
            return
        if not frame.crc_ok:
            logger.debug("ArmLink: ignoring status frame with invalid CRC.")
            return
        try:
            status = parse_arm_status(frame)
        except Exception:  # pragma: no cover - defensive parsing
            logger.exception("ArmLink: failed to parse status frame.")
            return
        self._update_status(status)

    def _update_status(self, status: ArmStatus) -> None:
        """Lưu trạng thái và kích hoạt callback người dùng nếu có."""
        self._last_status = status
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception:
                logger.exception("ArmLink: status callback failed.")
