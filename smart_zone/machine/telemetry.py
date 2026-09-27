"""Real machine telemetry reader over an existing serial connection.

Serial contract (fixed, do not change):
    Commands sent to ESP32:   SPEED:<deg_per_sec> / STOP / RESUME / LED:<level> / BUZZER:<ON|OFF>
    Telemetry received @20Hz: "T,<millis>,<angle_deg>,<speed_deg_per_sec>,<state>"
"""

from __future__ import annotations

import threading
import time

import serial


class MachineTelemetry:
    """Reads telemetry lines from an already-open serial.Serial in a background
    thread. Does not open/own the port -- it's passed in so the same
    serial.Serial can be shared with hardware/outputs.py for sending commands.
    """

    def __init__(self, ser: serial.Serial) -> None:
        self._ser = ser

        self._lock = threading.Lock()
        self._angle_deg: float = 0.0
        self._speed_deg_s: float = 0.0
        self._state: str = ""
        self._last_update_monotonic: float = 0.0

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw = self._ser.readline()
            except serial.SerialException:
                time.sleep(0.05)
                continue

            if not raw:
                continue

            line = raw.decode("ascii", errors="ignore").strip()
            self._parse_line(line)

    def _parse_line(self, line: str) -> None:
        parts = line.split(",")
        if len(parts) != 5 or parts[0] != "T":
            return

        _tag, _millis, angle_str, speed_str, state = parts
        try:
            angle_deg = float(angle_str)
            speed_deg_s = float(speed_str)
        except ValueError:
            return

        with self._lock:
            self._angle_deg = angle_deg
            self._speed_deg_s = speed_deg_s
            self._state = state
            self._last_update_monotonic = time.monotonic()

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
        """Heartbeat check: False if no telemetry line has been parsed
        within max_age_s, or if none has ever arrived."""
        with self._lock:
            last_update = self._last_update_monotonic
        if last_update == 0.0:
            return False
        return (time.monotonic() - last_update) <= max_age_s

    def close(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
