"""Unit tests for hardware.sim_outputs: recorded state + forwarding to mock telemetry."""

from __future__ import annotations

import time

import pytest

from smart_zone.hardware.sim_outputs import SimHardwareOutputs
from smart_zone.machine.mock_telemetry import STATE_STOPPED, MockMachineTelemetry
from smart_zone.safety.risk_engine import RiskState


@pytest.fixture
def machine():
    m = MockMachineTelemetry(angle_min_deg=0.0, angle_max_deg=90.0, start_angle_deg=10.0)
    yield m
    m.close()


class TestSetLedAndBuzzer:
    def test_set_led_records_level(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.set_led(2)
        assert sim.led_level == 2
        assert sim.recent_actions[-1].action == "LED:2"

    def test_buzzer_records_on_and_off(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.buzzer(True)
        assert sim.buzzer_on is True
        assert sim.recent_actions[-1].action == "BUZZER:ON"

        sim.buzzer(False)
        assert sim.buzzer_on is False
        assert sim.recent_actions[-1].action == "BUZZER:OFF"


class TestStopResumeForwarding:
    def test_stop_forwards_to_mock_telemetry_and_freezes_it(self, machine):
        machine.set_speed(30.0)
        time.sleep(0.2)

        sim = SimHardwareOutputs(machine)
        sim.stop()

        assert sim.stop_active is True
        assert machine.state == STATE_STOPPED
        assert machine.speed_deg_s == pytest.approx(0.0)

        frozen_angle = machine.angle_deg
        time.sleep(0.2)
        assert machine.angle_deg == pytest.approx(frozen_angle, abs=1e-9)

    def test_resume_forwards_to_mock_telemetry_and_restarts_it(self, machine):
        machine.set_speed(30.0)
        time.sleep(0.2)

        sim = SimHardwareOutputs(machine)
        sim.stop()
        frozen_angle = machine.angle_deg

        sim.resume()
        assert sim.stop_active is False

        time.sleep(0.2)
        assert machine.angle_deg != pytest.approx(frozen_angle, abs=1e-9)

    def test_set_speed_forwards_to_mock_telemetry(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.set_speed(25.0)
        assert abs(machine.speed_deg_s) == pytest.approx(25.0, abs=1e-6)


class TestApplyStateTransitions:
    def test_apply_state_transition_into_critical_stops_the_mock(self, machine):
        machine.set_speed(30.0)
        sim = SimHardwareOutputs(machine)

        sim.apply_state(RiskState.SAFE)
        sim.apply_state(RiskState.CRITICAL)

        assert sim.stop_active is True
        assert machine.state == STATE_STOPPED

    def test_apply_state_transition_back_to_safe_resumes_the_mock(self, machine):
        machine.set_speed(30.0)
        sim = SimHardwareOutputs(machine)

        sim.apply_state(RiskState.CRITICAL)
        assert sim.stop_active is True

        sim.apply_state(RiskState.SAFE)
        assert sim.stop_active is False

    def test_apply_state_records_led_and_buzzer_changes(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.apply_state(RiskState.WARNING)

        actions = [a.action for a in sim.recent_actions]
        assert "LED:1" in actions
        assert "BUZZER:OFF" in actions

    def test_apply_state_same_state_twice_does_not_re_record(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.apply_state(RiskState.WARNING)
        n_actions_after_first = len(sim.recent_actions)

        sim.apply_state(RiskState.WARNING)
        assert len(sim.recent_actions) == n_actions_after_first

    def test_recent_actions_capped(self, machine):
        sim = SimHardwareOutputs(machine)
        for i in range(30):
            sim.set_led(i % 4)
        assert len(sim.recent_actions) <= 20


class TestBuzzerShouldSound:
    def test_buzzer_should_sound_false_keeps_critical_silent(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.apply_state(RiskState.SAFE)
        sim.apply_state(RiskState.CRITICAL, buzzer_should_sound=False)
        assert sim.buzzer_on is False
        assert sim.stop_active is True  # STOP unaffected by buzzer_should_sound

    def test_buzzer_change_alone_updates_without_state_change(self, machine):
        sim = SimHardwareOutputs(machine)
        sim.apply_state(RiskState.CRITICAL, buzzer_should_sound=True)
        assert sim.buzzer_on is True

        sim.apply_state(RiskState.CRITICAL, buzzer_should_sound=False)
        assert sim.buzzer_on is False
