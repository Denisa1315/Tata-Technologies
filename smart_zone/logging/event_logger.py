"""Offline event log: one CSV row per worker ZONE change or system STATE
change (not per frame). Local file only -- no network/AWS dependency, so
this is the source of truth even if every cloud/remote integration is down
or absent. Uses the stdlib csv module; no pandas/database dependency
needed for a simple append-only row log.

Internal risk-engine state names (SAFE/WARNING/CRITICAL/DEGRADED) are
never renamed here -- system_state always uses them verbatim. CAUTION and
DANGER are per-worker ZONE display names only (zone_level column), a
separate concept from system_state.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "events.csv"

CSV_FIELDS = [
    "timestamp",
    "worker_label",
    "ground_x",
    "ground_y",
    "distance_to_camera_m",
    "distance_to_machine_m",
    "zone_level",
    "position_confidence",
    "feet_visible",
    "machine_angle_deg",
    "machine_speed_deg_s",
    "system_state",
    "stop_issued",
    "camera_health",
    "telemetry_health",
    "pipeline_fps",
    "frame_to_decision_ms",
]


@dataclass(frozen=True)
class EventRecord:
    worker_label: str
    ground_x: float
    ground_y: float
    distance_to_camera_m: float
    distance_to_machine_m: float
    zone_level: str
    position_confidence: str
    feet_visible: bool
    machine_angle_deg: float
    machine_speed_deg_s: float
    system_state: str
    stop_issued: bool
    camera_health: bool
    telemetry_health: bool
    pipeline_fps: float
    frame_to_decision_ms: float


SYSTEM_WORKER_LABEL = "SYSTEM"


def _replace_worker_label(record: EventRecord, worker_label: str) -> EventRecord:
    return EventRecord(
        worker_label=worker_label,
        ground_x=record.ground_x, ground_y=record.ground_y,
        distance_to_camera_m=record.distance_to_camera_m,
        distance_to_machine_m=record.distance_to_machine_m,
        zone_level=record.zone_level, position_confidence=record.position_confidence,
        feet_visible=record.feet_visible,
        machine_angle_deg=record.machine_angle_deg, machine_speed_deg_s=record.machine_speed_deg_s,
        system_state=record.system_state, stop_issued=record.stop_issued,
        camera_health=record.camera_health, telemetry_health=record.telemetry_health,
        pipeline_fps=record.pipeline_fps, frame_to_decision_ms=record.frame_to_decision_ms,
    )


class TransitionTracker:
    """Decides which per-worker rows are actually loggable this frame: a
    row is emitted for a worker only when THEIR OWN zone_level changes, or
    when the overall system_state changes and that worker's row happens to
    be the one riding along with it. A system_state change with zero
    workers present (e.g. a camera fault) still gets exactly one row,
    using worker_label="SYSTEM" as a placeholder.

    Holds no risk-decision logic of its own -- purely a "did this change
    since last frame" tracker, keyed by worker_label.
    """

    def __init__(self) -> None:
        self._last_zone_by_worker: dict[str, str] = {}
        self._last_system_state: str | None = None

    def rows_to_log(
        self,
        worker_rows: list[EventRecord],
        system_state: str,
        system_only_record: EventRecord | None = None,
    ) -> list[EventRecord]:
        """Given this frame's fully-populated EventRecord for every
        currently-tracked worker (system_state already filled in on all of
        them) plus the current system_state, return the subset that should
        actually be written this frame.

        system_only_record is the row to use if a system_state change needs
        logging but there are zero workers to attribute it to (e.g. a
        camera fault with an empty scene) -- the caller builds it with the
        actual current health/fps/latency values (worker_label is forced to
        SYSTEM_WORKER_LABEL regardless of what the caller set)."""
        # A change is only meaningful relative to a PREVIOUS observed state
        # -- the very first call has no prior baseline to differ from, so
        # it must not itself count as a "state change" needing a row (a
        # worker's first sighting is still logged, via the per-worker check
        # below, since a worker appearing at all is itself informative).
        system_state_changed = (
            self._last_system_state is not None and system_state != self._last_system_state
        )
        self._last_system_state = system_state

        current_labels = {r.worker_label for r in worker_rows}
        to_log: list[EventRecord] = []
        system_row_emitted = False

        for record in worker_rows:
            zone_changed = self._last_zone_by_worker.get(record.worker_label) != record.zone_level
            self._last_zone_by_worker[record.worker_label] = record.zone_level

            if zone_changed or (system_state_changed and not system_row_emitted):
                to_log.append(record)
                if system_state_changed:
                    system_row_emitted = True

        # Drop bookkeeping for workers no longer tracked, so a track ID
        # (or worker_label) reused later starts fresh rather than being
        # compared against stale history.
        for stale_label in set(self._last_zone_by_worker) - current_labels:
            del self._last_zone_by_worker[stale_label]

        if system_state_changed and not system_row_emitted and not worker_rows:
            if system_only_record is None:
                raise ValueError(
                    "system_state changed with zero workers present -- "
                    "system_only_record is required to log this transition"
                )
            to_log.append(_replace_worker_label(system_only_record, SYSTEM_WORKER_LABEL))

        return to_log


class EventLogger:
    def __init__(self, log_path: Path = DEFAULT_LOG_PATH) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        is_new_file = not self.log_path.exists() or self.log_path.stat().st_size == 0
        if is_new_file:
            with open(self.log_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()

    def log_event(self, record: EventRecord) -> None:
        row = {
            "timestamp": time.time(),
            "worker_label": record.worker_label,
            "ground_x": f"{record.ground_x:.3f}",
            "ground_y": f"{record.ground_y:.3f}",
            "distance_to_camera_m": f"{record.distance_to_camera_m:.3f}",
            "distance_to_machine_m": f"{record.distance_to_machine_m:.3f}",
            "zone_level": record.zone_level,
            "position_confidence": record.position_confidence,
            "feet_visible": record.feet_visible,
            "machine_angle_deg": f"{record.machine_angle_deg:.2f}",
            "machine_speed_deg_s": f"{record.machine_speed_deg_s:.2f}",
            "system_state": record.system_state,
            "stop_issued": record.stop_issued,
            "camera_health": record.camera_health,
            "telemetry_health": record.telemetry_health,
            "pipeline_fps": f"{record.pipeline_fps:.2f}",
            "frame_to_decision_ms": f"{record.frame_to_decision_ms:.2f}",
        }
        with open(self.log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)
