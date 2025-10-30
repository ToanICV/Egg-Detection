"""Configuration loader utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover - dependency may be absent during static checks
    yaml = None

from .models import (
    AppConfig,
    BehaviourConfig,
    CameraConfig,
    Config,
    ControlConfig,
    LoggingConfig,
    RoiConfig,
    SchedulerConfig,
    SerialLinkConfig,
    SerialTopologyConfig,
    YoloConfig,
)


def _normalize_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _load_raw_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")

    suffix = config_path.suffix.lower()
    with config_path.open("r", encoding="utf-8") as stream:
        if suffix in {".yaml", ".yml"}:
            if yaml is None:
                raise RuntimeError("PyYAML is required to parse YAML configuration files.")
            return yaml.safe_load(stream) or {}
        if suffix == ".json":
            return json.load(stream)
        raise ValueError(f"Unsupported config format: {suffix}")


def load_config(config_path: Path | str) -> Config:
    """Load configuration file and construct Config dataclass."""

    config_path = _normalize_path(config_path)
    raw = _load_raw_config(config_path)

    camera = CameraConfig(**raw.get("camera", {}))
    yolo_raw = raw.get("yolo", {})
    # Normalize weights path relative to config file for predictable behaviour.
    weights_path = yolo_raw.get("weights_path")
    if weights_path:
        yolo_raw["weights_path"] = (config_path.parent / weights_path).resolve()
    yolo = YoloConfig(**yolo_raw)

    logging_raw = raw.get("logging", {})
    log_path = logging_raw.get("filepath")
    if log_path:
        logging_raw["filepath"] = (config_path.parent / log_path).resolve()
    logging = LoggingConfig(**logging_raw)

    app_raw = dict(raw.get("app", {}))
    roi_raw = app_raw.pop("roi", None)
    roi = _load_roi_config(roi_raw)
    app = AppConfig(roi=roi, **app_raw)

    control = _load_control_config(raw, defaults=ControlConfig())

    return Config(camera=camera, yolo=yolo, logging=logging, app=app, control=control)


def _load_roi_config(raw_roi: Any) -> RoiConfig:
    if raw_roi is None:
        return RoiConfig()

    try:
        top_left = raw_roi["top_left"]
        bottom_right = raw_roi["bottom_right"]
    except (TypeError, KeyError) as exc:
        raise ValueError("ROI configuration must include 'top_left' and 'bottom_right' coordinates.") from exc

    def _pair(value: Any) -> tuple[float, float]:
        if value is None or len(value) != 2:
            raise ValueError("ROI coordinates must be a sequence of two ratios [x, y].")
        return float(value[0]), float(value[1])

    return RoiConfig(top_left=_pair(top_left), bottom_right=_pair(bottom_right))


def _load_control_config(raw_root: Dict[str, Any], defaults: ControlConfig) -> ControlConfig:
    control_raw = dict(raw_root.get("control", {})) if isinstance(raw_root.get("control"), dict) else {}

    serial_section = control_raw.get("serial")
    if serial_section is None and isinstance(raw_root.get("serial"), dict):
        serial_section = raw_root["serial"]
    serial_config = _load_serial_config(serial_section, defaults.serial)

    scheduler_raw = control_raw.get("scheduler", {})
    scheduler_config = defaults.scheduler
    if isinstance(scheduler_raw, dict):
        scheduler_config = SchedulerConfig(**scheduler_raw)

    behaviour_raw = control_raw.get("behaviour", {})
    behaviour_config = defaults.behaviour
    if isinstance(behaviour_raw, dict):
        behaviour_config = BehaviourConfig(**behaviour_raw)

    return ControlConfig(serial=serial_config, scheduler=scheduler_config, behaviour=behaviour_config)


def _load_serial_config(raw_serial: Any, defaults: SerialLinkConfig) -> SerialLinkConfig:
    """Load single serial configuration for RS485 bus."""
    if not isinstance(raw_serial, dict) or not raw_serial:
        return defaults
    return SerialLinkConfig(**raw_serial)


def _load_serial_topology(raw_serial: Any, defaults: SerialTopologyConfig) -> SerialTopologyConfig:
    """Legacy function for backward compatibility."""
    if not isinstance(raw_serial, dict) or not raw_serial:
        return defaults

    if "actor" in raw_serial or "arm" in raw_serial:
        actor_raw = raw_serial.get("actor", {})
        arm_raw = raw_serial.get("arm", {})
        actor_cfg = SerialLinkConfig(**actor_raw) if isinstance(actor_raw, dict) else defaults.actor
        arm_cfg = SerialLinkConfig(**arm_raw) if isinstance(arm_raw, dict) else defaults.arm
        return SerialTopologyConfig(actor=actor_cfg, arm=arm_cfg)

    # Backward compatibility: treat single serial block as shared defaults.
    shared = SerialLinkConfig(**raw_serial)
    return SerialTopologyConfig(actor=shared, arm=SerialLinkConfig(**raw_serial))
