"""Core state-machine implementation."""

from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Iterable, Mapping, MutableSequence

from .model import StateDefinition, TransitionResult

Listener = Callable[[TransitionResult], None]


class StateMachine:
    """Finite state machine with listener notifications."""

    def __init__(
        self,
        states: Mapping[str, StateDefinition],
        start_state: str,
        history_size: int = 64,
    ) -> None:
        if start_state not in states:
            raise ValueError(f"Unknown start state '{start_state}'")

        self._states = states
        self._start_state = start_state
        self._current_state = start_state
        self._listeners: MutableSequence[Listener] = []
        self._history: Deque[TransitionResult] = deque(maxlen=history_size)

    @property
    def current_state(self) -> StateDefinition:
        """Return the current state definition."""
        return self._states[self._current_state]

    @property
    def current_state_name(self) -> str:
        """Return the name of the current state."""
        return self._current_state

    def add_listener(self, listener: Listener) -> None:
        """Register a listener that receives TransitionResult notifications."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        """Remove a previously registered listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def dispatch(self, event: str) -> TransitionResult:
        """Trigger a transition based on the provided event name."""
        definition = self._states[self._current_state]
        next_state = definition.next_state_for(event)
        accepted = next_state is not None

        if not accepted:
            result = TransitionResult(
                previous_state=self._current_state,
                event=event,
                next_state=self._current_state,
                accepted=False,
                message=f"Su kien '{event}' khong hop le cho trang thai '{definition.label}'.",
            )
            self._history.append(result)
            self._emit(result)
            return result

        previous_state = self._current_state
        self._current_state = next_state  # type: ignore[assignment]
        result = TransitionResult(
            previous_state=previous_state,
            event=event,
            next_state=next_state,
            accepted=True,
            message=f"Chuyen {previous_state} -> {next_state} bang su kien {event}.",
        )
        self._history.append(result)
        self._emit(result)
        return result

    def history(self) -> Iterable[TransitionResult]:
        """Return an iterable snapshot of the transition history."""
        return tuple(self._history)

    def reset(self) -> None:
        """Reset the machine to the initial state."""
        self._current_state = self._start_state

    def _emit(self, result: TransitionResult) -> None:
        for listener in tuple(self._listeners):
            listener(result)
