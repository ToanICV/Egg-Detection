"""Simple helpers to emulate Actor behaviour."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActorSimulator:
    """Produce state-machine events representing Actor feedback."""

    start_event: str = "ACTOR_START"
    complete_event: str = "ACTOR_COMPLETE"
    fault_event: str = "ACTOR_FAULT"

    def emit_start(self) -> str:
        """Return the event for Actor start."""
        return self.start_event

    def emit_complete(self) -> str:
        """Return the event for Actor completion."""
        return self.complete_event

    def emit_fault(self) -> str:
        """Return the event for Actor fault."""
        return self.fault_event
