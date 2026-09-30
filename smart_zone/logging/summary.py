"""End-of-run summary: caution/danger event counts, total time in danger,
STOP command count, camera/telemetry fault counts, and rolling
frame-to-decision latency (average + max). Printed on exit and exposed to
the dashboard (same object, no separate computation).

Holds no risk-decision logic -- purely a running tally driven by events
the caller (app.py) already computed. No latency number is ever
hardcoded: frame_to_decision_ms values are recorded verbatim from the
caller's own wall-clock measurement each frame (see LatencyTracker).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class LatencyTracker:
    """Rolling average and maximum of frame-to-decision latency (ms),
    across every frame observed. No hardcoded latency value anywhere --
    every sample comes from the caller's own timing measurement."""

    def __init__(self) -> None:
        self._count = 0
        self._sum_ms = 0.0
        self._max_ms = 0.0

    def record(self, latency_ms: float) -> None:
        self._count += 1
        self._sum_ms += latency_ms
        if latency_ms > self._max_ms:
            self._max_ms = latency_ms

    @property
    def average_ms(self) -> float:
        if self._count == 0:
            return 0.0
        return self._sum_ms / self._count

    @property
    def max_ms(self) -> float:
        return self._max_ms

    @property
    def sample_count(self) -> int:
        return self._count


@dataclass
class RunSummary:
    caution_events: int = 0
    danger_events: int = 0
    time_in_danger_s: float = 0.0
    stop_commands: int = 0
    camera_faults: int = 0
    telemetry_faults: int = 0
    latency: LatencyTracker = field(default_factory=LatencyTracker)

    _caution_active: bool = field(default=False, repr=False)
    _last_danger_start: float | None = field(default=None, repr=False)
    _last_camera_alive: bool | None = field(default=None, repr=False)
    _last_telemetry_alive: bool | None = field(default=None, repr=False)
    _last_stop_active: bool = field(default=False, repr=False)

    def record_frame(
        self,
        now_s: float,
        any_worker_in_caution: bool,
        any_worker_in_danger: bool,
        stop_active: bool,
        camera_alive: bool,
        telemetry_alive: bool,
        frame_to_decision_ms: float,
    ) -> None:
        """Call once per frame with this frame's derived flags. Counts an
        "event" the moment the condition first becomes true (a rising
        edge), not once per frame it stays true, and accumulates
        time_in_danger_s only while any_worker_in_danger is continuously
        true, using wall-clock deltas between calls."""
        if any_worker_in_caution and not self._caution_active:
            self.caution_events += 1
        self._caution_active = any_worker_in_caution

        if any_worker_in_danger:
            is_new_danger = self._last_danger_start is None
            if is_new_danger:
                self.danger_events += 1
                self._last_danger_start = now_s
            else:
                self.time_in_danger_s += now_s - self._last_danger_start
                self._last_danger_start = now_s
        else:
            self._last_danger_start = None

        if stop_active and not self._last_stop_active:
            self.stop_commands += 1
        self._last_stop_active = stop_active

        if self._last_camera_alive is not None and self._last_camera_alive and not camera_alive:
            self.camera_faults += 1
        self._last_camera_alive = camera_alive

        if self._last_telemetry_alive is not None and self._last_telemetry_alive and not telemetry_alive:
            self.telemetry_faults += 1
        self._last_telemetry_alive = telemetry_alive

        self.latency.record(frame_to_decision_ms)

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("Smart-Zone Edge Guardian -- run summary")
        print("=" * 60)
        print(f"  CAUTION events:          {self.caution_events}")
        print(f"  DANGER events:           {self.danger_events}")
        print(f"  Total time in DANGER:    {self.time_in_danger_s:.1f}s")
        print(f"  STOP commands issued:    {self.stop_commands}")
        print(f"  Camera faults:           {self.camera_faults}")
        print(f"  Telemetry faults:        {self.telemetry_faults}")
        print(f"  frame_to_decision_ms:    avg={self.latency.average_ms:.1f}  max={self.latency.max_ms:.1f}  "
              f"(n={self.latency.sample_count})")
        print("=" * 60)
