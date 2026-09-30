"""Unit tests for hardware.outputs: transition-only command sends, STOP/RESUME."""

from __future__ import annotations

from smart_zone.hardware.outputs import HardwareOutputs
from smart_zone.safety.risk_engine import RiskState


class FakeSerial:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data.decode("ascii").strip())


class TestHardwareOutputs:
    def test_sends_led_and_buzzer_on_first_state(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.SAFE)
        assert "LED:0" in ser.sent
        assert "BUZZER:OFF" in ser.sent
        assert "STOP" not in ser.sent
        assert "RESUME" not in ser.sent

    def test_does_not_resend_on_repeated_same_state(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.WARNING)
        ser.sent.clear()

        outputs.apply_state(RiskState.WARNING)
        assert ser.sent == []

    def test_transition_into_critical_sends_stop(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.SAFE)
        ser.sent.clear()

        outputs.apply_state(RiskState.CRITICAL)
        assert "STOP" in ser.sent
        assert "LED:2" in ser.sent
        assert "BUZZER:ON" in ser.sent

    def test_transition_into_degraded_sends_stop(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.SAFE)
        ser.sent.clear()

        outputs.apply_state(RiskState.DEGRADED)
        assert "STOP" in ser.sent

    def test_transition_back_to_safe_sends_resume(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.CRITICAL)
        ser.sent.clear()

        outputs.apply_state(RiskState.SAFE)
        assert "RESUME" in ser.sent

    def test_critical_to_warning_does_not_resend_stop_or_resume(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.CRITICAL)
        ser.sent.clear()

        # still not SAFE -- must not RESUME, and machine is already stopped
        # so must not re-send STOP either.
        outputs.apply_state(RiskState.WARNING)
        assert "STOP" not in ser.sent
        assert "RESUME" not in ser.sent
        assert "LED:1" in ser.sent

    def test_critical_to_degraded_does_not_resend_stop(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.CRITICAL)
        ser.sent.clear()

        outputs.apply_state(RiskState.DEGRADED)
        assert "STOP" not in ser.sent  # already stopped, no need to resend

    def test_warning_to_safe_does_not_send_resume(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.WARNING)
        ser.sent.clear()

        # was never actually stopped (WARNING isn't a STOP_STATE), so no
        # RESUME should be sent going back to SAFE.
        outputs.apply_state(RiskState.SAFE)
        assert "RESUME" not in ser.sent


class TestBuzzerShouldSound:
    def test_critical_with_buzzer_should_sound_false_stays_silent(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        # Start from a state where the buzzer was actually on, so the
        # transition to a silenced CRITICAL is a real, observable change.
        outputs.apply_state(RiskState.CRITICAL, buzzer_should_sound=True)
        outputs.apply_state(RiskState.SAFE)
        outputs.apply_state(RiskState.CRITICAL, buzzer_should_sound=True)
        ser.sent.clear()

        outputs.apply_state(RiskState.SAFE)  # buzzer off, state resets
        outputs.apply_state(RiskState.CRITICAL, buzzer_should_sound=False)
        assert "BUZZER:ON" not in ser.sent
        assert "STOP" in ser.sent  # STOP is unaffected by buzzer_should_sound

    def test_buzzer_change_alone_sends_command_even_without_state_change(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.CRITICAL, buzzer_should_sound=True)
        ser.sent.clear()

        # state stays CRITICAL, but buzzer_should_sound flips off -- must
        # still send the buzzer update even with no state transition (and
        # must not resend LED/STOP, which are unchanged).
        outputs.apply_state(RiskState.CRITICAL, buzzer_should_sound=False)
        assert "BUZZER:OFF" in ser.sent
        assert "LED:2" not in ser.sent  # LED unchanged, no need to resend
        assert "STOP" not in ser.sent  # already stopped, no need to resend

    def test_no_change_at_all_sends_nothing(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.WARNING, buzzer_should_sound=True)
        ser.sent.clear()

        outputs.apply_state(RiskState.WARNING, buzzer_should_sound=True)
        assert ser.sent == []

    def test_default_buzzer_should_sound_is_true(self):
        ser = FakeSerial()
        outputs = HardwareOutputs(ser)
        outputs.apply_state(RiskState.CRITICAL)  # no buzzer_should_sound arg
        assert "BUZZER:ON" in ser.sent
