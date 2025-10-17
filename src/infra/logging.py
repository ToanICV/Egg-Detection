"""Logging configuration helpers."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from config.models import LoggingConfig


def configure_logging(config: LoggingConfig) -> None:
    """Setup Python logging according to provided configuration."""

    log_level = getattr(logging, config.level.upper(), logging.INFO)
    logging.captureWarnings(True)

    handlers: list[logging.Handler] = []
    log_path = config.resolved_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(_build_formatter())
    handlers.append(file_handler)

    if config.console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(_build_formatter(color=False))
        handlers.append(console_handler)

    logging.basicConfig(level=log_level, handlers=handlers, force=True)
    logging.getLogger("ultralytics").setLevel(logging.WARNING)


def _build_formatter(color: bool = False) -> logging.Formatter:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    return logging.Formatter(fmt=fmt, datefmt=datefmt)
