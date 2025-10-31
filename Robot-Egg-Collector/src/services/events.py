"""Định nghĩa sự kiện phục vụ luồng điều khiển Robot Egg Collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Sequence

from core.entities import Detection, FrameData
from serial_io.protocol import ActorStatus, ArmStatus


class EventType(Enum):
    """Phân loại các nhóm sự kiện chính lưu thông trên hệ thống bus."""

    DETECTION = auto()
    ACTOR_STATUS = auto()
    ARM_STATUS = auto()
    TIMER = auto()
    COMMAND_RESULT = auto()
    STOP = auto()


class TimerId(Enum):
    """Định danh các bộ hẹn giờ nội bộ của ứng dụng."""

    ACTOR_STATUS = "actor_status"
    ARM_STATUS = "arm_status"
    SCAN_ONLY_TIMEOUT = "scan_only_timeout"
    MOVE_ONLY_COUNTDOWN = "move_only_countdown"
    TURN_CHECK = "turn_check"


def _utc_now() -> datetime:
    """Trả về thời điểm hiện tại theo múi giờ UTC để đóng dấu sự kiện."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DetectionEvent:
    """Sự kiện chứa kết quả phát hiện vật thể từ pipeline thị giác."""

    detections: Sequence[Detection]
    frame: FrameData
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.DETECTION)


@dataclass(frozen=True)
class ActorStatusEvent:
    """Sự kiện phản ánh trạng thái tức thời của xe tự hành."""

    status: ActorStatus
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.ACTOR_STATUS)


@dataclass(frozen=True)
class ArmStatusEvent:
    """Sự kiện cập nhật tình trạng bận/rảnh của cánh tay gắp trứng."""

    status: ArmStatus
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.ARM_STATUS)


@dataclass(frozen=True)
class TimerEvent:
    """Sự kiện được phát khi một bộ hẹn giờ kích hoạt."""

    timer_id: TimerId
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.TIMER)


@dataclass(frozen=True)
class CommandResultEvent:
    """Sự kiện thông báo kết quả thực thi lệnh đối với phần cứng."""

    command: str
    success: bool
    details: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.COMMAND_RESULT)


@dataclass(frozen=True)
class StopEvent:
    """Sự kiện yêu cầu toàn hệ thống dừng lại với lý do tùy chọn."""

    reason: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.STOP)
