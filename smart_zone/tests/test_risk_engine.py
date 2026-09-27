"""Unit tests for safety.risk_engine: state machine, hysteresis, DEGRADED override,
and track-ID independence."""

from __future__ import annotations

import pytest

from smart_zone.safety.risk_engine import (
    HealthStatus,
    RiskEngine,
    RiskState,
    WorkerObservation,
)

HEALTHY = HealthStatus(camera_alive=True, telemetry_alive=True, fps=30.0)


def _fake_clock():
    """A controllable monotonic clock for deterministic debounce tests."""
    state = {"t": 0.0}

    def now():
        return state["t"]

    def advance(dt: float):
        state["t"] += dt

    return now, advance


def _obs(x=100.0, y=100.0, ttc=None, in_margin=False, in_core=False):
    # The core ellipse is geometrically inset within the outer margin ellipse
    # (see safety.zone.compute_core_zone_geometry), so in_core=True always
    # implies in_outer_margin=True in real data -- keep that invariant here.
    return WorkerObservation(
        position=(x, y), ttc_s=ttc, in_outer_margin=in_margin or in_core, in_core=in_core
    )


NO_WORKERS: list[WorkerObservation] = []


class TestBasicEscalation:
    def test_no_workers_is_safe(self):
        engine = RiskEngine()
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.SAFE

    def test_outer_margin_triggers_warning_immediately(self):
        engine = RiskEngine()
        result = engine.evaluate([_obs(in_margin=True)], HEALTHY)
        assert result.state == RiskState.WARNING

    def test_core_triggers_critical_immediately(self):
        engine = RiskEngine()
        result = engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert result.state == RiskState.CRITICAL

    def test_low_ttc_triggers_warning(self):
        engine = RiskEngine(ttc_warning_s=4.0)
        result = engine.evaluate([_obs(ttc=3.0)], HEALTHY)
        assert result.state == RiskState.WARNING

    def test_very_low_ttc_triggers_critical(self):
        engine = RiskEngine(ttc_critical_s=1.5)
        result = engine.evaluate([_obs(ttc=1.0)], HEALTHY)
        assert result.state == RiskState.CRITICAL

    def test_escalation_has_no_debounce_delay(self):
        now, advance = _fake_clock()
        engine = RiskEngine(clock=now)
        # single frame, immediately critical -- no need to "wait" for escalation
        result = engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert result.state == RiskState.CRITICAL


class TestMaxAcrossWorkers:
    def test_reports_max_risk_across_multiple_workers(self):
        engine = RiskEngine()
        workers = [_obs(x=1, in_margin=True), _obs(x=2, in_core=True), _obs(x=3)]
        result = engine.evaluate(workers, HEALTHY)
        assert result.state == RiskState.CRITICAL

    def test_min_ttc_reported_across_workers(self):
        engine = RiskEngine()
        workers = [_obs(x=1, ttc=5.0), _obs(x=2, ttc=2.0), _obs(x=3, ttc=None)]
        result = engine.evaluate(workers, HEALTHY)
        assert result.min_ttc_s == pytest.approx(2.0)


