"""Deterministic risk state machine: SAFE / WARNING / CRITICAL / DEGRADED.

Evaluates every currently tracked worker independently by ground-plane
POSITION (predicted position + TTC), never by tracker ID, and reports the
MAXIMUM risk level across all of them. Track IDs are only used upstream
(Section 1/3) to route observations to the right Kalman filter -- by the
time a worker's state reaches this engine, it is just
(position, ttc_s, in_outer_margin, in_core) data. An ID switch never resets
the engine's own state, because the engine holds no per-ID memory at all:
each frame it looks only at the aggregate condition across "any worker,
anywhere", plus two scalar debounce timers (one per level) for the whole
system.

Hysteresis: escalation is immediate -- any qualifying condition on any
worker this frame moves the state up immediately, with no debounce.
De-escalation only happens after the triggering condition has been
continuously ABSENT for `debounce_s` seconds. This is real timer-based
hysteresis (not just a comment): `_critical_clear_since` /
`_warning_clear_since` record the first moment each condition was observed
absent, and are reset to None the instant the condition reappears.

DEGRADED overrides everything else immediately (no debounce) on any
sensor/telemetry/compute fault; the caller (app.py) forces STOP regardless
of computed risk whenever state == DEGRADED (or CRITICAL).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

DEFAULT_TTC_WARNING_S = 4.0
DEFAULT_TTC_CRITICAL_S = 1.5
DEFAULT_DEBOUNCE_S = 1.0
DEFAULT_FPS_FLOOR = 8.0


class RiskState(IntEnum):
    SAFE = 0
    WARNING = 1
    CRITICAL = 2
    DEGRADED = 3


@dataclass(frozen=True)
class WorkerObservation:
    """One tracked worker's state this frame, as seen by the risk engine --
    ground-plane position and derived quantities only, no track ID."""
    position: tuple[float, float]
    ttc_s: float | None
    in_outer_margin: bool
    in_core: bool


@dataclass(frozen=True)
class HealthStatus:
    """Sensor/telemetry/compute health inputs that can force DEGRADED."""
    camera_alive: bool
    telemetry_alive: bool
    fps: float


@dataclass(frozen=True)
class RiskAssessment:
    state: RiskState
    min_ttc_s: float | None
    degraded_reason: str | None


class RiskEngine:
    def __init__(
        self,
        ttc_warning_s: float = DEFAULT_TTC_WARNING_S,
        ttc_critical_s: float = DEFAULT_TTC_CRITICAL_S,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        fps_floor: float = DEFAULT_FPS_FLOOR,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttc_warning_s = ttc_warning_s
        self.ttc_critical_s = ttc_critical_s
        self.debounce_s = debounce_s
        self.fps_floor = fps_floor
        self._clock = clock

        self._current_state = RiskState.SAFE
        # First moment (monotonic time) each condition was observed
        # continuously absent; None while the condition is currently present.
        self._critical_clear_since: float | None = None
        self._warning_clear_since: float | None = None

    def _condition_present(self, workers: list[WorkerObservation]) -> tuple[bool, bool]:
        """Returns (critical_condition_present, warning_condition_present)
        for this frame's worker observations, independent of any state
        history or track identity.

        Assumes critical thresholds are strictly tighter than warning ones
        (ttc_critical_s < ttc_warning_s, core ellipse inset within the outer
        margin ellipse) so critical_present implies warning_present. That
        invariant is what lets CRITICAL always fall through WARNING on its
        way back down to SAFE, rather than skipping it."""
        critical = any(
            w.in_core or (w.ttc_s is not None and w.ttc_s < self.ttc_critical_s)
            for w in workers
        )
        warning = any(
            w.in_outer_margin or (w.ttc_s is not None and w.ttc_s < self.ttc_warning_s)
            for w in workers
        )
        return critical, warning

    def _degraded_reason(self, health: HealthStatus) -> str | None:
        if not health.camera_alive:
            return "camera heartbeat lost"
        if not health.telemetry_alive:
            return "machine telemetry heartbeat lost"
        if health.fps < self.fps_floor:
            return f"FPS below floor ({health.fps:.1f} < {self.fps_floor:.1f})"
        return None

    def evaluate(self, workers: list[WorkerObservation], health: HealthStatus) -> RiskAssessment:
        now = self._clock()
        min_ttc = min((w.ttc_s for w in workers if w.ttc_s is not None), default=None)

        degraded_reason = self._degraded_reason(health)
        if degraded_reason is not None:
            self._current_state = RiskState.DEGRADED
            # Debounce timers don't apply to DEGRADED; clear them so recovery
            # starts from a clean slate once health is restored.
            self._critical_clear_since = None
            self._warning_clear_since = None
            return RiskAssessment(state=RiskState.DEGRADED, min_ttc_s=min_ttc, degraded_reason=degraded_reason)

        critical_present, warning_present = self._condition_present(workers)

        if critical_present:
            self._critical_clear_since = None
        elif self._critical_clear_since is None:
            self._critical_clear_since = now

        if warning_present:
            self._warning_clear_since = None
        elif self._warning_clear_since is None:
            self._warning_clear_since = now

        self._current_state = self._next_state(now, critical_present, warning_present)
        return RiskAssessment(state=self._current_state, min_ttc_s=min_ttc, degraded_reason=None)

    def _elapsed(self, since: float | None, now: float) -> bool:
        return since is not None and (now - since) >= self.debounce_s

    def _next_state(self, now: float, critical_present: bool, warning_present: bool) -> RiskState:
        previous = self._current_state

        if critical_present:
            return RiskState.CRITICAL

        if warning_present:
            if previous == RiskState.CRITICAL:
                # Critical condition just cleared this frame, but the
                # critical debounce hasn't elapsed yet -- hold CRITICAL.
                return RiskState.CRITICAL if not self._elapsed(self._critical_clear_since, now) else RiskState.WARNING
            return RiskState.WARNING

        # Neither condition present this frame.
        if previous == RiskState.CRITICAL:
            if not self._elapsed(self._critical_clear_since, now):
                return RiskState.CRITICAL
            # Critical debounce just elapsed -- fall through to WARNING's own
            # debounce, which (since warning wasn't present either) will have
            # started clearing at the same moment critical did, at latest.
            previous = RiskState.WARNING

        if previous == RiskState.WARNING:
            if not self._elapsed(self._warning_clear_since, now):
                return RiskState.WARNING
            return RiskState.SAFE

        return RiskState.SAFE

    @property
    def current_state(self) -> RiskState:
        return self._current_state
