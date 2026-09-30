"""Simulated hardware outputs -- same public methods as hardware.outputs.HardwareOutputs
(set_speed, stop, resume, set_led, buzzer, apply_state), but instead of
writing to a real serial port it stores the current output state in
readable attributes and forwards motion commands (stop/resume/set_speed)
to a MockMachineTelemetry so the simulated arm actually freezes and
resumes, matching what the real ESP32 would physically do.

Used by app.py's --sim mode: mock telemetry + sim outputs together give a
fully in-process simulation of the whole hardware loop, no serial port and
no real machine, but still behaviorally faithful (STOP really stops the
simulated arm, not just a printed message).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from smart_zone.hardware.outputs import BUZZER_ON_STATES, LED_LEVEL_BY_STATE, STOP_STATES
from smart_zone.machine.mock_telemetry import MockMachineTelemetry
from smart_zone.safety.risk_engine import RiskState

MAX_RECENT_ACTIONS = 20


@dataclass(frozen=True)
class RecordedAction:
    timestamp: float
    action: str


class SimHardwareOutputs:
    def __init__(self, mock_telemetry: MockMachineTelemetry) -> None:
        self._mock_telemetry = mock_telemetry
        self._last_state: RiskState | None = None
        self._last_buzzer_on: bool | None = None

        self.led_level: int = LED_LEVEL_BY_STATE[RiskState.SAFE]
        self.buzzer_on: bool = False
        self.stop_active: bool = False
        self.recent_actions: list[RecordedAction] = []

    def _record(self, action: str) -> None:
        self.recent_actions.append(RecordedAction(timestamp=time.time(), action=action))
        if len(self.recent_actions) > MAX_RECENT_ACTIONS:
            self.recent_actions.pop(0)

    def set_speed(self, deg_per_sec: float) -> None:
        self._mock_telemetry.set_speed(deg_per_sec)
        self._record(f"SPEED:{deg_per_sec}")

    def stop(self) -> None:
        self._mock_telemetry.stop()
        self.stop_active = True
        self._record("STOP")

    def resume(self) -> None:
        self._mock_telemetry.resume()
        self.stop_active = False
        self._record("RESUME")

    def set_led(self, level: int) -> None:
        self.led_level = level
        self._record(f"LED:{level}")

    def buzzer(self, on: bool) -> None:
        self.buzzer_on = on
        self._record(f"BUZZER:{'ON' if on else 'OFF'}")

    def apply_state(self, state: RiskState, buzzer_should_sound: bool = True) -> None:
        """Call once per frame with the current risk state. Only records/
        forwards commands when `state` or the buzzer decision differs from
        what was previously applied -- identical logic to
        HardwareOutputs.apply_state (see its docstring re: buzzer_should_sound
        for the stationary "quiet WARNING" case)."""
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
