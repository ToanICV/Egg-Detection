"""Simple helpers to emulate Arm behaviour."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ArmSimulator:
    """Produce state-machine events representing Arm feedback."""

    ready_event: str = "ARM_READY"
    error_event: str = "ARM_ERROR"

    def emit_ready(self) -> str:
        """Return the event name for the Arm Ready signal."""
        return self.ready_event

    def emit_error(self) -> str:
        """Return the event name for the Arm Error signal."""
        return self.error_event
