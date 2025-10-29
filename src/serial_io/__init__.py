"""Serial communication helpers for EggDetection control system."""

from .actor import ActorLink
from .arm import ArmLink
from .bus import SharedSerialBus
from .codec import DecodedFrame, FrameCodec
from .link import SerialLink
from .protocol import (
    ACTOR_GROUP_COMMAND,
    ACTOR_GROUP_STATUS,
    ARM_GROUP_COMMAND,
    ARM_GROUP_STATUS,
    ActorCommand,
    ActorStatus,
    ArmCommand,
    ArmStatus,
    build_actor_command,
    build_actor_status_request,
    build_arm_pick_command,
    build_arm_status_request,
    parse_actor_status,
    parse_arm_status,
)

__all__ = [
    "ActorLink",
    "ArmLink",
    "SharedSerialBus",
    "SerialLink",
    "FrameCodec",
    "DecodedFrame",
    "ActorCommand",
    "ActorStatus",
    "ArmCommand",
    "ArmStatus",
    "ACTOR_GROUP_COMMAND",
    "ACTOR_GROUP_STATUS",
    "ARM_GROUP_COMMAND",
    "ARM_GROUP_STATUS",
    "build_actor_command",
    "build_actor_status_request",
    "build_arm_pick_command",
    "build_arm_status_request",
    "parse_actor_status",
    "parse_arm_status",
]
