"""Unit tests for machine.mock_telemetry: commanded speed/stop/resume behavior
matching the ESP32 firmware's actual semantics."""

from __future__ import annotations

import time

import pytest

from smart_zone.machine.mock_telemetry import (
    STATE_RUNNING,
    STATE_STOPPED,
    MockMachineTelemetry,
)


class TestSetSpeed:
    def test_set_speed_starts_running_and_reports_state(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0)
        machine.set_speed(20.0)
        try:
            assert machine.state == STATE_RUNNING
            assert machine.speed_deg_s == pytest.approx(20.0, abs=1e-6)
        finally:
            machine.close()

    def test_angle_advances_while_running(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0, start_angle_deg=10.0)
        machine.set_speed(30.0)
        try:
            start_angle = machine.angle_deg
            time.sleep(0.3)
            assert machine.angle_deg > start_angle
        finally:
            machine.close()


class TestStop:
    def test_stop_freezes_angle_and_reports_zero_speed(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0, start_angle_deg=10.0)
        machine.set_speed(30.0)
        time.sleep(0.3)
        try:
            machine.stop()
            frozen_angle = machine.angle_deg
            assert machine.speed_deg_s == pytest.approx(0.0)
            assert machine.state == STATE_STOPPED

            time.sleep(0.3)  # angle must not move at all while stopped
            assert machine.angle_deg == pytest.approx(frozen_angle, abs=1e-9)
            assert machine.speed_deg_s == pytest.approx(0.0)
        finally:
            machine.close()


class TestResume:
    def test_resume_continues_from_frozen_angle_at_last_commanded_speed(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0, start_angle_deg=10.0)
        machine.set_speed(30.0)
        time.sleep(0.3)
        try:
            machine.stop()
            frozen_angle = machine.angle_deg

            machine.resume()
            assert machine.state == STATE_RUNNING
            # resumes at the speed that was commanded before stop(), not a
            # fresh/default speed
            assert abs(machine.speed_deg_s) == pytest.approx(30.0, abs=1e-6)

            time.sleep(0.3)
            assert machine.angle_deg != pytest.approx(frozen_angle, abs=1e-9)
        finally:
            machine.close()

    def test_resume_without_prior_stop_is_a_noop_change(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0)
        machine.set_speed(15.0)
        try:
            machine.resume()
            assert machine.state == STATE_RUNNING
        finally:
            machine.close()


class TestHeartbeat:
    def test_age_s_and_is_alive_track_recent_updates(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0)
        try:
            time.sleep(0.15)
            assert machine.age_s < 0.5
            assert machine.is_alive(max_age_s=0.5) is True
        finally:
            machine.close()

    def test_is_alive_false_after_close(self):
        machine = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0)
        machine.close()
        time.sleep(0.6)
        assert machine.is_alive(max_age_s=0.5) is False


class TestSweepBounds:
    def test_raises_on_invalid_bounds(self):
        with pytest.raises(ValueError):
            MockMachineTelemetry(angle_min_deg=100.0, angle_max_deg=50.0)

    def test_default_bounds_match_spec(self):
        machine = MockMachineTelemetry()
        try:
            assert machine._angle_min == pytest.approx(30.0)
            assert machine._angle_max == pytest.approx(150.0)
        finally:
            machine.close()
