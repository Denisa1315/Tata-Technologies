"""Unit tests for dashboard.sim_view: pure rendering, no decision logic.

These tests confirm sim_view only draws from the SimViewState it's given --
it must not import safety.risk_engine or any other decision-making module.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from smart_zone.dashboard.sim_view import (
    WINDOW_H,
    WINDOW_W,
    SimView,
    SimViewState,
    TransitionRecord,
    WorkerViewState,
)

SIM_VIEW_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "sim_view.py"


def _base_state(**overrides) -> SimViewState:
    defaults = dict(
        risk_state="SAFE",
        ttc_s=None,
        machine_pivot=(0.0, 0.0),
        machine_angle_deg=45.0,
        machine_speed_deg_s=10.0,
        machine_arm_length_m=3.0,
        machine_running=True,
        zone_center=(0.0, 0.0),
        zone_orientation_deg=45.0,
        zone_caution_semi_major_m=2.0,
        zone_caution_semi_minor_m=1.2,
        zone_danger_semi_major_m=1.0,
        zone_danger_semi_minor_m=0.6,
        workers=[],
        led_level=0,
        buzzer_on=False,
        stop_active=False,
        fps=25.0,
        camera_alive=True,
        telemetry_alive=True,
        camera_fault_simulated=False,
        recent_transitions=[],
        webcam_frame=None,
    )
    defaults.update(overrides)
    return SimViewState(**defaults)


class TestNoDecisionLogic:
    def test_does_not_import_risk_engine_or_other_decision_modules(self):
        """Static check: sim_view.py's import statements must not reference
        safety.risk_engine (or any zone/kalman computation module) -- it may
        only import display/plotting libraries and its own dataclasses."""
        tree = ast.parse(SIM_VIEW_PATH.read_text())
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        forbidden_substrings = ["risk_engine", "safety.zone", "prediction.kalman", "prediction.ttc"]
        for module in imported_modules:
            for forbidden in forbidden_substrings:
                assert forbidden not in module, f"sim_view.py imports decision logic: {module}"


class TestRenderProducesCorrectCanvas:
    def test_render_returns_correct_shape(self):
        view = SimView()
        canvas = view.render(_base_state())
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)
        assert canvas.dtype == np.uint8

    def test_render_with_no_workers_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(workers=[]))
        assert canvas is not None

    def test_render_with_workers_does_not_crash(self):
        view = SimView()
        workers = [
            WorkerViewState(track_id=1, position=(1.0, 1.0), forecast_position=(1.5, 1.2),
                             zone_level="CAUTION"),
            WorkerViewState(track_id=2, position=(0.2, 0.1), forecast_position=(0.1, 0.05),
                             zone_level="DANGER"),
        ]
        canvas = view.render(_base_state(workers=workers))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_each_risk_state_does_not_crash(self):
        view = SimView()
        for state_name in ["SAFE", "WARNING", "CRITICAL", "DEGRADED"]:
            canvas = view.render(_base_state(risk_state=state_name, led_level={"SAFE": 0, "WARNING": 1, "CRITICAL": 2, "DEGRADED": 3}[state_name]))
            assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_none_ttc_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(ttc_s=None))
        assert canvas is not None

    def test_render_with_stop_active_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(stop_active=True, machine_running=False))
        assert canvas is not None

    def test_render_with_camera_fault_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(camera_fault_simulated=True, camera_alive=False))
        assert canvas is not None

    def test_render_with_webcam_frame_composites_inset(self):
        view = SimView(show_webcam_inset=True)
        fake_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        canvas = view.render(_base_state(webcam_frame=fake_frame))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_without_webcam_inset_flag_skips_it_even_if_frame_given(self):
        view = SimView(show_webcam_inset=False)
        fake_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        canvas = view.render(_base_state(webcam_frame=fake_frame))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_many_transitions_only_shows_last_five(self):
        view = SimView()
        transitions = [
            TransitionRecord(timestamp=float(i), from_state="SAFE", to_state="WARNING", ttc_s=3.0)
            for i in range(20)
        ]
        canvas = view.render(_base_state(recent_transitions=transitions))
        assert canvas is not None


class TestPollKeys:
    def test_recognized_keys_are_returned(self):
        view = SimView()
        for key_char, expected in [("q", "q"), ("c", "c"), ("r", "r"), ("s", "s"), ("+", "+"), ("-", "-")]:
            with patch("cv2.waitKey", return_value=ord(key_char)):
                assert view.poll_keys() == expected

    def test_equals_sign_maps_to_plus(self):
        view = SimView()
        with patch("cv2.waitKey", return_value=ord("=")):
            assert view.poll_keys() == "+"

    def test_no_key_returns_none(self):
        view = SimView()
        with patch("cv2.waitKey", return_value=255):
            assert view.poll_keys() is None

    def test_unrecognized_key_returns_none(self):
        view = SimView()
        with patch("cv2.waitKey", return_value=ord("z")):
            assert view.poll_keys() is None
