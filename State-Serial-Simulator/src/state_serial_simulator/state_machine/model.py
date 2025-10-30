"""Data structures representing the state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping


@dataclass(slots=True)
class StateDefinition:
    """Description of a state in the machine."""

    name: str
    label: str
    description: str = ""
    transitions: Mapping[str, str] = field(default_factory=dict)

    def next_state_for(self, event: str) -> str | None:
        """Return the destination state for the provided event."""
        return self.transitions.get(event)


@dataclass(slots=True)
class TransitionResult:
    """Result of executing a transition."""

    previous_state: str
    event: str
    next_state: str
    accepted: bool
    message: str = ""

    @property
    def changed(self) -> bool:
        """Return True if the transition changed the state."""
        return self.accepted and self.previous_state != self.next_state
