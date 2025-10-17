"""Configuration loader utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover - dependency may be absent during static checks
    yaml = None

from .models import AppConfig, CameraConfig, Config, LoggingConfig, SerialConfig, YoloConfig


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

    app = AppConfig(**raw.get("app", {}))

    return Config(camera=camera, yolo=yolo, serial=serial, logging=logging, app=app)
