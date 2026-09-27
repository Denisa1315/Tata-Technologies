"""Offline event log: one CSV row per risk-state TRANSITION (not per frame).

Local file only -- no network/AWS dependency, so this is the source of
truth even if every cloud/remote integration is down or absent. Uses the
stdlib csv module; no pandas/database dependency needed for a simple
append-only row log.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "events.csv"

CSV_FIELDS = [
    "timestamp",
    "state",
    "ttc_s",
    "worker_count",
    "machine_angle_deg",
    "machine_speed_deg_s",
    "camera_health",
]


@dataclass(frozen=True)
class EventRecord:
    state: str
    ttc_s: float | None
    worker_count: int
    machine_angle_deg: float
    machine_speed_deg_s: float
    camera_health: bool


class EventLogger:
    def __init__(self, log_path: Path = DEFAULT_LOG_PATH) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        is_new_file = not self.log_path.exists() or self.log_path.stat().st_size == 0
        if is_new_file:
            with open(self.log_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()

    def log_transition(self, record: EventRecord) -> None:
        row = {
            "timestamp": time.time(),
            "state": record.state,
            "ttc_s": "" if record.ttc_s is None else f"{record.ttc_s:.3f}",
            "worker_count": record.worker_count,
            "machine_angle_deg": f"{record.machine_angle_deg:.2f}",
            "machine_speed_deg_s": f"{record.machine_speed_deg_s:.2f}",
            "camera_health": record.camera_health,
        }
        with open(self.log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(row)
