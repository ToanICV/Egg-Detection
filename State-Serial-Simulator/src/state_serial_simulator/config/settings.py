"""Application settings and default configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping

from state_serial_simulator.state_machine.model import StateDefinition

DEFAULT_LOG_FILE = Path("state_serial_simulator.log")


def _default_states() -> Dict[str, StateDefinition]:
    """Generate the default state-machine definition."""
    return {
        "INIT": StateDefinition(
            name="INIT",
            label="Init",
            description="Khoi tao chu trinh va cho bat dau.",
            transitions={
                "START_CYCLE": "WAITING_ARM",
                "RESET": "INIT",
            },
        ),
        "WAITING_ARM": StateDefinition(
            name="WAITING_ARM",
            label="Cho Arm",
            description="Dang cho tin hieu Arm phan hoi.",
            transitions={
                "ARM_READY": "ARM_CONFIRMED",
                "ARM_ERROR": "FAULT",
                "RESET": "INIT",
            },
        ),
        "ARM_CONFIRMED": StateDefinition(
            name="ARM_CONFIRMED",
            label="Arm Ready",
            description="Arm da san sang, kich hoat Actor.",
            transitions={
                "ACTOR_START": "ACTOR_RUNNING",
                "RESET": "INIT",
            },
        ),
        "ACTOR_RUNNING": StateDefinition(
            name="ACTOR_RUNNING",
            label="Actor dang chay",
            description="Actor dang trong qua trinh thuc thi.",
            transitions={
                "ACTOR_COMPLETE": "COMPLETED",
                "ACTOR_FAULT": "FAULT",
                "RESET": "INIT",
            },
        ),
        "COMPLETED": StateDefinition(
            name="COMPLETED",
            label="Hoan tat",
            description="Chu trinh da hoan tat thanh cong.",
            transitions={
                "RESET": "INIT",
            },
        ),
        "FAULT": StateDefinition(
            name="FAULT",
            label="Loi",
            description="Mot loi da xay ra, can reset.",
            transitions={
                "RESET": "INIT",
            },
        ),
    }


def _default_event_messages() -> Dict[str, str]:
    """Map state machine events to serial payloads."""
    return {
        "START_CYCLE": "CTRL:START",
        "RESET": "CTRL:RESET",
        "ARM_READY": "ARM:READY",
        "ARM_ERROR": "ARM:ERROR",
        "ACTOR_START": "ACTOR:START",
        "ACTOR_COMPLETE": "ACTOR:COMPLETE",
        "ACTOR_FAULT": "ACTOR:FAULT",
    }


@dataclass(slots=True)
class Settings:
    """Strongly typed application settings."""

    serial_port: str = "COM14"
    serial_baudrate: int = 115200
    serial_timeout: float = 0.3
    log_file: Path = DEFAULT_LOG_FILE
    states: Mapping[str, StateDefinition] = field(default_factory=_default_states)
    start_state: str = "INIT"
    event_messages: Mapping[str, str] = field(default_factory=_default_event_messages)
    auto_start_actor: bool = True

    def validate(self) -> None:
        """Validate basic invariants in the configuration."""
        if self.start_state not in self.states:
            raise ValueError(f"Invalid start_state '{self.start_state}'")

        for state_name, definition in self.states.items():
            for _, target in definition.transitions.items():
                if target not in self.states:
                    raise ValueError(
                        f"State '{state_name}' references undefined target '{target}'"
                    )

    def serial_payload_for(self, event: str) -> str | None:
        """Return the serial payload mapped to an event if any."""
        return self.event_messages.get(event)


def load_settings(extra_updates: Iterable[Mapping[str, object]] | None = None) -> Settings:
    """Load settings, applying optional overrides in order."""
    settings = Settings()

    if extra_updates:
        for overrides in extra_updates:
            for key, value in overrides.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)  # type: ignore[arg-type]

    settings.validate()
    return settings
