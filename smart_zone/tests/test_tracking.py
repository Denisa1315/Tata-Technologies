"""Unit tests for the N-consecutive-frame persistence filter in perception.tracking.

The underlying YOLO model is mocked out so these tests exercise only the
pure streak-tracking / trust logic, not the real detector.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_zone.perception.tracking import PersonTracker


def _make_box(track_id: int, xyxy=(0.0, 0.0, 10.0, 10.0), conf=0.9, cls=0):
    box = MagicMock()
    box.id = [track_id]
    box.xyxy = [np.array(xyxy)]
    box.conf = [conf]
    box.cls = [cls]
    return box


def _make_result(boxes: list):
    boxes_obj = MagicMock()
    boxes_obj.__iter__.return_value = iter(boxes)
    boxes_obj.id = [b.id[0] for b in boxes] if boxes else None
    return SimpleNamespace(boxes=boxes_obj if boxes else None, names={0: "person"})


@pytest.fixture
def tracker():
    with patch("smart_zone.perception.tracking.YOLO"):
        t = PersonTracker(persistence_frames=3)
    return t


def _feed(tracker: PersonTracker, frame_track_ids: list[list[int]]):
    """Feed a sequence of frames, each listing which track IDs appear."""
    outputs = []
    for ids in frame_track_ids:
        boxes = [_make_box(tid) for tid in ids]
        result = _make_result(boxes)
        tracker.model.track.return_value = [result]
        outputs.append(tracker.update(frame=np.zeros((10, 10, 3))))
    return outputs


class TestPersistenceFilter:
    def test_not_trusted_before_threshold(self, tracker):
        outputs = _feed(tracker, [[1], [1]])
        assert outputs[-1][0].consecutive_frames == 2
        assert outputs[-1][0].is_trusted is False

    def test_trusted_at_threshold(self, tracker):
        outputs = _feed(tracker, [[1], [1], [1]])
        assert outputs[-1][0].consecutive_frames == 3
        assert outputs[-1][0].is_trusted is True

    def test_single_frame_detection_is_not_trusted(self, tracker):
        outputs = _feed(tracker, [[1]])
        assert outputs[-1][0].is_trusted is False

    def test_gap_resets_streak(self, tracker):
        # seen, seen, missing, seen -> streak should restart at 1, not continue to 3
        outputs = _feed(tracker, [[1], [1], [], [1]])
        assert outputs[-1][0].consecutive_frames == 1
        assert outputs[-1][0].is_trusted is False

    def test_independent_tracks_have_independent_streaks(self, tracker):
        outputs = _feed(tracker, [[1, 2], [1], [1, 2]])
        last = {t.track_id: t for t in outputs[-1]}
        assert last[1].consecutive_frames == 3
        assert last[1].is_trusted is True
        # track 2 dropped out on frame 2, so its streak restarted this frame
        assert last[2].consecutive_frames == 1
        assert last[2].is_trusted is False

    def test_trusted_only_filters_correctly(self, tracker):
        outputs = _feed(tracker, [[1, 2], [1, 2], [1, 2]])
        trusted = PersonTracker.trusted_only(outputs[-1])
        assert {t.track_id for t in trusted} == {1, 2}

    def test_no_detections_returns_empty(self, tracker):
        outputs = _feed(tracker, [[]])
        assert outputs[-1] == []
