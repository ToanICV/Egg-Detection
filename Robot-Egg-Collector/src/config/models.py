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
    """Legacy serial communication configuration used by standalone sender."""

    port: str = "COM3"
    baudrate: int = 115200
    bytesize: int = 8
    parity: Literal["N", "E", "O", "M", "S"] = "N"
    stopbits: float = 1
    timeout: float = 0.1
    payload_format: Literal["json", "csv", "binary"] = "json"
    reconnect_delay_ms: int = 2000


@dataclass(frozen=True)
class SerialLinkConfig:
    """Serial link configuration for control endpoints."""

    port: str = "COM3"
    baudrate: int = 115200
    bytesize: int = 8
    parity: Literal["N", "E", "O", "M", "S"] = "N"
    stopbits: float = 1
    timeout: float = 0.1
    reconnect_delay_ms: int = 2000
    ack_timeout_ms: int = 500
    response_timeout_ms: int = 1000
    max_retries: int = 3
    read_chunk_size: int = 1


def _default_actor_serial() -> SerialLinkConfig:
    return SerialLinkConfig()


def _default_arm_serial() -> SerialLinkConfig:
    return SerialLinkConfig(port="COM4")


@dataclass(frozen=True)
class SerialTopologyConfig:
    """Serial configuration bundle for actor and arm links."""

    actor: SerialLinkConfig = field(default_factory=_default_actor_serial)
    arm: SerialLinkConfig = field(default_factory=_default_arm_serial)


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
class RoiConfig:
    """Region-of-interest configuration represented as ratios."""

    top_left: Sequence[float] = (0.0, 0.0)
    bottom_right: Sequence[float] = (1.0, 1.0)

    def as_tuple(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (
            (float(self.top_left[0]), float(self.top_left[1])),
            (float(self.bottom_right[0]), float(self.bottom_right[1])),
        )


@dataclass(frozen=True)
class AppConfig:
    """Application level configuration."""

    enable_overlay: bool = True
    roi: RoiConfig = field(default_factory=RoiConfig)


@dataclass(frozen=True)
class SchedulerConfig:
    """Scheduler settings for timers and polling loops."""

    actor_status_interval_ms: int = 1000
    arm_status_interval_ms: int = 1000
    scan_only_timeout_ms: int = 5000
    move_only_duration_ms: int = 5000
    detection_refresh_interval_ms: int = 1000
    turn_check_interval_ms: int = 1000


@dataclass(frozen=True)
class BehaviourConfig:
    """Control behaviour thresholds and limits."""

    distance_stop_threshold_cm: float = 30.0
    detection_center_tolerance: float = 0.2
    detection_min_confidence: float = 0.5
    max_arm_pick_attempts: int = 3
    arm_ready_timeout_ms: int = 2000
    arm_pick_timeout_ms: int = 8000


@dataclass(frozen=True)
class ControlConfig:
    """Top-level control subsystem configuration."""

    serial: SerialLinkConfig = field(default_factory=lambda: SerialLinkConfig(port="COM15"))
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    behaviour: BehaviourConfig = field(default_factory=BehaviourConfig)


@dataclass(frozen=True)
class Config:
    """Root configuration object."""

    camera: CameraConfig = field(default_factory=CameraConfig)
    yolo: YoloConfig = field(default_factory=YoloConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    app: AppConfig = field(default_factory=AppConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
