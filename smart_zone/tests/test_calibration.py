"""Unit tests for spatial.calibration._capture_calibration_frame: camera
open failure, mid-warm-up read failure, warm-up frame count, and the
dark-frame sanity check -- all with a mocked cv2.VideoCapture so no real
camera is needed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_zone.spatial.calibration import (
    DARK_FRAME_MEAN_THRESHOLD,
    WARMUP_FRAME_COUNT,
    _capture_calibration_frame,
)


def _bright_frame(mean_value=128.0):
    return np.full((480, 640, 3), mean_value, dtype=np.uint8)


def _dark_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


class TestCameraOpenFailure:
    def test_raises_clear_error_when_camera_fails_to_open(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError, match="Could not open camera index"):
                _capture_calibration_frame(camera_index=0)

    def test_error_mentions_the_camera_index_used(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError, match="index 2"):
                _capture_calibration_frame(camera_index=2)


class TestReadFailure:
    def test_raises_clear_error_when_read_returns_false(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.return_value = (False, None)

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError, match="returned False"):
                _capture_calibration_frame(camera_index=0)

    def test_releases_camera_even_on_read_failure(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.return_value = (False, None)

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError):
                _capture_calibration_frame(camera_index=0)

        fake_cap.release.assert_called_once()

    def test_fails_partway_through_warmup(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        # succeeds for a few frames, then fails
        results = [(True, _bright_frame())] * 5 + [(False, None)]
        fake_cap.read.side_effect = results

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError, match="warm-up frame 6"):
                _capture_calibration_frame(camera_index=0)


class TestWarmup:
    def test_reads_warmup_frame_count_frames_before_returning(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.return_value = (True, _bright_frame())

        with patch("cv2.VideoCapture", return_value=fake_cap):
            _capture_calibration_frame(camera_index=0)

        assert fake_cap.read.call_count == WARMUP_FRAME_COUNT

    def test_returns_the_last_warmup_frame(self):
        first_frame = _bright_frame(100.0)
        last_frame = _bright_frame(150.0)
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        results = [(True, first_frame)] * (WARMUP_FRAME_COUNT - 1) + [(True, last_frame)]
        fake_cap.read.side_effect = results

        with patch("cv2.VideoCapture", return_value=fake_cap):
            frame = _capture_calibration_frame(camera_index=0)

        assert frame is last_frame


class TestDarkFrameDetection:
    def test_raises_on_all_black_frame(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.return_value = (True, _dark_frame())

        with patch("cv2.VideoCapture", return_value=fake_cap):
            with pytest.raises(RuntimeError, match="suspiciously dark"):
                _capture_calibration_frame(camera_index=0)

    def test_accepts_a_normally_lit_frame(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        fake_cap.read.return_value = (True, _bright_frame(120.0))

        with patch("cv2.VideoCapture", return_value=fake_cap):
            frame = _capture_calibration_frame(camera_index=0)

        assert frame is not None

    def test_threshold_boundary(self):
        fake_cap = MagicMock()
        fake_cap.isOpened.return_value = True
        just_above = _bright_frame(DARK_FRAME_MEAN_THRESHOLD + 1.0)
        fake_cap.read.return_value = (True, just_above)

        with patch("cv2.VideoCapture", return_value=fake_cap):
            frame = _capture_calibration_frame(camera_index=0)
        assert frame is not None
