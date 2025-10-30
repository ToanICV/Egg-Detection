"""Global exception handling for the application."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("app.exceptions")


def install_exception_hook() -> None:
    """Install global exception handlers for main thread and worker threads."""

    hook = _ExceptionHook()
    hook.install()


@dataclass
class _ExceptionHook:
    _original_excepthook: Optional[callable] = None
    _original_thread_excepthook: Optional[callable] = None

    def install(self) -> None:
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._handle_exception

        if hasattr(threading, "excepthook"):
            self._original_thread_excepthook = threading.excepthook
            threading.excepthook = self._handle_thread_exception  # type: ignore[assignment]

    def _handle_exception(self, exc_type, exc_value, exc_traceback) -> None:
        logger.critical(
            "Unhandled exception: %s",
            exc_value,
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_thread_exception(self, args: "threading.ExceptHookArgs") -> None:  # pragma: no cover
        logger.critical(
            "Unhandled thread exception in %s: %s",
            args.thread.name,
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if self._original_thread_excepthook:
            self._original_thread_excepthook(args)
