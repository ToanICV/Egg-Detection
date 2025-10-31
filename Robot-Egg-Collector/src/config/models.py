"""Định nghĩa các dataclass cấu hình cho ứng dụng Robot Egg Collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Sequence


@dataclass(frozen=True)
class CameraConfig:
    """Thiết lập cho camera thu hình (thiết bị, độ phân giải, FPS, ...)."""

    device_index: int = 0
    resolution: Sequence[int] = (640, 480)
    fps: int = 25
    reconnect_delay_ms: int = 2000
    frame_queue_size: int = 4


@dataclass(frozen=True)
class YoloConfig:
    """Cấu hình dành cho bộ phát hiện YOLO."""

    weights_path: Path = Path("weights/egg_detector.pt")
    confidence_threshold: float = 0.4
    iou_threshold: float = 0.5
    device: Literal["cpu", "cuda"] = "cpu"
    image_size: Optional[int] = None
    max_det: int = 50
    half: bool = False

    def resolved_weights(self) -> Path:
        """Chuẩn hóa đường dẫn tới file trọng số trên hệ thống."""
        path = self.weights_path if isinstance(self.weights_path, Path) else Path(self.weights_path)
        return path.expanduser().resolve()


@dataclass(frozen=True)
class SerialConfig:
    """Cấu hình giao tiếp nối tiếp dùng cho bộ phát tọa độ độc lập."""

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
    """Cấu hình giao tiếp nối tiếp cho các thiết bị điều khiển chính."""

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
    """Tạo cấu hình mặc định cho đường nối tiếp của xe tự hành."""
    return SerialLinkConfig()


def _default_arm_serial() -> SerialLinkConfig:
    """Tạo cấu hình mặc định cho cánh tay, mặc định cổng COM khác với actor."""
    return SerialLinkConfig(port="COM4")


@dataclass(frozen=True)
class SerialTopologyConfig:
    """Gói cấu hình nối tiếp cho cả xe tự hành và cánh tay."""

    actor: SerialLinkConfig = field(default_factory=_default_actor_serial)
    arm: SerialLinkConfig = field(default_factory=_default_arm_serial)


@dataclass(frozen=True)
class LoggingConfig:
    """Thiết lập ghi log: mức độ, đường dẫn, dung lượng xoay vòng."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    filepath: Path = Path("logs/app.log")
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 5
    console: bool = True

    def resolved_path(self) -> Path:
        """Trả về đường dẫn log tuyệt đối sau khi mở rộng ~."""
        return self.filepath.expanduser().resolve()


@dataclass(frozen=True)
class RoiConfig:
    """Thiết lập vùng quan tâm (ROI) theo tỷ lệ so với kích thước khung hình."""

    top_left: Sequence[float] = (0.0, 0.0)
    bottom_right: Sequence[float] = (1.0, 1.0)

    def as_tuple(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Chuyển ROI thành cặp tọa độ dạng tuple(float, float)."""
        return (
            (float(self.top_left[0]), float(self.top_left[1])),
            (float(self.bottom_right[0]), float(self.bottom_right[1])),
        )


@dataclass(frozen=True)
class AppConfig:
    """Cấu hình cấp ứng dụng (tùy chọn overlay, ROI,...)."""

    enable_overlay: bool = True
    roi: RoiConfig = field(default_factory=RoiConfig)
    detection_publish_interval_ms: int = 1000


@dataclass(frozen=True)
class SchedulerConfig:
    """Thiết lập bộ hẹn giờ phục vụ polling và chuyển trạng thái."""

    actor_status_interval_ms: int = 1000
    arm_status_interval_ms: int = 1000
    scan_only_timeout_ms: int = 5000
    move_only_duration_ms: int = 5000
    detection_refresh_interval_ms: int = 1000
    turn_check_interval_ms: int = 1000


@dataclass(frozen=True)
class BehaviourConfig:
    """Ngưỡng hành vi điều khiển: khoảng dừng, độ lệch trung tâm, số lần thử..."""

    distance_stop_threshold_cm: float = 30.0
    detection_center_tolerance: float = 0.2
    detection_min_confidence: float = 0.5
    max_arm_pick_attempts: int = 3
    arm_ready_timeout_ms: int = 2000
    arm_pick_timeout_ms: int = 8000


@dataclass(frozen=True)
class ControlConfig:
    """Cấu hình tổng thể cho khối điều khiển (serial, scheduler, hành vi)."""

    serial: SerialLinkConfig = field(default_factory=lambda: SerialLinkConfig(port="COM15"))
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    behaviour: BehaviourConfig = field(default_factory=BehaviourConfig)


@dataclass(frozen=True)
class Config:
    """Đối tượng cấu hình gốc tập hợp mọi nhóm thiết lập của ứng dụng."""

    camera: CameraConfig = field(default_factory=CameraConfig)
    yolo: YoloConfig = field(default_factory=YoloConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    app: AppConfig = field(default_factory=AppConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
