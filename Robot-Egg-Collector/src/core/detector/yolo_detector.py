"""Triển khai bộ phát hiện YOLOv11 dựa trên thư viện Ultralytics."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import List

import numpy as np

try:
    from ultralytics import YOLO
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise ImportError(
        "Ultralytics package is required for YoloDetector. Install with `pip install ultralytics`."
    ) from exc

from config.models import YoloConfig
from core.entities import BoundingBox, Detection, FrameData

from .base import DetectorBase, DetectionResult

logger = logging.getLogger("detector.yolo")


class YoloDetector(DetectorBase):
    """Bộ phát hiện sử dụng mô hình YOLO của Ultralytics."""

    def __init__(self, config: YoloConfig) -> None:
        """Nhận cấu hình YOLO và chuẩn bị trường nội bộ."""
        self._config = config
        self._model: YOLO | None = None
        self._names: List[str] | None = None

    def warmup(self) -> None:
        """Nạp trọng số YOLO và chuẩn hóa cấu hình trước khi suy luận."""
        if self._model is not None:
            return
        logger.info("Loading YOLO weights from %s", self._config.weights_path)
        self._model = YOLO(str(self._config.weights_path))
        names_dict = getattr(self._model, "names", None)
        if isinstance(names_dict, dict):
            self._names = [names_dict[key] for key in sorted(names_dict.keys())]
        else:
            self._names = None
        if self._config.half and self._config.device == "cpu":
            logger.warning("Half precision requested on CPU; forcing full precision.")
            self._config = YoloConfig(
                weights_path=self._config.weights_path,
                confidence_threshold=self._config.confidence_threshold,
                iou_threshold=self._config.iou_threshold,
                device=self._config.device,
                image_size=self._config.image_size,
                max_det=self._config.max_det,
                half=False,
            )

    def detect(self, frame: FrameData) -> DetectionResult:
        """Chạy suy luận YOLO trên khung hình và trả về danh sách phát hiện."""
        self.warmup()
        assert self._model is not None

        start = perf_counter()
        predict_kwargs = dict(
            source=frame.image,
            conf=self._config.confidence_threshold,
            iou=self._config.iou_threshold,
            device=self._config.device,
            max_det=self._config.max_det,
            half=self._config.half,
            verbose=False,
        )
        if self._config.image_size:
            predict_kwargs["imgsz"] = self._config.image_size

        results = self._model.predict(**predict_kwargs)
        inference_time_ms = (perf_counter() - start) * 1000.0
        result = results[0]
        detections = self._parse_results(result, frame)
        annotated_image = self._build_annotated_image(result)
        logger.debug("YOLO inference produced %d detections (%.1f ms)", len(detections), inference_time_ms)
        return DetectionResult(
            frame=frame,
            detections=detections,
            inference_time_ms=inference_time_ms,
            annotated_image=annotated_image,
        )

    def _parse_results(self, result, frame: FrameData) -> List[Detection]:
        """Chuyển đổi kết quả từ Ultralytics thành danh sách Detection."""
        detections: List[Detection] = []
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xyxy is None:
            return detections

        xyxy = boxes.xyxy.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        names_map = getattr(result, "names", None) or self._names

        for idx, (coords, conf, cls_id) in enumerate(zip(xyxy, confidences, classes)):
            bbox = BoundingBox(*coords.tolist())
            label = names_map[cls_id] if names_map and cls_id < len(names_map) else f"class_{cls_id}"
            detections.append(
                Detection(
                    id=idx,
                    label=label,
                    confidence=float(conf),
                    bbox=bbox,
                )
            )
        return detections

    def _build_annotated_image(self, result) -> "np.ndarray | None":
        """Sinh ảnh có vẽ bounding box phục vụ hiển thị; trả None nếu thất bại."""
        try:
            plotted = result.plot()  # returns numpy array with boxes drawn
            return plotted
        except Exception as exc:  # pragma: no cover - plotting is best-effort
            logger.warning("Failed to build annotated image: %s", exc)
            return None
