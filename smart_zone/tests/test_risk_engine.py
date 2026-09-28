"""Unit tests for safety.risk_engine: position-only state machine, hysteresis,
DEGRADED override, stationary quiet mode, and track-ID independence."""

from __future__ import annotations

import pytest

from smart_zone.safety.risk_engine import (
    HealthStatus,
    RiskEngine,
    RiskState,
    WorkerObservation,
)
from smart_zone.safety.zone import ZoneLevel

HEALTHY = HealthStatus(camera_alive=True, telemetry_alive=True, fps=30.0)
ARM_REACH_M = 3.0


def _fake_clock():
    state = {"t": 0.0}

    def now():
        return state["t"]

    def advance(dt: float):
        state["t"] += dt

    return now, advance


def _obs(x=100.0, y=100.0, zone_level=ZoneLevel.OUTSIDE, distance=100.0):
    return WorkerObservation(position=(x, y), zone_level=zone_level, distance_from_pivot_m=distance)


NO_WORKERS: list[WorkerObservation] = []


class TestBasicEscalationPositionOnly:
    def test_no_workers_is_safe(self):
        engine = RiskEngine(use_prediction=False)
        result = engine.evaluate(NO_WORKERS, HEALTHY, machine_tangential_speed_m_s=1.0)
        assert result.state == RiskState.SAFE

    def test_caution_triggers_warning_immediately(self):
        engine = RiskEngine(use_prediction=False)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.CAUTION, distance=10.0)], HEALTHY, 1.0)
        assert result.state == RiskState.WARNING

    def test_danger_triggers_critical_immediately(self):
        engine = RiskEngine(use_prediction=False, arm_reach_m=ARM_REACH_M)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL

    def test_escalation_has_no_debounce_delay(self):
        now, _ = _fake_clock()
        engine = RiskEngine(use_prediction=False, clock=now, arm_reach_m=ARM_REACH_M)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL


class TestMaxAcrossWorkers:
    def test_reports_max_risk_across_multiple_workers(self):
        engine = RiskEngine(use_prediction=False, arm_reach_m=ARM_REACH_M)
        workers = [
            _obs(x=1, zone_level=ZoneLevel.CAUTION, distance=5.0),
            _obs(x=2, zone_level=ZoneLevel.DANGER, distance=1.0),
            _obs(x=3, zone_level=ZoneLevel.OUTSIDE, distance=50.0),
        ]
        result = engine.evaluate(workers, HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL

    def test_per_worker_zone_levels_reported(self):
        engine = RiskEngine(use_prediction=False, arm_reach_m=ARM_REACH_M)
        workers = [
            _obs(x=1, zone_level=ZoneLevel.CAUTION, distance=5.0),
            _obs(x=2, zone_level=ZoneLevel.DANGER, distance=1.0),
        ]
        result = engine.evaluate(workers, HEALTHY, 1.0)
        levels = {(r.position, r.zone_level) for r in result.worker_reports}
        assert ((1, 100.0), ZoneLevel.CAUTION) in levels
        assert ((2, 100.0), ZoneLevel.DANGER) in levels


class TestHysteresisDebounce:
    def test_does_not_deescalate_before_debounce_elapses(self):
        now, advance = _fake_clock()
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, clock=now, arm_reach_m=ARM_REACH_M)

        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.5)
        result = engine.evaluate(NO_WORKERS, HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL

    def test_deescalates_after_debounce_elapses(self):
        now, advance = _fake_clock()
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, clock=now, arm_reach_m=ARM_REACH_M)

        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        engine.evaluate(NO_WORKERS, HEALTHY, 1.0)  # first observed absent, starts the clear-timer

        advance(1.1)
        result = engine.evaluate(NO_WORKERS, HEALTHY, 1.0)
        assert result.state == RiskState.SAFE

    def test_condition_reappearing_resets_the_debounce_timer(self):
        now, advance = _fake_clock()
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, clock=now, arm_reach_m=ARM_REACH_M)

        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        engine.evaluate(NO_WORKERS, HEALTHY, 1.0)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.5)
        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.3)
        engine.evaluate(NO_WORKERS, HEALTHY, 1.0)  # absence re-observed, timer restarts here
        advance(0.9)
        result = engine.evaluate(NO_WORKERS, HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL

        advance(0.2)
        result = engine.evaluate(NO_WORKERS, HEALTHY, 1.0)
        assert result.state == RiskState.SAFE

    def test_critical_falls_through_warning_on_the_way_down(self):
        now, advance = _fake_clock()
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, clock=now, arm_reach_m=ARM_REACH_M)

        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert engine.current_state == RiskState.CRITICAL

        engine.evaluate([_obs(zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY, 1.0)
        advance(1.1)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY, 1.0)
        assert result.state == RiskState.WARNING


class TestDegradedOverride:
    def test_camera_dead_forces_degraded_regardless_of_risk(self):
        engine = RiskEngine(use_prediction=False)
        health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)
        result = engine.evaluate(NO_WORKERS, health, 1.0)
        assert result.state == RiskState.DEGRADED
        assert "camera" in result.degraded_reason

    def test_telemetry_dead_forces_degraded(self):
        engine = RiskEngine(use_prediction=False)
        health = HealthStatus(camera_alive=True, telemetry_alive=False, fps=30.0)
        result = engine.evaluate(NO_WORKERS, health, 1.0)
        assert result.state == RiskState.DEGRADED

    def test_low_fps_forces_degraded(self):
        engine = RiskEngine(use_prediction=False, fps_floor=10.0)
        health = HealthStatus(camera_alive=True, telemetry_alive=True, fps=5.0)
        result = engine.evaluate(NO_WORKERS, health, 1.0)
        assert result.state == RiskState.DEGRADED

    def test_degraded_overrides_danger_condition(self):
        engine = RiskEngine(use_prediction=False, arm_reach_m=ARM_REACH_M)
        health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], health, 1.0)
        assert result.state == RiskState.DEGRADED

    def test_recovering_from_degraded_lands_on_current_raw_level(self):
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, arm_reach_m=ARM_REACH_M)
        bad_health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)

        engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], bad_health, 1.0)
        assert engine.current_state == RiskState.DEGRADED

        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL


