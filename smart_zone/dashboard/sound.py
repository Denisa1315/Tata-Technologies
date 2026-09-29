"""Sound feedback for the --sim dashboard.

Display/presentation only, same constraint as the rest of dashboard/: it
reacts to (state, buzzer_should_sound) values app.py already computed from
the real risk engine -- it does not import or call risk_engine, zone,
kalman, ttc, or confidence itself, and makes no decision about what state
the system is in.

Behavior:
  - Repeating beep while state == CRITICAL, using the SAME
    buzzer_should_sound signal that already gates the simulated hardware
    buzzer (hardware.sim_outputs) -- not a separate state check, so sound
    and the simulated buzzer light never disagree about when to be quiet.
    Stops immediately once CRITICAL clears (or buzzer_should_sound goes
    False for the current CRITICAL frame).
  - One short beep on WARNING ENTRY only (the transition into WARNING from
    something else), never repeating and never re-firing while WARNING
    persists. No beep at all for a "quiet" stationary WARNING (i.e. when
    buzzer_should_sound is False on that entry).

Uses `afplay` (macOS, no new dependency -- it's a system command, not a
Python package) to play a short system sound; falls back to the terminal
bell character if afplay is unavailable or fails to launch.
"""

from __future__ import annotations

import shutil
import subprocess
import time

DEFAULT_BEEP_SOUND_PATH = "/System/Library/Sounds/Ping.aiff"
CRITICAL_BEEP_INTERVAL_S = 0.6


def _play_beep(sound_path: str = DEFAULT_BEEP_SOUND_PATH) -> None:
    afplay_path = shutil.which("afplay")
    if afplay_path is not None:
        try:
            subprocess.Popen(
                [afplay_path, sound_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass
    print("\a", end="", flush=True)


class SoundController:
    def __init__(
        self,
        beep_sound_path: str = DEFAULT_BEEP_SOUND_PATH,
        critical_beep_interval_s: float = CRITICAL_BEEP_INTERVAL_S,
        play_fn=_play_beep,
    ) -> None:
        self._beep_sound_path = beep_sound_path
        self._critical_beep_interval_s = critical_beep_interval_s
        self._play_fn = play_fn

        self._last_state: str | None = None
        self._last_critical_beep_time: float | None = None

    def update(self, state: str, buzzer_should_sound: bool, now: float | None = None) -> None:
        """Call once per frame with the current risk state and the same
        buzzer_should_sound flag passed to hardware.apply_state()."""
        if now is None:
            now = time.time()

        entered_warning = state == "WARNING" and self._last_state != "WARNING"
        if entered_warning and buzzer_should_sound:
            self._play_fn(self._beep_sound_path)

        if state == "CRITICAL" and buzzer_should_sound:
            due = (
                self._last_critical_beep_time is None
                or (now - self._last_critical_beep_time) >= self._critical_beep_interval_s
            )
            if due:
                self._play_fn(self._beep_sound_path)
                self._last_critical_beep_time = now
        else:
            self._last_critical_beep_time = None

        self._last_state = state
