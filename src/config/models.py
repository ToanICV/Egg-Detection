"""Dataclass definitions for application configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Sequence


@dataclass(frozen=True)
class CameraConfig:
    """Camera related configuration."""

    device_index: int = 0
    resolution: Sequence[int] = (640, 480)
    fps: int = 25
    reconnect_delay_ms: int = 2000
    frame_queue_size: int = 4


@dataclass(frozen=True)
class YoloConfig:
    """YOLO detector configuration."""

    weights_path: Path = Path("weights/egg_detector.pt")
    confidence_threshold: float = 0.4
    iou_threshold: float = 0.5
    device: Literal["cpu", "cuda"] = "cpu"
    image_size: Optional[int] = None
    max_det: int = 50
    half: bool = False

    def resolved_weights(self) -> Path:
        path = self.weights_path if isinstance(self.weights_path, Path) else Path(self.weights_path)
        return path.expanduser().resolve()


@dataclass(frozen=True)
class SerialConfig:
    """Serial communication configuration."""

    port: str = "COM3"
    baudrate: int = 115200
    bytesize: int = 8
    parity: Literal["N", "E", "O", "M", "S"] = "N"
    stopbits: float = 1
    timeout: float = 0.1
    payload_format: Literal["json", "csv"] = "json"
    reconnect_delay_ms: int = 2000


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    filepath: Path = Path("logs/app.log")
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 5
    console: bool = True

    def resolved_path(self) -> Path:
        return self.filepath.expanduser().resolve()


@dataclass(frozen=True)
class AppConfig:
    """Application level configuration."""

    auto_start: bool = True
    ui_language: str = "vi"
    frame_skip: int = 0
    enable_overlay: bool = True
    overlay_frame_gap: int = 10


@dataclass(frozen=True)
class Config:
    """Root configuration object."""

    camera: CameraConfig = field(default_factory=CameraConfig)
    yolo: YoloConfig = field(default_factory=YoloConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    app: AppConfig = field(default_factory=AppConfig)
