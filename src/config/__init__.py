"""Configuration package for EggDetection application."""

from .loader import load_config
from .models import AppConfig, CameraConfig, Config, LoggingConfig, SerialConfig, YoloConfig

__all__ = [
    "AppConfig",
    "CameraConfig",
    "Config",
    "LoggingConfig",
    "SerialConfig",
    "YoloConfig",
    "load_config",
]
