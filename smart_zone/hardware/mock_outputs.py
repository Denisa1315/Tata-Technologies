"""Console-only stand-in for hardware.outputs.HardwareOutputs -- no serial
port needed. Prints the same transition-triggered LED/BUZZER/STOP/RESUME
actions instead of writing them to a real ESP32, so the pipeline is
runnable with zero hardware connected (see app.py --mock-hardware).
"""

from __future__ import annotations

from smart_zone.hardware.outputs import BUZZER_ON_STATES, LED_LEVEL_BY_STATE, STOP_STATES
from smart_zone.safety.risk_engine import RiskState


class MockHardwareOutputs:
    def __init__(self) -> None:
        self._last_state: RiskState | None = None

    def apply_state(self, state: RiskState) -> None:
        if state == self._last_state:
            return

        was_stopped = self._last_state in STOP_STATES if self._last_state is not None else False
        now_stopped = state in STOP_STATES

        print(f"[mock-hardware] LED:{LED_LEVEL_BY_STATE[state]}")
        print(f"[mock-hardware] BUZZER:{'ON' if state in BUZZER_ON_STATES else 'OFF'}")

        if now_stopped and not was_stopped:
            print("[mock-hardware] STOP")
        elif was_stopped and state == RiskState.SAFE:
            print("[mock-hardware] RESUME")

        self._last_state = state
