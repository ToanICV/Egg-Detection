"""Command builders and parsers for the actor and arm protocols."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Sequence

from .codec import DecodedFrame, FrameCodec

ACTOR_GROUP_COMMAND = 0x04
ACTOR_GROUP_STATUS = 0x03
ARM_GROUP_COMMAND = 0x04
ARM_GROUP_STATUS = 0x03


class ActorCommand(enum.IntEnum):
    MOVE_FORWARD = 0x01
    MOVE_BACKWARD = 0x02
    STOP = 0x03
    TURN_90 = 0x04
    READ_STATUS = 0x05
    ACK = 0xFF


class ArmCommand(enum.IntEnum):
    READ_STATUS = 0x51
    ACK = 0xFF


@dataclass(frozen=True)
class ActorStatus:
    is_moving: bool
    distance_cm: int | None = None


@dataclass(frozen=True)
class ArmStatus:
    is_busy: bool


def build_actor_command(command: ActorCommand) -> bytes:
    group = ACTOR_GROUP_STATUS if command is ActorCommand.READ_STATUS else ACTOR_GROUP_COMMAND
    payload = [group, command]
    length = len(payload) + 3
    return FrameCodec.encode(payload, length=length)


def build_actor_status_request() -> bytes:
    return build_actor_command(ActorCommand.READ_STATUS)


def build_arm_pick_command(x_mm: int, y_mm: int) -> bytes:
    x_mm = max(0, min(0xFFFF, int(round(x_mm))))
    y_mm = max(0, min(0xFFFF, int(round(y_mm))))
    payload = [
        ARM_GROUP_COMMAND,
        (x_mm >> 8) & 0xFF,
        x_mm & 0xFF,
        (y_mm >> 8) & 0xFF,
        y_mm & 0xFF,
    ]
    # Datasheet examples show length byte 0x06; keep compatibility.
    return FrameCodec.encode(payload, length=0x06)


def build_arm_status_request() -> bytes:
    payload = [ARM_GROUP_STATUS, ArmCommand.READ_STATUS]
    return FrameCodec.encode(payload, length=0x06)


def parse_actor_status(frame: DecodedFrame) -> ActorStatus:
    if frame.group != ACTOR_GROUP_STATUS:
        raise ValueError("Frame group does not represent actor status.")
    data = frame.payload_as_ints()
    moving_flag = data[0] if data else 0
    distance = data[1] if len(data) > 1 else None
    return ActorStatus(is_moving=bool(moving_flag), distance_cm=distance)


def parse_arm_status(frame: DecodedFrame) -> ArmStatus:
    if frame.group != ARM_GROUP_STATUS:
        raise ValueError("Frame group does not represent arm status.")
    data = frame.payload_as_ints()
    busy_flag = data[0] if data else 0
    return ArmStatus(is_busy=bool(busy_flag))
