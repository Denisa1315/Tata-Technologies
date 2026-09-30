"""Deterministic risk state machine: SAFE / WARNING / CRITICAL / DEGRADED.

Evaluates every currently tracked worker independently by ground-plane
POSITION, never by tracker ID, and reports the MAXIMUM risk level across
all of them. Track IDs are only used upstream to route observations to the
right Kalman filter -- by the time a worker's state reaches this engine,
it is just per-worker geometric/derived data. An ID switch never resets
the engine's own state, because the engine holds no per-ID memory at all:
each frame it looks only at the aggregate condition across "any worker,
anywhere", plus two scalar debounce timers (one per level) for the whole
system.

Two decision modes, selected by `use_prediction`:

  - use_prediction=False (the default): position-only. Any trusted worker
    with zone_level == DANGER gives CRITICAL; otherwise any worker with
    zone_level == CAUTION gives WARNING; otherwise SAFE. The Kalman
    filter's forecast/TTC are NOT consulted at all in this mode -- Kalman
    is only a position smoother upstream (see prediction/kalman.py); using
    its forecast to decide risk would reintroduce exactly the kind of
    trajectory-extrapolation dependency this mode is meant to avoid.

  - use_prediction=True: restores the old TTC-and-forecast-based behavior
    (in_outer_margin/in_core + ttc_s thresholds), for comparison/fallback.

Hysteresis: escalation is immediate -- any qualifying condition on any
worker this frame moves the state up immediately, with no debounce.
De-escalation only happens after the triggering condition has been
continuously ABSENT for `debounce_s` seconds. This is real timer-based
hysteresis: `_critical_clear_since` / `_warning_clear_since` record the
first moment each condition was observed absent, and are reset to None
the instant the condition reappears.

DEGRADED overrides everything else immediately (no debounce) on any
sensor/telemetry/compute fault; the caller (app.py) forces STOP regardless
of computed risk whenever state == DEGRADED (or CRITICAL).

Stationary quiet mode (quiet_when_stationary, use_prediction=False only):
when the machine's tangential speed is at/below
stationary_speed_threshold_m_s, a worker merely in CAUTION or DANGER (per
the baseline circle -- see safety/zone.py) is capped at WARNING rather
than escalating to CRITICAL, UNLESS that worker is within the arm's own
physical reach radius (arm_reach_m), in which case it is a real,
physically-reachable danger and still escalates to CRITICAL normally. The
caller is expected to mark such "quiet" WARNING observations so the
hardware layer can stay silent (no buzzer) for it -- see
WorkerObservation.silent_warning and RiskAssessment.buzzer_should_sound.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from smart_zone.safety.zone import ZoneLevel

DEFAULT_TTC_WARNING_S = 4.0
DEFAULT_TTC_CRITICAL_S = 1.5
DEFAULT_DEBOUNCE_S = 1.0
DEFAULT_FPS_FLOOR = 8.0
DEFAULT_STATIONARY_SPEED_THRESHOLD_M_S = 0.05


class RiskState(IntEnum):
    SAFE = 0
    WARNING = 1
    CRITICAL = 2
    DEGRADED = 3


@dataclass(frozen=True)
class WorkerObservation:
    """One tracked worker's state this frame, as seen by the risk engine --
    ground-plane position and derived quantities only, no track ID.

    zone_level is used when use_prediction=False (the default).
    ttc_s / in_outer_margin / in_core are used only when use_prediction=True
    (the legacy TTC-and-forecast path); they're harmless to leave populated
    otherwise since the engine simply won't read them in position-only mode.

    distance_from_pivot_m is the worker's straight-line ground-plane
    distance from the machine's pivot -- used only for the stationary
    "within arm reach" check, independent of which zone ellipse they're in.
    """
    position: tuple[float, float]
    zone_level: ZoneLevel
    distance_from_pivot_m: float
    ttc_s: float | None = None
    in_outer_margin: bool = False
    in_core: bool = False


@dataclass(frozen=True)
class HealthStatus:
    """Sensor/telemetry/compute health inputs that can force DEGRADED."""
    camera_alive: bool
    telemetry_alive: bool
    fps: float


@dataclass(frozen=True)
class WorkerRiskReport:
    """Per-worker zone level, echoed back so the dashboard can label each
    worker individually (in addition to the overall aggregate state)."""
    position: tuple[float, float]
    zone_level: ZoneLevel


@dataclass(frozen=True)
class RiskAssessment:
    state: RiskState
    min_ttc_s: float | None
    degraded_reason: str | None
    worker_reports: list[WorkerRiskReport]
    # False only for a "quiet" stationary WARNING (quiet_when_stationary
    # capped a worker at WARNING rather than CRITICAL) -- tells the hardware
    # layer not to sound the buzzer for this state, per spec section 4. True
    # in every other case, including ordinary WARNING/CRITICAL/DEGRADED.
    buzzer_should_sound: bool


class RiskEngine:
    def __init__(
        self,
        use_prediction: bool = False,
        ttc_warning_s: float = DEFAULT_TTC_WARNING_S,
        ttc_critical_s: float = DEFAULT_TTC_CRITICAL_S,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        fps_floor: float = DEFAULT_FPS_FLOOR,
        quiet_when_stationary: bool = True,
        stationary_speed_threshold_m_s: float = DEFAULT_STATIONARY_SPEED_THRESHOLD_M_S,
        arm_reach_m: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.use_prediction = use_prediction
        self.ttc_warning_s = ttc_warning_s
        self.ttc_critical_s = ttc_critical_s
        self.debounce_s = debounce_s
        self.fps_floor = fps_floor
        self.quiet_when_stationary = quiet_when_stationary
        self.stationary_speed_threshold_m_s = stationary_speed_threshold_m_s
        self.arm_reach_m = arm_reach_m
        self._clock = clock

        self._current_state = RiskState.SAFE
        # First moment (monotonic time) each condition was observed
        # continuously absent; None while the condition is currently present.
        self._critical_clear_since: float | None = None
        self._warning_clear_since: float | None = None

    def _condition_present_position_only(
        self, workers: list[WorkerObservation], is_stationary: bool
    ) -> tuple[bool, bool, bool]:
        """Returns (critical_present, warning_present, is_quiet_warning) for
        the position-only (use_prediction=False) mode.

        is_quiet_warning is True iff the only reason warning_present is True
        is the stationary-quiet cap (i.e. some worker would otherwise have
        driven CRITICAL, but was capped because the machine is stationary
        and that worker is outside arm_reach_m) -- used to decide whether
        the hardware buzzer should stay silent."""
        any_danger_in_reach = False
        any_danger_out_of_reach = False
        any_caution = False

        for w in workers:
            if w.zone_level == ZoneLevel.DANGER:
                if w.distance_from_pivot_m <= self.arm_reach_m:
                    any_danger_in_reach = True
                else:
                    any_danger_out_of_reach = True
            elif w.zone_level == ZoneLevel.CAUTION:
                any_caution = True

        stationary_quiet_active = self.quiet_when_stationary and is_stationary

        if any_danger_in_reach:
            # Always a real, physically-reachable danger -- CRITICAL
            # regardless of stationary/quiet mode.
            return True, True, False

        if any_danger_out_of_reach:
            if stationary_quiet_active:
                # Capped at WARNING, silently, per spec section 4.
                return False, True, True
            return True, True, False

        if any_caution:
            is_quiet = stationary_quiet_active
            return False, True, is_quiet

        return False, False, False

    def _condition_present_prediction(self, workers: list[WorkerObservation]) -> tuple[bool, bool]:
        """Legacy TTC-and-forecast condition check (use_prediction=True).

        Assumes critical thresholds are strictly tighter than warning ones
        (ttc_critical_s < ttc_warning_s, core ellipse inset within the outer
        margin ellipse) so critical_present implies warning_present."""
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

    def evaluate(
        self,
        workers: list[WorkerObservation],
        health: HealthStatus,
        machine_tangential_speed_m_s: float = 0.0,
    ) -> RiskAssessment:
        now = self._clock()
        min_ttc = min((w.ttc_s for w in workers if w.ttc_s is not None), default=None)
        worker_reports = [WorkerRiskReport(position=w.position, zone_level=w.zone_level) for w in workers]

        degraded_reason = self._degraded_reason(health)
        if degraded_reason is not None:
            self._current_state = RiskState.DEGRADED
            # Debounce timers don't apply to DEGRADED; clear them so recovery
            # starts from a clean slate once health is restored.
            self._critical_clear_since = None
            self._warning_clear_since = None
            return RiskAssessment(
                state=RiskState.DEGRADED, min_ttc_s=min_ttc, degraded_reason=degraded_reason,
                worker_reports=worker_reports, buzzer_should_sound=True,
            )

        is_quiet_warning = False
        if self.use_prediction:
            critical_present, warning_present = self._condition_present_prediction(workers)
        else:
            is_stationary = machine_tangential_speed_m_s <= self.stationary_speed_threshold_m_s
            critical_present, warning_present, is_quiet_warning = self._condition_present_position_only(
                workers, is_stationary
            )

        if critical_present:
            self._critical_clear_since = None
        elif self._critical_clear_since is None:
            self._critical_clear_since = now

        if warning_present:
            self._warning_clear_since = None
        elif self._warning_clear_since is None:
            self._warning_clear_since = now

        self._current_state = self._next_state(now, critical_present, warning_present)

        buzzer_should_sound = not (self._current_state == RiskState.WARNING and is_quiet_warning)

        return RiskAssessment(
            state=self._current_state, min_ttc_s=min_ttc, degraded_reason=None,
            worker_reports=worker_reports, buzzer_should_sound=buzzer_should_sound,
        )

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
