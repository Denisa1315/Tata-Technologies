"""Integration test for Section 2: drives safety.zone + safety.confidence +
safety.risk_engine + logging.event_logger + logging.summary together
through a scripted scenario (far away -> caution -> danger -> low-confidence
escalation -> leaves -> camera fault -> recovers), and checks the CSV has
exactly one row per zone/state transition (never per frame) and the
end-of-run summary totals match what the script actually did.
"""

from __future__ import annotations

import csv

from smart_zone.logging.event_logger import EventLogger, EventRecord, TransitionTracker
from smart_zone.logging.summary import RunSummary
from smart_zone.safety.confidence import (
    apply_confidence_to_zone_level,
    assess_confidence,
    range_based_margin_m,
)
from smart_zone.safety.risk_engine import HealthStatus, RiskEngine, RiskState, WorkerObservation
from smart_zone.safety.zone import (
    ZoneLevel,
    compute_caution_zone_geometry,
    compute_zone_geometry,
    zone_level_for_point,
)

PIVOT = (0.0, 0.0)
RADIUS_M = 3.0
CAMERA_POS = (0.0, -1.0)
FRAME_H = 1080.0

ZONE_KWARGS = dict(
    stopping_coeff=0.3, human_speed_mps=1.6, reaction_time_s=0.3,
    margin_m=0.1, baseline_radius_m=0.58, offset_ratio=0.3,
)
CAUTION_BAND_M = 0.7
CONF_KWARGS = dict(edge_margin_px=8, height_disagreement_ratio_threshold=0.35, reference_height_px_at_1m=800.0)


class Pipeline:
    """Small harness that wires the real modules together the same way
    app.py does, driven by scripted (position, bbox) inputs instead of a
    live camera."""

    def __init__(self, log_path):
        self.engine = RiskEngine(use_prediction=False, debounce_s=1.0, arm_reach_m=RADIUS_M)
        self.logger = EventLogger(log_path=log_path)
        self.tracker = TransitionTracker()
        self.summary = RunSummary()
        self.t = 0.0

    def step(self, worker_specs, health, angle_deg=0.0, speed_deg_s=0.0, dt=0.1):
        self.t += dt
        danger = compute_zone_geometry(PIVOT, angle_deg, speed_deg_s, RADIUS_M, **ZONE_KWARGS)
        caution = compute_caution_zone_geometry(danger, caution_band_m=CAUTION_BAND_M)

        worker_obs, basics = [], []
        any_caution = any_danger = False

        for label, pos, bbox in worker_specs:
            raw = zone_level_for_point(danger, caution, pos)
            conf = assess_confidence(bbox, pos, CAMERA_POS, PIVOT, FRAME_H, **CONF_KWARGS)
            margin = range_based_margin_m(conf.distance_to_camera_m, slope_m_per_m=0.05, max_margin_m=0.5)
            widened = compute_caution_zone_geometry(danger, caution_band_m=CAUTION_BAND_M + margin)
            level_with_margin = zone_level_for_point(danger, widened, pos)
            level = apply_confidence_to_zone_level(raw, conf.confidence, level_with_margin)

            any_caution = any_caution or level == ZoneLevel.CAUTION
            any_danger = any_danger or level == ZoneLevel.DANGER

            worker_obs.append(WorkerObservation(position=pos, zone_level=level, distance_from_pivot_m=conf.distance_to_machine_m))
            basics.append(dict(
                worker_label=label, ground_x=pos[0], ground_y=pos[1],
                distance_to_camera_m=conf.distance_to_camera_m, distance_to_machine_m=conf.distance_to_machine_m,
                zone_level=level.value, position_confidence=conf.confidence.value, feet_visible=conf.feet_visible,
            ))

        assessment = self.engine.evaluate(worker_obs, health, 0.0)
        stop_issued = assessment.state in {RiskState.CRITICAL, RiskState.DEGRADED}
        latency_ms = 15.0

        def build(b):
            return EventRecord(
                machine_angle_deg=angle_deg, machine_speed_deg_s=speed_deg_s,
                system_state=assessment.state.name, stop_issued=stop_issued,
                telemetry_health=health.telemetry_alive, pipeline_fps=30.0,
                frame_to_decision_ms=latency_ms, camera_health=health.camera_alive,
                **b,
            )

        records = [build(b) for b in basics]
        system_only = build(dict(worker_label="", ground_x=0.0, ground_y=0.0,
                                  distance_to_camera_m=0.0, distance_to_machine_m=0.0,
                                  zone_level="", position_confidence="", feet_visible=False))
        rows = self.tracker.rows_to_log(records, assessment.state.name, system_only_record=system_only)
        for row in rows:
            self.logger.log_event(row)

        self.summary.record_frame(self.t, any_caution, any_danger, stop_issued,
                                    health.camera_alive, health.telemetry_alive, latency_ms)
        return assessment, rows


