"""Centralised event bus based on Qt signals."""

from __future__ import annotations

from PyQt5 import QtCore


class EventBus(QtCore.QObject):
    """Simple event bus used to decouple UI and logic."""

    state_changed = QtCore.pyqtSignal(str, str)
    """Emitted with (previous_state, current_state)."""

    transition_result = QtCore.pyqtSignal(dict)
    """Emitted with transition metadata."""

    log_event = QtCore.pyqtSignal(str, str)
    """Emitted with (level, message)."""

    serial_status = QtCore.pyqtSignal(bool, str)
    """Emitted with (connected, message)."""

    serial_message = QtCore.pyqtSignal(str, str, str)
    """Emitted with (origin, intent, payload) for inbound serial data."""

    trigger_event = QtCore.pyqtSignal(str)
    """UI requests to trigger a state-machine event."""


__all__ = ["EventBus"]
