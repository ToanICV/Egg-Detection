"""Abstract camera interface."""

from __future__ import annotations

import abc

from PyQt5.QtCore import QObject, pyqtSignal

from core.entities import FrameData


class _CameraBaseMeta(type(QObject), abc.ABCMeta):
    """Metaclass combining PyQt and ABC metaclasses."""


class CameraBase(QObject, metaclass=_CameraBaseMeta):
    """Base class for camera implementations."""

    frame_captured = pyqtSignal(object)  # FrameData
    error_occurred = pyqtSignal(str)
    started = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._running = False

    @abc.abstractmethod
    def start(self) -> None:
        """Start streaming frames."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop streaming frames."""

    @abc.abstractmethod
    def is_running(self) -> bool:
        """Return whether camera is currently active."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release underlying resources."""
