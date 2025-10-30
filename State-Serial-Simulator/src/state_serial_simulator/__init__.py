"""State Serial Simulator package."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .config.settings import Settings, load_settings

__all__ = ["AppController", "Settings", "load_settings"]


def __getattr__(name: str) -> Any:
    """Lazily import heavy modules (Qt)."""
    if name == "AppController":
        module = import_module("state_serial_simulator.app.controller")
        return getattr(module, "AppController")
    raise AttributeError(name)
