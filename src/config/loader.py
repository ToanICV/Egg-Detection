"""Configuration loader utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover - dependency may be absent during static checks
    yaml = None

from .models import AppConfig, CameraConfig, Config, LoggingConfig, RoiConfig, SerialConfig, YoloConfig


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

    serial = SerialConfig(**raw.get("serial", {}))

    logging_raw = raw.get("logging", {})
    log_path = logging_raw.get("filepath")
    if log_path:
        logging_raw["filepath"] = (config_path.parent / log_path).resolve()
    logging = LoggingConfig(**logging_raw)

    app_raw = dict(raw.get("app", {}))
    roi_raw = app_raw.pop("roi", None)
    roi = _load_roi_config(roi_raw)
    app = AppConfig(roi=roi, **app_raw)

    return Config(camera=camera, yolo=yolo, serial=serial, logging=logging, app=app)


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
