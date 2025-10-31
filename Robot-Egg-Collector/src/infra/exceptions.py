"""Thiết lập bộ xử lý ngoại lệ toàn cục cho ứng dụng."""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("app.exceptions")


def install_exception_hook() -> None:
    """Cài đặt handler ngoại lệ cho thread chính và thread nền."""

    hook = _ExceptionHook()
    hook.install()


@dataclass
class _ExceptionHook:
    """Giữ tham chiếu tới hook gốc và triển khai phương thức thay thế."""

    _original_excepthook: Optional[callable] = None
    _original_thread_excepthook: Optional[callable] = None

    def install(self) -> None:
        """Ghi đè excepthook của Python và của threading (nếu khả dụng)."""
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._handle_exception

        if hasattr(threading, "excepthook"):
            self._original_thread_excepthook = threading.excepthook
            threading.excepthook = self._handle_thread_exception  # type: ignore[assignment]

    def _handle_exception(self, exc_type, exc_value, exc_traceback) -> None:
        """Ghi log lỗi chưa bắt và chuyển cho hook gốc xử lý tiếp."""
        logger.critical(
            "Unhandled exception: %s",
            exc_value,
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_thread_exception(self, args: "threading.ExceptHookArgs") -> None:  # pragma: no cover
        """Xử lý ngoại lệ phát sinh trong thread nền, sau đó gọi hook gốc."""
        logger.critical(
            "Unhandled thread exception in %s: %s",
            args.thread.name,
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if self._original_thread_excepthook:
            self._original_thread_excepthook(args)
