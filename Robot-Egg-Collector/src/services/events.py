"""Event definitions for EggDetection control workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Sequence

from core.entities import Detection, FrameData
from serial_io.protocol import ActorStatus, ArmStatus


class EventType(Enum):
    DETECTION = auto()
    ACTOR_STATUS = auto()
    ARM_STATUS = auto()
    TIMER = auto()
    COMMAND_RESULT = auto()
    STOP = auto()


class TimerId(Enum):
    ACTOR_STATUS = "actor_status"
    ARM_STATUS = "arm_status"
    SCAN_ONLY_TIMEOUT = "scan_only_timeout"
    MOVE_ONLY_COUNTDOWN = "move_only_countdown"
    TURN_CHECK = "turn_check"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DetectionEvent:
    detections: Sequence[Detection]
    frame: FrameData
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.DETECTION)


@dataclass(frozen=True)
class ActorStatusEvent:
    status: ActorStatus
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.ACTOR_STATUS)


@dataclass(frozen=True)
class ArmStatusEvent:
    status: ArmStatus
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.ARM_STATUS)


@dataclass(frozen=True)
class TimerEvent:
    timer_id: TimerId
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.TIMER)


@dataclass(frozen=True)
class CommandResultEvent:
    command: str
    success: bool
    details: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.COMMAND_RESULT)


@dataclass(frozen=True)
class StopEvent:
    reason: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    type: EventType = field(init=False, default=EventType.STOP)
