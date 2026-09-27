"""Unit tests for logging.event_logger: CSV append-only transition log."""

from __future__ import annotations

import csv

from smart_zone.logging.event_logger import CSV_FIELDS, EventLogger, EventRecord


class TestEventLogger:
    def test_creates_file_with_header_if_missing(self, tmp_path):
        log_path = tmp_path / "events.csv"
        EventLogger(log_path=log_path)

        assert log_path.exists()
        with open(log_path) as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == CSV_FIELDS

    def test_logs_one_row_per_call(self, tmp_path):
        log_path = tmp_path / "events.csv"
        logger = EventLogger(log_path=log_path)

        logger.log_transition(EventRecord(
            state="WARNING", ttc_s=3.2, worker_count=1,
            machine_angle_deg=10.0, machine_speed_deg_s=5.0, camera_health=True,
        ))
        logger.log_transition(EventRecord(
            state="CRITICAL", ttc_s=0.9, worker_count=2,
            machine_angle_deg=12.0, machine_speed_deg_s=6.0, camera_health=True,
        ))

        with open(log_path) as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["state"] == "WARNING"
        assert rows[1]["state"] == "CRITICAL"

    def test_none_ttc_is_written_as_empty_string(self, tmp_path):
        log_path = tmp_path / "events.csv"
        logger = EventLogger(log_path=log_path)

        logger.log_transition(EventRecord(
            state="SAFE", ttc_s=None, worker_count=0,
            machine_angle_deg=0.0, machine_speed_deg_s=0.0, camera_health=True,
        ))

        with open(log_path) as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["ttc_s"] == ""

    def test_reopening_existing_logger_does_not_duplicate_header_or_truncate(self, tmp_path):
        log_path = tmp_path / "events.csv"
        logger1 = EventLogger(log_path=log_path)
        logger1.log_transition(EventRecord(
            state="WARNING", ttc_s=2.0, worker_count=1,
            machine_angle_deg=0.0, machine_speed_deg_s=0.0, camera_health=True,
        ))

        logger2 = EventLogger(log_path=log_path)  # simulates app restart
        logger2.log_transition(EventRecord(
            state="SAFE", ttc_s=None, worker_count=0,
            machine_angle_deg=0.0, machine_speed_deg_s=0.0, camera_health=True,
        ))

        with open(log_path) as f:
            reader = csv.reader(f)
            all_rows = list(reader)

        header_rows = [r for r in all_rows if r == CSV_FIELDS]
        assert len(header_rows) == 1
        assert len(all_rows) == 3  # 1 header + 2 data rows
