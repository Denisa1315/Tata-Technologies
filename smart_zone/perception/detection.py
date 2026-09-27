"""Person-only detection wrapper around Ultralytics YOLOv8n."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ultralytics import YOLO

COCO_PERSON_CLASS_ID = 0
SMART_ZONE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_WEIGHTS = str(SMART_ZONE_ROOT / "yolov8n.pt")
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class Detection:
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


class PersonDetector:
    """Runs YOLOv8n restricted to the COCO 'person' class."""

    def __init__(
        self,
        model_weights: str = DEFAULT_MODEL_WEIGHTS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        device: str | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.device = device
        # Ultralytics auto-downloads weights on first use if not present locally.
        self.model = YOLO(model_weights)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            source=frame,
            classes=[COCO_PERSON_CLASS_ID],
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        return self._to_detections(results[0])

    def _to_detections(self, result) -> list[Detection]:
        detections: list[Detection] = []
        boxes = result.boxes
        if boxes is None:
            return detections

        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            class_name = result.names.get(cls_id, str(cls_id))
            detections.append(
                Detection(
                    bbox_xyxy=(xyxy[0], xyxy[1], xyxy[2], xyxy[3]),
                    confidence=conf,
                    class_id=cls_id,
                    class_name=class_name,
                )
            )
        return detections
