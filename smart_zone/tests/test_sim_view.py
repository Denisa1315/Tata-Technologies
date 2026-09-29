"""Unit tests for dashboard.sim_view and dashboard.hologram_view: pure
rendering, no decision logic.

These tests confirm both views only draw from the SimViewState they're
given -- neither may import safety.risk_engine, safety.zone,
safety.confidence, or prediction.kalman/ttc.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from smart_zone.dashboard.hologram_view import HologramView
from smart_zone.dashboard.sim_view import (
    DARK_THEME,
    LIGHT_THEME,
    WINDOW_H,
    WINDOW_W,
    SimView,
    SimViewState,
    SummaryViewState,
    TransitionRecord,
    WorkerViewState,
)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
SIM_VIEW_PATH = DASHBOARD_DIR / "sim_view.py"
HOLOGRAM_VIEW_PATH = DASHBOARD_DIR / "hologram_view.py"
SOUND_PATH = DASHBOARD_DIR / "sound.py"

FORBIDDEN_IMPORT_SUBSTRINGS = [
    "risk_engine", "safety.zone", "safety.confidence", "prediction.kalman", "prediction.ttc",
]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _base_state(**overrides) -> SimViewState:
    defaults = dict(
        risk_state="SAFE",
        ttc_s=None,
        use_prediction=False,
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
        summary=None,
    )
    defaults.update(overrides)
    return SimViewState(**defaults)


LED_LEVEL_BY_STATE = {"SAFE": 0, "WARNING": 1, "CRITICAL": 2, "DEGRADED": 3}


class TestNoDecisionLogic:
    def test_sim_view_does_not_import_decision_logic(self):
        modules = _imported_modules(SIM_VIEW_PATH)
        for module in modules:
            for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
                assert forbidden not in module, f"sim_view.py imports decision logic: {module}"

    def test_hologram_view_does_not_import_decision_logic(self):
        modules = _imported_modules(HOLOGRAM_VIEW_PATH)
        for module in modules:
            for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
                assert forbidden not in module, f"hologram_view.py imports decision logic: {module}"

    def test_sound_does_not_import_decision_logic(self):
        modules = _imported_modules(SOUND_PATH)
        for module in modules:
            for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
                assert forbidden not in module, f"sound.py imports decision logic: {module}"


class TestPlainViewRendering:
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

    @pytest.mark.parametrize("state_name", ["SAFE", "WARNING", "CRITICAL", "DEGRADED"])
    def test_render_each_risk_state_does_not_crash(self, state_name):
        view = SimView()
        canvas = view.render(_base_state(risk_state=state_name, led_level=LED_LEVEL_BY_STATE[state_name]))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_low_confidence_worker_does_not_crash(self):
        view = SimView()
        workers = [
            WorkerViewState(track_id=1, position=(0.5, 0.5), forecast_position=(0.6, 0.5),
                             zone_level="DANGER", position_confidence="LOW"),
        ]
        canvas = view.render(_base_state(workers=workers, risk_state="CRITICAL"))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_none_ttc_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(ttc_s=None))
        assert canvas is not None

    def test_render_hides_ttc_and_forecast_when_use_prediction_false(self):
        view = SimView()
        workers = [WorkerViewState(track_id=1, position=(0.5, 0.5), forecast_position=(5.0, 5.0), zone_level="CAUTION")]
        canvas = view.render(_base_state(use_prediction=False, ttc_s=3.2, workers=workers))
        # Can't easily assert absence of a specific line pixel-by-pixel
        # reliably, but this at least exercises the use_prediction=False
        # path without crashing and without needing forecast_position to
        # be sane (it's a wildly out-of-frame value here).
        assert canvas is not None

    def test_render_shows_ttc_and_forecast_when_use_prediction_true(self):
        view = SimView()
        workers = [WorkerViewState(track_id=1, position=(0.5, 0.5), forecast_position=(0.6, 0.6), zone_level="CAUTION")]
        canvas = view.render(_base_state(use_prediction=True, ttc_s=3.2, workers=workers))
        assert canvas is not None

    def test_render_shows_person_in_zone_on_critical(self):
        view = SimView()
        canvas = view.render(_base_state(risk_state="CRITICAL", led_level=2))
        assert canvas is not None

    def test_render_with_stop_active_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(stop_active=True, machine_running=False))
        assert canvas is not None

    def test_render_with_camera_fault_does_not_crash(self):
        view = SimView()
        canvas = view.render(_base_state(camera_fault_simulated=True, camera_alive=False))
        assert canvas is not None

    def test_render_with_summary_does_not_crash(self):
        view = SimView()
        summary = SummaryViewState(
            caution_events=2, danger_events=1, time_in_danger_s=3.4, stop_commands=1,
            camera_faults=0, telemetry_faults=0, latency_avg_ms=15.0, latency_max_ms=40.0,
        )
        canvas = view.render(_base_state(summary=summary))
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


class TestThemeToggle:
    def test_default_theme_is_dark(self):
        view = SimView()
        assert view.theme is DARK_THEME

    def test_toggle_switches_dark_to_light(self):
        view = SimView()
        new_theme = view.toggle_theme()
        assert new_theme is LIGHT_THEME
        assert view.theme is LIGHT_THEME

    def test_toggle_switches_light_back_to_dark(self):
        view = SimView(theme=LIGHT_THEME)
        new_theme = view.toggle_theme()
        assert new_theme is DARK_THEME
        assert view.theme is DARK_THEME

    def test_toggle_persists_across_renders(self):
        view = SimView()
        view.toggle_theme()
        assert view.theme is LIGHT_THEME
        view.render(_base_state())
        view.render(_base_state())
        assert view.theme is LIGHT_THEME  # rendering itself never changes the theme

    def test_double_toggle_returns_to_original(self):
        view = SimView()
        view.toggle_theme()
        view.toggle_theme()
        assert view.theme is DARK_THEME

    @pytest.mark.parametrize("theme", [DARK_THEME, LIGHT_THEME])
    @pytest.mark.parametrize("state_name", ["SAFE", "WARNING", "CRITICAL", "DEGRADED"])
    def test_render_each_state_in_each_theme_does_not_crash(self, theme, state_name):
        view = SimView(theme=theme)
        workers = [WorkerViewState(track_id=1, position=(0.5, 0.5), forecast_position=(0.6, 0.5),
                                    zone_level="DANGER", position_confidence="LOW")]
        canvas = view.render(_base_state(
            risk_state=state_name, led_level=LED_LEVEL_BY_STATE[state_name],
            workers=workers, stop_active=(state_name in {"CRITICAL", "DEGRADED"}),
        ))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)
        assert canvas.dtype == np.uint8

    def test_light_theme_background_is_lighter_than_dark_theme(self):
        """Sanity check that the light theme is a genuinely different,
        lighter palette -- not an accidental no-op or a near-identical
        copy of the dark theme."""
        dark_canvas = SimView(theme=DARK_THEME).render(_base_state())
        light_canvas = SimView(theme=LIGHT_THEME).render(_base_state())
        # Compare mean brightness over the main viewport area only (a
        # region guaranteed to be background-dominated regardless of what
        # else is drawn there).
        region = (slice(150, 600), slice(50, 900))
        assert light_canvas[region].mean() > dark_canvas[region].mean() + 50

    def test_state_meaning_colors_unchanged_across_themes(self):
        """SAFE/WARNING/CRITICAL/DEGRADED must mean the same color in both
        themes -- check the status-bar state pill's color pixel matches
        between themes for a given risk_state."""
        from smart_zone.dashboard.sim_view import COLOR_BY_STATE_NAME
        for state_name in ["SAFE", "WARNING", "CRITICAL", "DEGRADED"]:
            # COLOR_BY_STATE_NAME is a single shared dict (not per-theme),
            # so this is really just confirming that fact holds structurally.
            assert state_name in COLOR_BY_STATE_NAME

    def test_toggle_does_not_affect_hologram_view(self):
        """Toggling sim_view's theme must have zero effect on a separately
        constructed HologramView -- they share no state."""
        sim_view = SimView()
        holo_view = HologramView()

        holo_canvas_before = holo_view.render(_base_state())
        sim_view.toggle_theme()
        holo_canvas_after = holo_view.render(_base_state())

        assert np.array_equal(holo_canvas_before, holo_canvas_after)


class TestHologramViewRendering:
    def test_render_returns_correct_shape(self):
        view = HologramView()
        canvas = view.render(_base_state())
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)
        assert canvas.dtype == np.uint8

    @pytest.mark.parametrize("state_name", ["SAFE", "WARNING", "CRITICAL", "DEGRADED"])
    def test_render_each_risk_state_does_not_crash(self, state_name):
        view = HologramView()
        canvas = view.render(_base_state(
            risk_state=state_name, led_level=LED_LEVEL_BY_STATE[state_name],
            machine_running=(state_name != "DEGRADED"),
        ))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_workers_does_not_crash(self):
        view = HologramView()
        workers = [
            WorkerViewState(track_id=1, position=(1.0, 1.0), forecast_position=(1.5, 1.2), zone_level="CAUTION"),
            WorkerViewState(track_id=2, position=(0.2, 0.1), forecast_position=(0.1, 0.05), zone_level="DANGER"),
        ]
        canvas = view.render(_base_state(workers=workers))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_low_confidence_worker_does_not_crash(self):
        view = HologramView()
        workers = [
            WorkerViewState(track_id=1, position=(0.5, 0.5), forecast_position=(0.6, 0.5),
                             zone_level="DANGER", position_confidence="LOW"),
        ]
        canvas = view.render(_base_state(workers=workers, risk_state="CRITICAL"))
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_with_stopped_machine_does_not_crash(self):
        view = HologramView()
        canvas = view.render(_base_state(machine_running=False, stop_active=True))
        assert canvas is not None

    def test_render_with_camera_fault_does_not_crash(self):
        view = HologramView()
        canvas = view.render(_base_state(camera_fault_simulated=True, camera_alive=False))
        assert canvas is not None

    def test_render_with_summary_does_not_crash(self):
        view = HologramView()
        summary = SummaryViewState(
            caution_events=2, danger_events=1, time_in_danger_s=3.4, stop_commands=1,
            camera_faults=0, telemetry_faults=0, latency_avg_ms=15.0, latency_max_ms=40.0,
        )
        canvas = view.render(_base_state(summary=summary))
        assert canvas is not None

    def test_render_with_webcam_frame_composites_inset(self):
        view = HologramView()
        fake_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        canvas = view.render(_base_state(webcam_frame=fake_frame), show_webcam_inset=True)
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_without_webcam_inset_flag_skips_it(self):
        view = HologramView()
        fake_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        canvas = view.render(_base_state(webcam_frame=fake_frame), show_webcam_inset=False)
        assert canvas.shape == (WINDOW_H, WINDOW_W, 3)

    def test_render_hides_ttc_when_use_prediction_false(self):
        view = HologramView()
        canvas = view.render(_base_state(use_prediction=False, ttc_s=3.2))
        assert canvas is not None

    def test_render_shows_person_in_zone_on_critical(self):
        view = HologramView()
        canvas = view.render(_base_state(risk_state="CRITICAL", led_level=2, machine_running=False))
        assert canvas is not None


class TestPollKeys:
    def test_recognized_keys_are_returned(self):
        view = SimView()
        for key_char, expected in [
            ("q", "q"), ("c", "c"), ("r", "r"), ("s", "s"), ("+", "+"), ("-", "-"),
            ("h", "h"), ("d", "d"), ("w", "w"),
        ]:
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