class TestHysteresisDebounce:
    def test_does_not_deescalate_before_debounce_elapses(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.5)  # condition clears, but only 0.5s < 1.0s debounce
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.CRITICAL

    def test_deescalates_after_debounce_elapses(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert engine.current_state == RiskState.CRITICAL

        # First sample where the condition is absent starts the clear-timer
        # (we can't assume continuous absence before this sample) -- it
        # takes debounce_s *from this point* to actually de-escalate.
        engine.evaluate(NO_WORKERS, HEALTHY)
        advance(1.1)
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.SAFE

    def test_condition_reappearing_resets_the_debounce_timer(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        engine.evaluate([_obs(in_core=True)], HEALTHY)
        engine.evaluate(NO_WORKERS, HEALTHY)  # condition clears, timer starts at t=0
        assert engine.current_state == RiskState.CRITICAL  # not yet 1.0s

        advance(0.5)
        engine.evaluate([_obs(in_core=True)], HEALTHY)  # condition reappears, timer reset (cleared)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.3)  # t=0.8: condition absent again -- clear-timer restarts here, at t=0.8
        engine.evaluate(NO_WORKERS, HEALTHY)
        assert engine.current_state == RiskState.CRITICAL

        advance(0.9)  # t=1.7: only 0.9s since the restart at t=0.8 -- must still hold
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.CRITICAL

        advance(0.2)  # t=1.9: now 1.1s since the restart at t=0.8 -- may finally clear
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.SAFE

    def test_critical_falls_through_warning_on_the_way_down(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert engine.current_state == RiskState.CRITICAL

        # core clears but outer margin still triggered -> critical debounce
        # starts, but warning condition is present so it can only fall to WARNING.
        engine.evaluate([_obs(in_margin=True)], HEALTHY)
        advance(1.1)
        result = engine.evaluate([_obs(in_margin=True)], HEALTHY)
        assert result.state == RiskState.WARNING

    def test_warning_debounce_independent_of_critical(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        engine.evaluate([_obs(in_margin=True)], HEALTHY)
        assert engine.current_state == RiskState.WARNING

        advance(0.5)  # condition clears here; clear-timer starts at t=0.5
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.WARNING  # only 0s of continuous absence so far

        advance(0.6)  # t=1.1, only 0.6s of continuous absence -- still under 1.0s
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.WARNING  # not yet debounced

        advance(0.5)  # t=1.6, now 1.1s of continuous absence -- past debounce
        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.SAFE


class TestDegradedOverride:
    def test_camera_dead_forces_degraded_regardless_of_risk(self):
        engine = RiskEngine()
        health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)
        result = engine.evaluate(NO_WORKERS, health)
        assert result.state == RiskState.DEGRADED
        assert "camera" in result.degraded_reason

    def test_telemetry_dead_forces_degraded(self):
        engine = RiskEngine()
        health = HealthStatus(camera_alive=True, telemetry_alive=False, fps=30.0)
        result = engine.evaluate(NO_WORKERS, health)
        assert result.state == RiskState.DEGRADED
        assert "telemetry" in result.degraded_reason

    def test_low_fps_forces_degraded(self):
        engine = RiskEngine(fps_floor=10.0)
        health = HealthStatus(camera_alive=True, telemetry_alive=True, fps=5.0)
        result = engine.evaluate(NO_WORKERS, health)
        assert result.state == RiskState.DEGRADED
        assert "FPS" in result.degraded_reason

    def test_degraded_overrides_critical_condition(self):
        engine = RiskEngine()
        health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)
        result = engine.evaluate([_obs(in_core=True)], health)
        assert result.state == RiskState.DEGRADED

    def test_degraded_has_no_debounce_on_entry(self):
        now, advance = _fake_clock()
        engine = RiskEngine(clock=now)
        health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)
        result = engine.evaluate(NO_WORKERS, health)
        assert result.state == RiskState.DEGRADED  # immediate, first frame

    def test_recovering_from_degraded_lands_on_current_raw_level(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)
        bad_health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)

        engine.evaluate([_obs(in_core=True)], bad_health)
        assert engine.current_state == RiskState.DEGRADED

        # health restored, but a critical condition is present -- must land on
        # CRITICAL immediately, not SAFE, and not stuck in DEGRADED.
        result = engine.evaluate([_obs(in_core=True)], HEALTHY)
        assert result.state == RiskState.CRITICAL

    def test_recovering_from_degraded_to_safe_has_no_leftover_debounce(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)
        bad_health = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)

        engine.evaluate(NO_WORKERS, bad_health)
        assert engine.current_state == RiskState.DEGRADED

        result = engine.evaluate(NO_WORKERS, HEALTHY)
        assert result.state == RiskState.SAFE


class TestTrackIdIndependence:
    def test_state_does_not_glitch_when_track_id_changes_mid_scenario(self):
        """The engine receives WorkerObservation with no ID at all -- but
        simulate the realistic upstream scenario: a worker in the core is
        tracked as id=1, then id switches to id=7 (simulating a re-detect),
        while remaining at the same dangerous ground-plane position the
        whole time. The reported risk state must stay CRITICAL throughout,
        never glitching down even momentarily."""
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        # Frame 1: worker (originally track id=1 upstream) is in the core.
        result1 = engine.evaluate([_obs(x=5.0, y=5.0, in_core=True)], HEALTHY)
        assert result1.state == RiskState.CRITICAL

        advance(0.05)
        # Frame 2: same physical worker, but upstream track ID switched
        # (e.g. occlusion caused ByteTrack to reassign). The risk engine
        # never saw an ID at all -- it only ever saw ground-plane position --
        # so nothing changes from its point of view.
        result2 = engine.evaluate([_obs(x=5.01, y=5.02, in_core=True)], HEALTHY)
        assert result2.state == RiskState.CRITICAL

        advance(0.05)
        result3 = engine.evaluate([_obs(x=5.0, y=5.0, in_core=True)], HEALTHY)
        assert result3.state == RiskState.CRITICAL

    def test_worker_disappearing_and_a_new_one_appearing_elsewhere_debounces_normally(self):
        now, advance = _fake_clock()
        engine = RiskEngine(debounce_s=1.0, clock=now)

        # Frame 1: dangerous worker present (say, id=1 upstream).
        result1 = engine.evaluate([_obs(x=1.0, y=1.0, in_core=True)], HEALTHY)
        assert result1.state == RiskState.CRITICAL

        # Frame 2 (same instant): that worker is gone (track lost), a
        # completely different worker (a new id upstream) is now merely in
        # the outer margin. This is just an ordinary de-escalation from the
        # engine's point of view -- it still requires the critical condition
        # to have been continuously absent for debounce_s before dropping,
        # regardless of which track produced which frame's observations.
        result2 = engine.evaluate([_obs(x=99.0, y=99.0, in_margin=True)], HEALTHY)
        assert result2.state == RiskState.CRITICAL  # debounce not yet elapsed

        advance(1.1)
        # a further frame is needed after the debounce delay has elapsed
        # since the clear-timer above started when the condition was first
        # observed absent (result2's frame), not before.
        result3 = engine.evaluate([_obs(x=99.0, y=99.0, in_margin=True)], HEALTHY)
        assert result3.state == RiskState.WARNING  # now reflects actual max risk