HEALTHY = HealthStatus(camera_alive=True, telemetry_alive=True, fps=30.0)
FAULT = HealthStatus(camera_alive=False, telemetry_alive=True, fps=30.0)

# Bbox heights chosen to match expected_box_height_px() at each position's
# actual distance_to_camera_m (CAMERA_POS=(0,-1), reference_height_px_at_1m
# =800 default) -- i.e. genuinely HIGH-confidence detections, feet visible
# well clear of the frame edge, so these tests exercise the zone-level
# transition alone without also triggering the (separately-tested)
# LOW-confidence escalation path.
FAR_BBOX = (900.0, 400.0, 1000.0, 454.0)      # dist=14.87m -> expected ~54px tall
CAUTION_BBOX = (900.0, 100.0, 1000.0, 638.0)  # dist=1.49m -> expected ~538px tall
DANGER_BBOX = (900.0, 50.0, 1000.0, 816.0)    # dist=1.04m -> expected ~766px tall


class TestOneRowPerTransitionNotPerFrame:
    def test_stable_worker_produces_no_repeated_rows(self, tmp_path):
        pipeline = Pipeline(tmp_path / "events.csv")
        for _ in range(30):
            _, rows = pipeline.step([("track_1", (10.0, 10.0), FAR_BBOX)], HEALTHY)
        with open(tmp_path / "events.csv") as f:
            data_rows = list(csv.DictReader(f))
        assert len(data_rows) == 1  # only the first-sighting row

    def test_row_count_matches_number_of_transitions(self, tmp_path):
        pipeline = Pipeline(tmp_path / "events.csv")
        # far (SAFE) x3 -> caution (WARNING) x3 -> danger (CRITICAL) x3 -> far again x3
        for _ in range(3):
            pipeline.step([("track_1", (10.0, 10.0), FAR_BBOX)], HEALTHY)
        for _ in range(3):
            pipeline.step([("track_1", (1.1, 0.0), CAUTION_BBOX)], HEALTHY)
        for _ in range(3):
            pipeline.step([("track_1", (0.3, 0.0), DANGER_BBOX)], HEALTHY)
        for _ in range(3):
            pipeline.step([("track_1", (10.0, 10.0), FAR_BBOX)], HEALTHY)

        with open(tmp_path / "events.csv") as f:
            data_rows = list(csv.DictReader(f))
        # 4 distinct zone_levels visited by this one worker -> 4 rows
        assert len(data_rows) == 4
        assert [r["zone_level"] for r in data_rows] == ["OUTSIDE", "CAUTION", "DANGER", "OUTSIDE"]


class TestLowConfidenceEscalation:
    def test_edge_cropped_worker_in_caution_escalates_to_danger_in_log(self, tmp_path):
        pipeline = Pipeline(tmp_path / "events.csv")
        edge_bbox = (900.0, 300.0, 1000.0, FRAME_H)  # feet cut off
        # position 0.9m from pivot at zero speed -> raw CAUTION (baseline
        # circle: danger=0.58m, caution=1.28m)
        assessment, rows = pipeline.step([("track_1", (0.9, 0.0), edge_bbox)], HEALTHY)
        assert rows[0].zone_level == "DANGER"
        assert rows[0].position_confidence == "LOW"
        assert assessment.state == RiskState.CRITICAL


class TestSummaryMatchesScriptedScenario:
    def test_summary_totals_match_the_script(self, tmp_path):
        pipeline = Pipeline(tmp_path / "events.csv")

        # far (SAFE)
        pipeline.step([("track_1", (10.0, 10.0), FAR_BBOX)], HEALTHY, dt=0.5)
        # caution (WARNING) -- 1 caution event
        pipeline.step([("track_1", (1.1, 0.0), CAUTION_BBOX)], HEALTHY, dt=0.5)
        # danger (CRITICAL + STOP) -- 1 danger event, 1 stop command
        pipeline.step([("track_1", (0.3, 0.0), DANGER_BBOX)], HEALTHY, dt=0.5)
        pipeline.step([("track_1", (0.3, 0.0), DANGER_BBOX)], HEALTHY, dt=0.5)  # accumulates 0.5s danger time
        # clears
        pipeline.step([("track_1", (10.0, 10.0), FAR_BBOX)], HEALTHY, dt=0.5)
        # camera fault -- 1 camera fault
        pipeline.step([], FAULT, dt=0.5)
        # recovers
        pipeline.step([], HEALTHY, dt=0.5)

        assert pipeline.summary.caution_events == 1
        assert pipeline.summary.danger_events == 1
        assert pipeline.summary.time_in_danger_s > 0.0
        assert pipeline.summary.stop_commands == 1
        assert pipeline.summary.camera_faults == 1
        assert pipeline.summary.telemetry_faults == 0
        assert pipeline.summary.latency.sample_count == 7
