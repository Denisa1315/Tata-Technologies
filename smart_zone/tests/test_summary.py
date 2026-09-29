"""Unit tests for logging.summary: RunSummary event counting and
LatencyTracker rolling average/max."""

from __future__ import annotations

import pytest

from smart_zone.logging.summary import LatencyTracker, RunSummary


class TestLatencyTracker:
    def test_average_of_no_samples_is_zero(self):
        tracker = LatencyTracker()
        assert tracker.average_ms == pytest.approx(0.0)
        assert tracker.max_ms == pytest.approx(0.0)

    def test_average_matches_known_samples(self):
        tracker = LatencyTracker()
        for v in [10.0, 20.0, 30.0]:
            tracker.record(v)
        assert tracker.average_ms == pytest.approx(20.0)

    def test_max_tracks_the_largest_sample(self):
        tracker = LatencyTracker()
        for v in [10.0, 50.0, 20.0]:
            tracker.record(v)
        assert tracker.max_ms == pytest.approx(50.0)

    def test_sample_count(self):
        tracker = LatencyTracker()
        tracker.record(5.0)
        tracker.record(5.0)
        assert tracker.sample_count == 2

    def test_no_hardcoded_latency_reflects_only_recorded_values(self):
        tracker = LatencyTracker()
        tracker.record(123.456)
        assert tracker.average_ms == pytest.approx(123.456)
        assert tracker.max_ms == pytest.approx(123.456)


class TestRunSummaryEventCounting:
    def test_caution_event_counted_once_per_rising_edge(self):
        summary = RunSummary()
        summary.record_frame(0.0, True, False, False, True, True, 10.0)
        summary.record_frame(0.1, True, False, False, True, True, 10.0)  # still caution -- no new event
        summary.record_frame(0.2, True, False, False, True, True, 10.0)
        assert summary.caution_events == 1

    def test_caution_event_fires_again_after_clearing(self):
        summary = RunSummary()
        summary.record_frame(0.0, True, False, False, True, True, 10.0)
        summary.record_frame(0.1, False, False, False, True, True, 10.0)  # clears
        summary.record_frame(0.2, True, False, False, True, True, 10.0)  # new rising edge
        assert summary.caution_events == 2

    def test_danger_event_counted_once_per_rising_edge(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, True, True, True, True, 10.0)
        summary.record_frame(0.1, False, True, True, True, True, 10.0)
        assert summary.danger_events == 1

    def test_time_in_danger_accumulates_across_frames(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, True, True, True, True, 10.0)
        summary.record_frame(1.0, False, True, True, True, True, 10.0)
        summary.record_frame(2.5, False, True, True, True, True, 10.0)
        # danger continuously true from t=0 to t=2.5 -> 2.5s accumulated
        assert summary.time_in_danger_s == pytest.approx(2.5)

    def test_time_in_danger_stops_accumulating_after_clearing(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, True, True, True, True, 10.0)
        summary.record_frame(1.0, False, True, True, True, True, 10.0)
        summary.record_frame(2.0, False, False, False, True, True, 10.0)  # danger clears
        summary.record_frame(10.0, False, False, False, True, True, 10.0)  # long gap, no danger
        assert summary.time_in_danger_s == pytest.approx(1.0)

    def test_stop_command_counted_once_per_rising_edge(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, True, True, True, True, 10.0)
        summary.record_frame(0.1, False, True, True, True, True, 10.0)
        summary.record_frame(0.2, False, False, False, True, True, 10.0)  # STOP released
        summary.record_frame(0.3, False, True, True, True, True, 10.0)  # STOP again
        assert summary.stop_commands == 2

    def test_camera_fault_counted_on_transition_to_dead(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, False, False, True, True, 10.0)  # first frame establishes baseline
        summary.record_frame(0.1, False, False, False, False, True, 10.0)  # camera dies
        summary.record_frame(0.2, False, False, False, False, True, 10.0)  # still dead -- no new fault
        assert summary.camera_faults == 1

    def test_telemetry_fault_counted_on_transition_to_dead(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, False, False, True, True, 10.0)
        summary.record_frame(0.1, False, False, False, True, False, 10.0)
        assert summary.telemetry_faults == 1

    def test_first_frame_does_not_spuriously_count_a_fault(self):
        # No baseline yet on the very first frame -- must not count a fault
        # just because camera_alive/telemetry_alive start out however they do.
        summary = RunSummary()
        summary.record_frame(0.0, False, False, False, False, False, 10.0)
        assert summary.camera_faults == 0
        assert summary.telemetry_faults == 0

    def test_latency_recorded_every_frame(self):
        summary = RunSummary()
        summary.record_frame(0.0, False, False, False, True, True, 15.0)
        summary.record_frame(0.1, False, False, False, True, True, 25.0)
        assert summary.latency.average_ms == pytest.approx(20.0)
        assert summary.latency.max_ms == pytest.approx(25.0)


class TestRunSummaryScriptedScenario:
    def test_matches_a_full_scripted_scenario(self):
        """SAFE(no worker) -> CAUTION -> DANGER+STOP -> clears -> DANGER
        again+STOP -> clears -> camera fault -> recovers.

        time_in_danger_s accumulates only between consecutive frames where
        danger was observed continuously true -- it does NOT extrapolate
        forward to the frame where the condition is first observed to have
        cleared (same "don't assume continuity you didn't sample"
        principle as the risk-engine debounce timers)."""
        summary = RunSummary()

        # t=0: safe baseline
        summary.record_frame(0.0, False, False, False, True, True, 10.0)
        # t=0.5: caution
        summary.record_frame(0.5, True, False, False, True, True, 10.0)
        # t=1.0: danger + stop starts (danger_start=1.0, no accumulation yet)
        summary.record_frame(1.0, False, True, True, True, True, 10.0)
        # t=1.8: still danger + stop -> accumulates 1.8-1.0=0.8s
        summary.record_frame(1.8, False, True, True, True, True, 10.0)
        # t=2.0: clears back to safe (no further accumulation past t=1.8)
        summary.record_frame(2.0, False, False, False, True, True, 10.0)
        # t=3.0: danger again (2nd event) + stop again (2nd stop) -- new danger_start=3.0
        summary.record_frame(3.0, False, True, True, True, True, 10.0)
        # t=3.5: still danger -> accumulates 3.5-3.0=0.5s (total so far 1.3s)
        summary.record_frame(3.5, False, True, True, True, True, 10.0)
        # t=4.0: clears
        summary.record_frame(4.0, False, False, False, True, True, 10.0)
        # t=4.5: camera fault
        summary.record_frame(4.5, False, False, False, False, True, 10.0)
        # t=5.0: camera recovers
        summary.record_frame(5.0, False, False, False, True, True, 10.0)

        assert summary.caution_events == 1
        assert summary.danger_events == 2
        assert summary.time_in_danger_s == pytest.approx(1.3)
        assert summary.stop_commands == 2
        assert summary.camera_faults == 1
        assert summary.telemetry_faults == 0
