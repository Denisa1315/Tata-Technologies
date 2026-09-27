"""Persistent-ID tracking on top of YOLOv8n, with an N-frame persistence filter.

Uses Ultralytics' built-in `.track()` (ByteTrack) rather than the `supervision`
library: ultralytics is already a hard dependency for detection, ByteTrack is
bundled with it (`bytetrack.yaml`), and `.track()` returns persistent IDs
directly on the same Boxes object `.predict()` does — so no extra package or
detection<->tracker glue code is needed for this phase.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from smart_zone.perception.detection import (
    COCO_PERSON_CLASS_ID,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MODEL_WEIGHTS,
)

DEFAULT_PERSISTENCE_FRAMES = 3
DEFAULT_TRACKER_CONFIG = "bytetrack.yaml"


@dataclass(frozen=True)
class TrackedDetection:
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str
    consecutive_frames: int
    is_trusted: bool


class PersonTracker:
    """Wraps YOLO .track() and enforces an N-consecutive-frame trust filter.

    A track is only reported as "trusted" once it has appeared in at least
    `persistence_frames` consecutive frames. This suppresses single-frame
    false-positive detections from ever being treated as a real worker.
    Missing a single frame resets that track's streak to zero.
    """

    def __init__(
        self,
        model_weights: str = DEFAULT_MODEL_WEIGHTS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        persistence_frames: int = DEFAULT_PERSISTENCE_FRAMES,
        tracker_config: str = DEFAULT_TRACKER_CONFIG,
        device: str | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.persistence_frames = persistence_frames
        self.tracker_config = tracker_config
        self.device = device
        self.model = YOLO(model_weights)

        self._streaks: dict[int, int] = defaultdict(int)
        self._seen_this_frame: set[int] = set()

    def update(self, frame: np.ndarray) -> list[TrackedDetection]:
        results = self.model.track(
            source=frame,
            classes=[COCO_PERSON_CLASS_ID],
            conf=self.confidence_threshold,
            tracker=self.tracker_config,
            device=self.device,
            persist=True,
            verbose=False,
        )
        return self._to_tracked_detections(results[0])

    def _to_tracked_detections(self, result) -> list[TrackedDetection]:
        current_frame_ids: set[int] = set()
        tracked: list[TrackedDetection] = []

        boxes = result.boxes
        if boxes is not None and boxes.id is not None:
            for box in boxes:
                track_id = int(box.id[0])
                current_frame_ids.add(track_id)

                self._streaks[track_id] += 1
                streak = self._streaks[track_id]

                xyxy = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                class_name = result.names.get(cls_id, str(cls_id))

                tracked.append(
                    TrackedDetection(
                        track_id=track_id,
                        bbox_xyxy=(xyxy[0], xyxy[1], xyxy[2], xyxy[3]),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=class_name,
                        consecutive_frames=streak,
                        is_trusted=streak >= self.persistence_frames,
                    )
                )

        # Reset the streak for any track not seen this frame so a gap breaks
        # "consecutive" — persistence is only meaningful frame-to-frame.
        stale_ids = set(self._streaks.keys()) - current_frame_ids
        for stale_id in stale_ids:
            del self._streaks[stale_id]

        return tracked

    @staticmethod
    def trusted_only(tracked_detections: list[TrackedDetection]) -> list[TrackedDetection]:
        return [t for t in tracked_detections if t.is_trusted]