class TestStationaryQuietMode:
    def test_danger_within_arm_reach_is_critical_even_when_stationary(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0)
        # stationary: tangential speed below threshold
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.0)
        assert result.state == RiskState.CRITICAL
        assert result.buzzer_should_sound is True

    def test_danger_outside_arm_reach_capped_at_warning_when_stationary(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=10.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.0)
        assert result.state == RiskState.WARNING

    def test_capped_warning_is_silent(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=10.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.0)
        assert result.buzzer_should_sound is False

    def test_caution_while_stationary_is_also_silent_warning(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.0)
        assert result.state == RiskState.WARNING
        assert result.buzzer_should_sound is False

    def test_ordinary_warning_while_moving_is_not_silent(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY,
                                   machine_tangential_speed_m_s=1.0)
        assert result.state == RiskState.WARNING
        assert result.buzzer_should_sound is True

    def test_quiet_mode_disabled_escalates_normally_even_stationary(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=False, arm_reach_m=3.0)
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=10.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.0)
        assert result.state == RiskState.CRITICAL
        assert result.buzzer_should_sound is True

    def test_stationary_threshold_respected(self):
        engine = RiskEngine(use_prediction=False, quiet_when_stationary=True, arm_reach_m=3.0,
                             stationary_speed_threshold_m_s=0.1)
        # speed just above threshold -> not stationary -> normal escalation
        result = engine.evaluate([_obs(zone_level=ZoneLevel.DANGER, distance=10.0)], HEALTHY,
                                   machine_tangential_speed_m_s=0.2)
        assert result.state == RiskState.CRITICAL


class TestUsePredictionLegacyMode:
    def test_ttc_and_forecast_mode_still_works(self):
        engine = RiskEngine(use_prediction=True, ttc_critical_s=1.5, ttc_warning_s=4.0)
        obs = WorkerObservation(
            position=(1.0, 1.0), zone_level=ZoneLevel.OUTSIDE, distance_from_pivot_m=1.0,
            ttc_s=0.5, in_outer_margin=True, in_core=True,
        )
        result = engine.evaluate([obs], HEALTHY, 1.0)
        assert result.state == RiskState.CRITICAL

    def test_ttc_mode_ignores_zone_level(self):
        # zone_level says DANGER but in_core/in_outer_margin/ttc all say safe
        # -- use_prediction=True must ignore zone_level entirely.
        engine = RiskEngine(use_prediction=True)
        obs = WorkerObservation(
            position=(1.0, 1.0), zone_level=ZoneLevel.DANGER, distance_from_pivot_m=1.0,
            ttc_s=None, in_outer_margin=False, in_core=False,
        )
        result = engine.evaluate([obs], HEALTHY, 1.0)
        assert result.state == RiskState.SAFE


class TestTrackIdIndependence:
    def test_state_does_not_glitch_when_track_id_changes_mid_scenario(self):
        """The engine receives WorkerObservation with no ID at all. Simulate
        the realistic upstream scenario: a worker in DANGER is tracked as
        id=1, then the track ID switches (e.g. re-detect after occlusion),
        while remaining at the same dangerous ground-plane position. The
        reported risk state must stay CRITICAL throughout."""
        engine = RiskEngine(use_prediction=False, arm_reach_m=ARM_REACH_M)

        result1 = engine.evaluate([_obs(x=5.0, y=5.0, zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result1.state == RiskState.CRITICAL

        # "track ID switched" upstream -- the engine never saw an ID at all,
        # so nothing here changes from its point of view.
        result2 = engine.evaluate([_obs(x=5.01, y=5.02, zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result2.state == RiskState.CRITICAL

        result3 = engine.evaluate([_obs(x=5.0, y=5.0, zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result3.state == RiskState.CRITICAL

    def test_worker_disappearing_and_a_new_one_appearing_elsewhere_debounces_normally(self):
        now, advance = _fake_clock()
        engine = RiskEngine(use_prediction=False, debounce_s=1.0, clock=now, arm_reach_m=ARM_REACH_M)

        result1 = engine.evaluate([_obs(x=1.0, y=1.0, zone_level=ZoneLevel.DANGER, distance=1.0)], HEALTHY, 1.0)
        assert result1.state == RiskState.CRITICAL

        result2 = engine.evaluate([_obs(x=99.0, y=99.0, zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY, 1.0)
        assert result2.state == RiskState.CRITICAL  # debounce not yet elapsed

        advance(1.1)
        result3 = engine.evaluate([_obs(x=99.0, y=99.0, zone_level=ZoneLevel.CAUTION, distance=5.0)], HEALTHY, 1.0)
        assert result3.state == RiskState.WARNING
