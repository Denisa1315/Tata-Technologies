"""Drop-in mock for MachineTelemetry -- no ESP32/serial hardware needed.

Exposes the identical interface (angle_deg / speed_deg_s / state properties,
is_alive()) so the rest of the pipeline can be built and tested before any
real machine is connected. Internally oscillates a simulated angle back and
forth between two limits at a configurable angular speed, updated in a
background thread to mirror the real 20Hz telemetry cadence.
"""

from __future__ import annotations

import threading
import time

TELEMETRY_HZ = 20.0
TELEMETRY_PERIOD_S = 1.0 / TELEMETRY_HZ


class MockMachineTelemetry:
    def __init__(
        self,
        angle_min_deg: float = -45.0,
        angle_max_deg: float = 45.0,
        angular_speed_deg_s: float = 15.0,
        start_angle_deg: float | None = None,
    ) -> None:
        if angle_min_deg >= angle_max_deg:
            raise ValueError("angle_min_deg must be < angle_max_deg")

        self._angle_min = angle_min_deg
        self._angle_max = angle_max_deg
        self._angular_speed = abs(angular_speed_deg_s)

        self._lock = threading.Lock()
        self._angle_deg = start_angle_deg if start_angle_deg is not None else angle_min_deg
        self._direction = 1.0  # +1 sweeping toward angle_max, -1 toward angle_min
        self._speed_deg_s = self._direction * self._angular_speed
        self._state = "RUNNING"
        self._last_update_monotonic = time.monotonic()

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._simulate_loop, daemon=True)
        self._thread.start()

    def _simulate_loop(self) -> None:
        prev_time = time.monotonic()
        while not self._stop_event.is_set():
            time.sleep(TELEMETRY_PERIOD_S)
            now = time.monotonic()
            dt = now - prev_time
            prev_time = now

            with self._lock:
                new_angle = self._angle_deg + self._direction * self._angular_speed * dt

                if new_angle >= self._angle_max:
                    new_angle = self._angle_max
                    self._direction = -1.0
                elif new_angle <= self._angle_min:
                    new_angle = self._angle_min
                    self._direction = 1.0

                self._angle_deg = new_angle
                self._speed_deg_s = self._direction * self._angular_speed
                self._last_update_monotonic = now

    @property
    def angle_deg(self) -> float:
        with self._lock:
            return self._angle_deg

    @property
    def speed_deg_s(self) -> float:
        with self._lock:
            return self._speed_deg_s

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def is_alive(self, max_age_s: float = 0.5) -> bool:
        with self._lock:
            last_update = self._last_update_monotonic
        return (time.monotonic() - last_update) <= max_age_s

    def close(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
