"""Drop-in mock for MachineTelemetry -- no ESP32/serial hardware needed.

Exposes the identical read interface (angle_deg / speed_deg_s / state /
age_s properties, is_alive()) so the rest of the pipeline can be built and
tested before any real machine is connected. Matches the ESP32 firmware's
actual commanded behavior, not just free-running oscillation:

- set_speed(deg_per_sec): sets the sweep rate and (re)starts running from
  the current angle, bouncing between angle_min_deg/angle_max_deg.
- stop(): freezes the angle exactly where it is, reports speed 0 and
  state STOPPED. The internal commanded speed/direction is remembered but
  not applied while stopped.
- resume(): continues sweeping from the frozen angle, at the speed that
  was commanded before stop() was called (not a fresh default).

The sweep still runs on a background thread at the 20Hz telemetry cadence,
mirroring the real serial link's update rate.
"""

from __future__ import annotations

import threading
import time

TELEMETRY_HZ = 20.0
TELEMETRY_PERIOD_S = 1.0 / TELEMETRY_HZ

# Consistent with the sweep range used elsewhere (e.g. safety/zone.py demo
# scripts assume a machine that can swing broadly); default matches the
# range named in this task (30 to 150 degrees).
DEFAULT_ANGLE_MIN_DEG = 30.0
DEFAULT_ANGLE_MAX_DEG = 150.0
DEFAULT_ANGULAR_SPEED_DEG_S = 15.0

STATE_RUNNING = "RUNNING"
STATE_STOPPED = "STOPPED"


class MockMachineTelemetry:
    def __init__(
        self,
        angle_min_deg: float = DEFAULT_ANGLE_MIN_DEG,
        angle_max_deg: float = DEFAULT_ANGLE_MAX_DEG,
        angular_speed_deg_s: float = DEFAULT_ANGULAR_SPEED_DEG_S,
        start_angle_deg: float | None = None,
    ) -> None:
        if angle_min_deg >= angle_max_deg:
            raise ValueError("angle_min_deg must be < angle_max_deg")

        self._angle_min = angle_min_deg
        self._angle_max = angle_max_deg

        self._lock = threading.Lock()
        self._angle_deg = start_angle_deg if start_angle_deg is not None else angle_min_deg
        self._direction = 1.0  # +1 sweeping toward angle_max, -1 toward angle_min
        # Commanded angular speed magnitude -- what set_speed() last set, and
        # what resume() restarts at. Independent from whether we're currently
        # running or stopped.
        self._commanded_speed = abs(angular_speed_deg_s)
        self._running = True
        self._state = STATE_RUNNING
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
                if self._running:
                    new_angle = self._angle_deg + self._direction * self._commanded_speed * dt

                    if new_angle >= self._angle_max:
                        new_angle = self._angle_max
                        self._direction = -1.0
                    elif new_angle <= self._angle_min:
                        new_angle = self._angle_min
                        self._direction = 1.0

                    self._angle_deg = new_angle

                self._last_update_monotonic = now

    def set_speed(self, deg_per_sec: float) -> None:
        """Set the commanded sweep rate and (re)start running from the
        current angle. Matches ESP32 SPEED:<deg_per_sec> command semantics."""
        with self._lock:
            self._commanded_speed = abs(deg_per_sec)
            self._running = True
            self._state = STATE_RUNNING

    def stop(self) -> None:
        """Freeze the angle exactly where it is; reports speed 0, state
        STOPPED, until resume() is called. Matches ESP32 STOP semantics."""
        with self._lock:
            self._running = False
            self._state = STATE_STOPPED

    def resume(self) -> None:
        """Continue sweeping from the frozen angle at the last commanded
        speed. Matches ESP32 RESUME semantics."""
        with self._lock:
            self._running = True
            self._state = STATE_RUNNING

    def reset(self, angle_deg: float | None = None, angular_speed_deg_s: float | None = None) -> None:
        """Simulation-only convenience (no equivalent ESP32 command): snap
        back to a starting angle and commanded speed, running. Used by demo
        tooling (e.g. dashboard 'r' key) to restart a scenario -- not part
        of the fixed serial contract."""
        with self._lock:
            self._angle_deg = self._angle_min if angle_deg is None else angle_deg
            self._direction = 1.0
            if angular_speed_deg_s is not None:
                self._commanded_speed = abs(angular_speed_deg_s)
            self._running = True
            self._state = STATE_RUNNING

    @property
    def angle_deg(self) -> float:
        with self._lock:
            return self._angle_deg

    @property
    def speed_deg_s(self) -> float:
        with self._lock:
            if not self._running:
                return 0.0
            return self._direction * self._commanded_speed

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def age_s(self) -> float:
        """Seconds since the last simulated telemetry update."""
        with self._lock:
            last_update = self._last_update_monotonic
        return time.monotonic() - last_update

    def is_alive(self, max_age_s: float = 0.5) -> bool:
        return self.age_s <= max_age_s

    def close(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
