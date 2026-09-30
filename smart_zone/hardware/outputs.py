"""Hardware output commands sent to the ESP32 over the shared serial contract.

Serial contract (fixed, do not change):
    SPEED:<deg_per_sec> / STOP / RESUME / LED:<level> / BUZZER:<ON|OFF>

Exposes one public method per serial command (set_speed, stop, resume,
set_led, buzzer) plus apply_state(), which is what the real-time loop in
app.py actually calls once per frame: it decides which of those commands
are needed for a risk-state TRANSITION and calls the matching method(s) --
commands are only sent on transitions, never every frame, since the ESP32
side has no concept of "current state" to diff against and spamming the
serial link would be wasteful. STOP is sent immediately on any transition
INTO CRITICAL or DEGRADED; RESUME is sent on transition back to SAFE.
LED/BUZZER track the new state on every transition.

Does not open the serial port itself -- takes an already-open serial.Serial
(the same instance machine/telemetry.py reads from), consistent with that
module's constructor contract.
"""

from __future__ import annotations

import serial

from smart_zone.safety.risk_engine import RiskState

LED_LEVEL_BY_STATE = {
    RiskState.SAFE: 0,
    RiskState.WARNING: 1,
    RiskState.CRITICAL: 2,
    RiskState.DEGRADED: 3,
}

BUZZER_ON_STATES = frozenset({RiskState.CRITICAL, RiskState.DEGRADED})
STOP_STATES = frozenset({RiskState.CRITICAL, RiskState.DEGRADED})


class HardwareOutputs:
    """Sends LED/BUZZER/STOP/RESUME/SPEED commands to the ESP32."""

    def __init__(self, ser: serial.Serial) -> None:
        self._ser = ser
        self._last_state: RiskState | None = None
        self._last_buzzer_on: bool | None = None

    def _send(self, command: str) -> None:
        self._ser.write(f"{command}\n".encode("ascii"))

    def set_speed(self, deg_per_sec: float) -> None:
        self._send(f"SPEED:{deg_per_sec}")

    def stop(self) -> None:
        self._send("STOP")

    def resume(self) -> None:
        self._send("RESUME")

    def set_led(self, level: int) -> None:
        self._send(f"LED:{level}")

    def buzzer(self, on: bool) -> None:
        self._send(f"BUZZER:{'ON' if on else 'OFF'}")

    def apply_state(self, state: RiskState, buzzer_should_sound: bool = True) -> None:
        """Call once per frame with the current risk state. Only sends
        commands when `state` differs from the previously applied state.

        buzzer_should_sound lets the caller (via
        RiskAssessment.buzzer_should_sound) silence the buzzer for a "quiet"
        WARNING -- e.g. the stationary-machine case in risk_engine.py, where
        a worker in the baseline caution/danger zone is capped at WARNING
        with no audible alert. STOP/RESUME and LED are unaffected by this;
        only the buzzer command is gated on it."""
        buzzer_on = (state in BUZZER_ON_STATES) and buzzer_should_sound

        state_changed = state != self._last_state
        buzzer_changed = buzzer_on != self._last_buzzer_on

        if not state_changed and not buzzer_changed:
            return

        if state_changed:
            was_stopped = self._last_state in STOP_STATES if self._last_state is not None else False
            now_stopped = state in STOP_STATES

            self.set_led(LED_LEVEL_BY_STATE[state])

            if now_stopped and not was_stopped:
                self.stop()
            elif was_stopped and state == RiskState.SAFE:
                self.resume()

        if buzzer_changed:
            self.buzzer(buzzer_on)

        self._last_state = state
        self._last_buzzer_on = buzzer_on
