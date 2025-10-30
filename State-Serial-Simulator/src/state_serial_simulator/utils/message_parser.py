"""Helpers to classify inbound serial messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


Actor = str
Intent = str

ARM_KEYWORDS = ("ARM", "MANIPULATOR")
ACTOR_KEYWORDS = ("ACTOR", "ACT", "GRIPPER")

INTENT_KEYWORDS: Dict[Intent, tuple[str, ...]] = {
    "STOP": ("STOP", "HALT", "PAUSE"),
    "ROTATE": ("ROTATE", "TURN", "SPIN"),
    "MOVE_FORWARD": ("MOVE", "FORWARD", "ADVANCE"),
    "GRAB_EGG": ("GRAB", "PICK", "CLAMP", "EGG"),
    "QUERY_STATE": ("QUERY", "STATUS?", "STATE?", "STATUS"),
}


@dataclass(frozen=True)
class MessageInfo:
    """Structured information extracted from raw payload."""

    origin: Actor
    intent: Intent
    payload: str


def _detect_origin(text: str) -> Actor:
    upper = text.upper()
    if any(keyword in upper for keyword in ARM_KEYWORDS):
        return "ARM"
    if any(keyword in upper for keyword in ACTOR_KEYWORDS):
        return "ACTOR"
    return "UNKNOWN"


def _detect_intent(text: str) -> Intent:
    upper = text.upper()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in upper for keyword in keywords):
            return intent
    return "UNKNOWN"


def classify_message(payload: str) -> MessageInfo:
    """Return structured info extracted from an inbound payload."""
    payload = payload.strip()
    origin = _detect_origin(payload)
    intent = _detect_intent(payload)
    return MessageInfo(origin=origin, intent=intent, payload=payload)


__all__ = ["MessageInfo", "classify_message"]
