"""Unit tests for logging.event_logger: CSV schema, transition-only row
selection (per-worker zone change or system state change, never per frame)."""

from __future__ import annotations

import csv

from smart_zone.logging.event_logger import (
    CSV_FIELDS,
    SYSTEM_WORKER_LABEL,
    EventLogger,
    EventRecord,
    TransitionTracker,
)


def _record(worker_label="track_1", zone_level="OUTSIDE", system_state="SAFE", **overrides):
    defaults = dict(
        worker_label=worker_label, ground_x=1.0, ground_y=1.0,
        distance_to_camera_m=2.0, distance_to_machine_m=1.0,
        zone_level=zone_level, position_confidence="HIGH", feet_visible=True,
        machine_angle_deg=0.0, machine_speed_deg_s=0.0,
        system_state=system_state, stop_issued=False,
        camera_health=True, telemetry_health=True,
        pipeline_fps=25.0, frame_to_decision_ms=15.0,
    )
    defaults.update(overrides)
    return EventRecord(**defaults)


class TestEventLoggerCSV:
    def test_creates_file_with_header_if_missing(self, tmp_path):
        log_path = tmp_path / "events.csv"
        EventLogger(log_path=log_path)
        with open(log_path) as f:
            header = next(csv.reader(f))
        assert header == CSV_FIELDS

    def test_logs_one_row_per_call(self, tmp_path):
        log_path = tmp_path / "events.csv"
        logger = EventLogger(log_path=log_path)
        logger.log_event(_record(zone_level="CAUTION"))
        logger.log_event(_record(zone_level="DANGER"))

        with open(log_path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["zone_level"] == "CAUTION"
        assert rows[1]["zone_level"] == "DANGER"

    def test_reopening_existing_logger_does_not_duplicate_header_or_truncate(self, tmp_path):
        log_path = tmp_path / "events.csv"
        EventLogger(log_path=log_path).log_event(_record())
        EventLogger(log_path=log_path).log_event(_record())  # simulates app restart

        with open(log_path) as f:
            all_rows = list(csv.reader(f))
        header_rows = [r for r in all_rows if r == CSV_FIELDS]
        assert len(header_rows) == 1
        assert len(all_rows) == 3  # 1 header + 2 data rows


class TestTransitionTrackerZoneChange:
    def test_first_sighting_of_a_worker_is_logged(self):
        tracker = TransitionTracker()
        rows = tracker.rows_to_log([_record(zone_level="OUTSIDE")], system_state="SAFE")
        assert len(rows) == 1

    def test_no_row_when_zone_and_state_both_unchanged(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([_record(zone_level="OUTSIDE")], system_state="SAFE")

        rows = tracker.rows_to_log([_record(zone_level="OUTSIDE")], system_state="SAFE")
        assert rows == []

    def test_row_logged_when_workers_own_zone_changes(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([_record(zone_level="OUTSIDE")], system_state="SAFE")

        rows = tracker.rows_to_log([_record(zone_level="CAUTION")], system_state="WARNING")
        assert len(rows) == 1
        assert rows[0].zone_level == "CAUTION"

    def test_no_row_per_frame_for_a_stable_worker(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([_record(zone_level="DANGER")], system_state="CRITICAL")
        for _ in range(20):
            rows = tracker.rows_to_log([_record(zone_level="DANGER")], system_state="CRITICAL")
            assert rows == []


class TestTransitionTrackerMultiWorker:
    def test_only_the_worker_whose_zone_changed_gets_a_row(self):
        tracker = TransitionTracker()
        tracker.rows_to_log(
            [_record(worker_label="A", zone_level="OUTSIDE"), _record(worker_label="B", zone_level="DANGER")],
            system_state="CRITICAL",
        )
        rows = tracker.rows_to_log(
            [_record(worker_label="A", zone_level="CAUTION"), _record(worker_label="B", zone_level="DANGER")],
            system_state="CRITICAL",  # system state unchanged -- B's zone unchanged -- no row for B
        )
        assert len(rows) == 1
        assert rows[0].worker_label == "A"

    def test_system_state_change_rides_along_on_one_workers_row_only(self):
        tracker = TransitionTracker()
        tracker.rows_to_log(
            [_record(worker_label="A", zone_level="CAUTION"), _record(worker_label="B", zone_level="DANGER")],
            system_state="CRITICAL",
        )
        # system_state changes (CRITICAL -> WARNING) but neither worker's
        # own zone_level changed -- exactly one row should be emitted,
        # riding along on whichever worker is processed first.
        rows = tracker.rows_to_log(
            [_record(worker_label="A", zone_level="CAUTION"), _record(worker_label="B", zone_level="DANGER")],
            system_state="WARNING",
        )
        assert len(rows) == 1


class TestTransitionTrackerSystemOnly:
    def test_system_state_change_with_zero_workers_logs_one_system_row(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([], system_state="SAFE")

        system_only = _record(worker_label="placeholder", system_state="DEGRADED", camera_health=False)
        rows = tracker.rows_to_log([], system_state="DEGRADED", system_only_record=system_only)
        assert len(rows) == 1
        assert rows[0].worker_label == SYSTEM_WORKER_LABEL
        assert rows[0].system_state == "DEGRADED"

    def test_no_row_when_zero_workers_and_state_unchanged(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([], system_state="SAFE")
        rows = tracker.rows_to_log([], system_state="SAFE")
        assert rows == []

    def test_raises_if_system_only_record_missing_when_needed(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([], system_state="SAFE")
        try:
            tracker.rows_to_log([], system_state="DEGRADED")
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestTransitionTrackerStaleWorkerCleanup:
    def test_worker_leaving_and_a_new_label_reusing_starts_fresh(self):
        tracker = TransitionTracker()
        tracker.rows_to_log([_record(worker_label="track_1", zone_level="DANGER")], system_state="CRITICAL")
        # track_1 disappears entirely for a frame
        tracker.rows_to_log([], system_state="CRITICAL")
        # a worker reusing the same label later must be treated as a fresh
        # sighting (logged), not compared against the old DANGER history
        rows = tracker.rows_to_log([_record(worker_label="track_1", zone_level="DANGER")], system_state="CRITICAL")
        assert len(rows) == 1
