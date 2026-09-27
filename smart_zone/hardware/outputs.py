"""Hardware output commands sent to the ESP32 over the shared serial contract.

Serial contract (fixed, do not change):
    SPEED:<deg_per_sec> / STOP / RESUME / LED:<level> / BUZZER:<ON|OFF>

Commands are sent only on risk-state TRANSITIONS, never every frame -- the
ESP32 side has no concept of "current state" to diff against, so it's this
module's job not to spam the serial link. STOP is sent immediately on any
transition INTO CRITICAL or DEGRADED; RESUME is sent on transition back to
SAFE. LED/BUZZER track the new state on every transition.

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
    """Sends LED/BUZZER/STOP/RESUME commands on risk-state transitions."""

    def __init__(self, ser: serial.Serial) -> None:
        self._ser = ser
        self._last_state: RiskState | None = None

    def _send(self, command: str) -> None:
        self._ser.write(f"{command}\n".encode("ascii"))

    def apply_state(self, state: RiskState) -> None:
        """Call once per frame with the current risk state. Only sends
        commands when `state` differs from the previously applied state."""
        if state == self._last_state:
            return

        was_stopped = self._last_state in STOP_STATES if self._last_state is not None else False
        now_stopped = state in STOP_STATES

        self._send(f"LED:{LED_LEVEL_BY_STATE[state]}")
        self._send(f"BUZZER:{'ON' if state in BUZZER_ON_STATES else 'OFF'}")

        if now_stopped and not was_stopped:
            self._send("STOP")
        elif was_stopped and state == RiskState.SAFE:
            self._send("RESUME")

        self._last_state = state
