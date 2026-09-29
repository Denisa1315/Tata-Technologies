"""Smart-Zone Edge Guardian orchestrator.

Wires: perception (detect+track) -> spatial (homography) -> machine
telemetry -> prediction (Kalman + TTC) -> safety (zone + risk engine) ->
hardware outputs -> logging, in one real-time loop.

Run from the Tata-Technologies/ parent directory:

    # No hardware needed -- uses mock telemetry, prints actions to console:
    python -m smart_zone.app --mock-hardware

    # Real ESP32 connected:
    python -m smart_zone.app --serial-port /dev/tty.usbserial-XXXX

Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import cv2
import serial
import yaml

from smart_zone.dashboard.hologram_view import HologramView
from smart_zone.dashboard.sim_view import (
    WINDOW_H,
    WINDOW_W,
    SimView,
    SimViewState,
    SummaryViewState,
    TransitionRecord,
    WorkerViewState,
)
from smart_zone.dashboard.sound import SoundController
from smart_zone.hardware.mock_outputs import MockHardwareOutputs
from smart_zone.hardware.outputs import HardwareOutputs
from smart_zone.hardware.sim_outputs import SimHardwareOutputs
from smart_zone.logging.event_logger import EventLogger, EventRecord, TransitionTracker
from smart_zone.logging.summary import RunSummary
from smart_zone.machine.mock_telemetry import MockMachineTelemetry
from smart_zone.machine.telemetry import MachineTelemetry
from smart_zone.perception.tracking import PersonTracker
from smart_zone.prediction.kalman import WorkerKalmanBank
from smart_zone.prediction.ttc import time_to_collision_s
from smart_zone.safety.confidence import (
    PositionConfidence,
    apply_confidence_to_zone_level,
    assess_confidence,
    range_based_margin_m,
)
from smart_zone.safety.risk_engine import HealthStatus, RiskEngine, RiskState, WorkerObservation
from smart_zone.safety.zone import (
    ZoneLevel,
    compute_caution_zone_geometry,
    compute_zone_geometry,
    tangential_speed_m_s,
    zone_level_for_point,
)
from smart_zone.spatial.homography import (
    CALIBRATION_YAML_PATH,
    bbox_to_ground_position,
    compute_homography,
    load_homography_from_yaml,
)

THRESHOLDS_YAML_PATH = Path(__file__).resolve().parent / "config" / "thresholds.yaml"

_PLACEHOLDER_IMAGE_POINTS = [(80.0, 480.0), (560.0, 480.0), (560.0, 240.0), (80.0, 240.0)]
_PLACEHOLDER_WORLD_POINTS = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]

DEFAULT_BAUD_RATE = 115200
DEFAULT_SIM_ANGULAR_SPEED_DEG_S = 20.0
DISPLAY_COLOR_BY_STATE = {
    RiskState.SAFE: (0, 200, 0),
    RiskState.WARNING: (0, 200, 255),
    RiskState.CRITICAL: (0, 0, 255),
    RiskState.DEGRADED: (255, 0, 255),
}


def _load_thresholds() -> dict:
    with open(THRESHOLDS_YAML_PATH) as f:
        return yaml.safe_load(f)


def _load_homography() -> tuple:
    try:
        return load_homography_from_yaml(CALIBRATION_YAML_PATH), False
    except ValueError:
        print(
            "!! No calibration found in config/calibration.yaml -- using a "
            "PLACEHOLDER homography. Run `python -m smart_zone.spatial.calibration` "
            "to calibrate your real camera before relying on this for real testing.\n"
        )
        return compute_homography(_PLACEHOLDER_IMAGE_POINTS, _PLACEHOLDER_WORLD_POINTS), True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart-Zone Edge Guardian")
    parser.add_argument("--mock-hardware", action="store_true",
                         help="Use mock telemetry and print actions instead of opening a serial port.")
    parser.add_argument("--sim", action="store_true",
                         help="Use mock telemetry + in-process simulated outputs (readable state, no printing, "
                              "no serial port) -- STOP/RESUME really freeze/resume the simulated arm.")
    parser.add_argument("--serial-port", default=None,
                         help="Serial device for the ESP32 (e.g. /dev/tty.usbserial-XXXX). Required unless --mock-hardware/--sim.")
    parser.add_argument("--baud-rate", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--no-display", action="store_true",
                         help="Don't open a live camera preview window.")
    parser.add_argument("--record", default=None, metavar="PATH.mp4",
                         help="Save the composed sim-view window to this video file (--sim only).")
    parser.add_argument("--no-webcam-inset", action="store_true",
                         help="Hide the live-webcam inset in the sim view (for headless testing).")
    return parser.parse_args()


def _keyboard_speed_step(current_speed: float) -> float:
    return max(1.0, current_speed * 0.25)


def main() -> None:
    args = parse_args()
    if not args.mock_hardware and not args.sim and not args.serial_port:
        raise SystemExit("One of --mock-hardware, --sim, or --serial-port <device> is required.")

    thresholds = _load_thresholds()
    pivot = tuple(thresholds["machine_geometry"]["pivot_m"])
    radius_m = thresholds["machine_geometry"]["radius_m"]
    camera_ground_position = tuple(thresholds["camera_geometry"]["ground_position_m"])
    zone_cfg = thresholds["safety"]["zone"]
    risk_cfg = thresholds["safety"]["risk_engine"]
    confidence_cfg = thresholds["safety"]["confidence"]

    matrix, _is_placeholder = _load_homography()

    tracker = PersonTracker()
    kalman_bank = WorkerKalmanBank()

    def _build_risk_engine() -> RiskEngine:
        return RiskEngine(
            use_prediction=risk_cfg["use_prediction"],
            ttc_warning_s=risk_cfg["ttc_warning_s"],
            ttc_critical_s=risk_cfg["ttc_critical_s"],
            debounce_s=risk_cfg["debounce_s"],
            fps_floor=risk_cfg["fps_floor"],
            quiet_when_stationary=risk_cfg["quiet_when_stationary"],
            stationary_speed_threshold_m_s=risk_cfg["stationary_speed_threshold_m_s"],
            arm_reach_m=radius_m,
        )

    risk_engine = _build_risk_engine()
    event_logger = EventLogger()
    transition_tracker = TransitionTracker()
    run_summary = RunSummary()

    ser = None
    if args.sim:
        machine = MockMachineTelemetry(angle_min_deg=-45.0, angle_max_deg=45.0,
                                        angular_speed_deg_s=DEFAULT_SIM_ANGULAR_SPEED_DEG_S)
        hardware = SimHardwareOutputs(machine)
    elif args.mock_hardware:
        machine = MockMachineTelemetry(angle_min_deg=-45.0, angle_max_deg=45.0,
                                        angular_speed_deg_s=DEFAULT_SIM_ANGULAR_SPEED_DEG_S)
        hardware = MockHardwareOutputs()
    else:
        ser = serial.Serial(args.serial_port, args.baud_rate, timeout=1.0)
        machine = MachineTelemetry(ser)
        hardware = HardwareOutputs(ser)

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {args.camera_index}.")

    camera_timeout_s = risk_cfg["camera_timeout_s"]
    telemetry_max_age_s = risk_cfg["telemetry_max_age_s"]

    last_frame_time = time.time()
    prev_loop_time = time.time()
    fps = 0.0
    last_reported_state: RiskState | None = None

    # --sim-only demo/orchestration state. sim_view.py never touches these
    # decisions itself -- it only reports which key was pressed each frame
    # (poll_keys()); interpreting a key press as "simulate a camera fault"
    # or "reset the scenario" happens here, in app.py.
    sim_view = SimView(show_webcam_inset=not args.no_webcam_inset) if args.sim else None
    hologram_view = HologramView() if args.sim else None
    hologram_enabled = False
    sound_controller = SoundController() if args.sim else None
    camera_fault_simulated = False
    recent_transitions: list[TransitionRecord] = []
    video_writer = None
    snapshot_count = 0

    if args.sim and args.record:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(args.record, fourcc, 20.0, (WINDOW_W, WINDOW_H))
        if not video_writer.isOpened():
            raise RuntimeError(f"Could not open video writer for {args.record}")

    print("Smart-Zone Edge Guardian running. Press Ctrl+C to stop.\n")
    try:
        while True:
            ok, frame = cap.read()
            now = time.time()

            # A simulated camera fault is treated exactly like a real camera
            # loss: it overrides `ok`/camera_alive for this frame, same as
            # if the lens were actually covered and cap.read() kept failing.
            if camera_fault_simulated:
                ok = False

            if ok:
                last_frame_time = now
            camera_alive = (now - last_frame_time) <= camera_timeout_s

            loop_dt = max(now - prev_loop_time, 1e-3)
            prev_loop_time = now
            fps = 0.9 * fps + 0.1 * (1.0 / loop_dt) if fps > 0 else (1.0 / loop_dt)

            worker_observations: list[WorkerObservation] = []
            worker_view_states: list[WorkerViewState] = []
            worker_log_basics: list[dict] = []  # per-worker fields known before the risk decision
            trusted = []
            any_caution = False
            any_danger = False

            machine_speed_m_s = tangential_speed_m_s(machine.speed_deg_s, radius_m)
            danger_zone = compute_zone_geometry(
                pivot=pivot,
                current_angle_deg=machine.angle_deg,
                angular_speed_deg_s=machine.speed_deg_s,
                radius_m=radius_m,
                stopping_coeff=zone_cfg["stopping_coeff"],
                human_speed_mps=zone_cfg["human_speed_mps"],
                reaction_time_s=zone_cfg["reaction_time_s"],
                margin_m=zone_cfg["margin_m"],
                baseline_radius_m=zone_cfg["baseline_radius_m"],
                offset_ratio=zone_cfg["offset_ratio"],
            )
            caution_zone = compute_caution_zone_geometry(danger_zone, caution_band_m=zone_cfg["caution_band_m"])

            if ok:
                tracked = tracker.update(frame)
                trusted = PersonTracker.trusted_only(tracked)
                frame_height_px = frame.shape[0]

                active_ids = {t.track_id for t in trusted}
                for stale_id in kalman_bank.active_track_ids() - active_ids:
                    kalman_bank.drop(stale_id)

                for t in trusted:
                    ground_pos = bbox_to_ground_position(matrix, t.bbox_xyxy)
                    estimate = kalman_bank.update(t.track_id, ground_pos, loop_dt)
                    position = (estimate.x, estimate.y)

                    raw_zone_level = zone_level_for_point(danger_zone, caution_zone, position)

                    conf = assess_confidence(
                        bbox_xyxy=t.bbox_xyxy, ground_position=position,
                        camera_ground_position=camera_ground_position, machine_pivot=pivot,
                        frame_height_px=frame_height_px,
                        edge_margin_px=confidence_cfg["edge_margin_px"],
                        height_disagreement_ratio_threshold=confidence_cfg["height_disagreement_ratio"],
                        reference_height_px_at_1m=confidence_cfg["reference_height_px_at_1m"],
                    )

                    # Range-based margin: widen the caution band by an
                    # amount that grows with distance_to_camera_m, and
                    # reclassify against that widened zone -- used only to
                    # decide the LOW-confidence OUTSIDE->CAUTION escalation,
                    # not as the zone_level workers are normally judged by.
                    margin_m = range_based_margin_m(
                        conf.distance_to_camera_m,
                        slope_m_per_m=confidence_cfg["range_margin_slope_m_per_m"],
                        max_margin_m=confidence_cfg["range_margin_max_m"],
                    )
                    widened_caution_zone = compute_caution_zone_geometry(
                        danger_zone, caution_band_m=zone_cfg["caution_band_m"] + margin_m
                    )
                    zone_level_with_margin = zone_level_for_point(danger_zone, widened_caution_zone, position)

                    zone_level = apply_confidence_to_zone_level(
                        raw_zone_level, conf.confidence, zone_level_with_margin
                    )

                    any_caution = any_caution or zone_level == ZoneLevel.CAUTION
                    any_danger = any_danger or zone_level == ZoneLevel.DANGER

                    # Kalman stays only a position smoother -- its
                    # forecast/velocity is only consulted for TTC when
                    # use_prediction is explicitly on, never for the
                    # position-only decision path.
                    ttc = None
                    if risk_cfg["use_prediction"]:
                        ttc = time_to_collision_s(position, (estimate.vx, estimate.vy), caution_zone)

                    worker_observations.append(WorkerObservation(
                        position=position, zone_level=zone_level,
                        distance_from_pivot_m=conf.distance_to_machine_m, ttc_s=ttc,
                    ))
                    worker_view_states.append(WorkerViewState(
                        track_id=t.track_id, position=position,
                        forecast_position=(estimate.forecast_x, estimate.forecast_y),
                        zone_level=zone_level.value, position_confidence=conf.confidence.value,
                        distance_to_machine_m=conf.distance_to_machine_m,
                        distance_to_camera_m=conf.distance_to_camera_m,
                        detection_confidence_pct=t.confidence * 100.0,
                    ))
                    worker_log_basics.append(dict(
                        worker_label=f"track_{t.track_id}",
                        ground_x=position[0], ground_y=position[1],
                        distance_to_camera_m=conf.distance_to_camera_m,
                        distance_to_machine_m=conf.distance_to_machine_m,
                        zone_level=zone_level.value, position_confidence=conf.confidence.value,
                        feet_visible=conf.feet_visible,
                    ))

            health = HealthStatus(
                camera_alive=camera_alive,
                telemetry_alive=machine.is_alive(max_age_s=telemetry_max_age_s),
                fps=fps,
            )
            assessment = risk_engine.evaluate(worker_observations, health, machine_speed_m_s)
            hardware.apply_state(assessment.state, buzzer_should_sound=assessment.buzzer_should_sound)

            frame_to_decision_ms = (time.time() - now) * 1000.0
            stop_issued = assessment.state in {RiskState.CRITICAL, RiskState.DEGRADED}

            def _build_record(basics: dict) -> EventRecord:
                return EventRecord(
                    machine_angle_deg=machine.angle_deg, machine_speed_deg_s=machine.speed_deg_s,
                    system_state=assessment.state.name, stop_issued=stop_issued,
                    telemetry_health=health.telemetry_alive,
                    pipeline_fps=fps, frame_to_decision_ms=frame_to_decision_ms,
                    camera_health=camera_alive,
                    **basics,
                )

            worker_log_records = [_build_record(b) for b in worker_log_basics]
            system_only_record = _build_record(dict(
                worker_label="", ground_x=0.0, ground_y=0.0,
                distance_to_camera_m=0.0, distance_to_machine_m=0.0,
                zone_level="", position_confidence="", feet_visible=False,
            ))
            for row in transition_tracker.rows_to_log(
                worker_log_records, assessment.state.name, system_only_record=system_only_record
            ):
                event_logger.log_event(row)

            run_summary.record_frame(
                now_s=now, any_worker_in_caution=any_caution, any_worker_in_danger=any_danger,
                stop_active=stop_issued, camera_alive=camera_alive, telemetry_alive=health.telemetry_alive,
                frame_to_decision_ms=frame_to_decision_ms,
            )

            if assessment.state != last_reported_state:
                print(
                    f"[{time.strftime('%H:%M:%S')}] STATE -> {assessment.state.name}  "
                    f"(ttc={assessment.min_ttc_s}, workers={len(worker_observations)}, "
                    f"angle={machine.angle_deg:.1f}, speed={machine.speed_deg_s:.1f}, "
                    f"fps={fps:.1f}, camera_alive={camera_alive})"
                )
                if last_reported_state is not None:
                    recent_transitions.append(TransitionRecord(
                        timestamp=now,
                        from_state=last_reported_state.name,
                        to_state=assessment.state.name,
                        ttc_s=assessment.min_ttc_s,
                    ))
                last_reported_state = assessment.state

            if args.sim and sim_view is not None:
                webcam_inset = None
                if not args.no_webcam_inset and ok:
                    webcam_inset = frame.copy()
                    color = DISPLAY_COLOR_BY_STATE[assessment.state]
                    for t in trusted:
                        x1, y1, x2, y2 = (int(v) for v in t.bbox_xyxy)
                        cv2.rectangle(webcam_inset, (x1, y1), (x2, y2), color, 2)

                # Pure display aggregation from values already computed
                # above -- no new decision logic, just min()/max() over the
                # same per-worker data already fed into the risk engine.
                closest_distance_m = (
                    min(w.distance_to_machine_m for w in worker_view_states)
                    if worker_view_states else None
                )
                zone_severity = {"OUTSIDE": 0, "CAUTION": 1, "DANGER": 2}
                highest_risk_worker_label = (
                    f"W-{max(worker_view_states, key=lambda w: zone_severity[w.zone_level]).track_id:02d}"
                    if worker_view_states else None
                )
                interlock_action = "STOP" if assessment.state in {RiskState.CRITICAL, RiskState.DEGRADED} else "MONITOR"

                view_state = SimViewState(
                    risk_state=assessment.state.name,
                    ttc_s=assessment.min_ttc_s,
                    use_prediction=risk_cfg["use_prediction"],
                    machine_pivot=pivot,
                    machine_angle_deg=machine.angle_deg,
                    machine_speed_deg_s=machine.speed_deg_s,
                    machine_arm_length_m=radius_m,
                    machine_running=(machine.state == "RUNNING"),
                    zone_center=danger_zone.center,
                    zone_orientation_deg=danger_zone.orientation_deg,
                    zone_caution_semi_major_m=caution_zone.semi_major_m,
                    zone_caution_semi_minor_m=caution_zone.semi_minor_m,
                    zone_danger_semi_major_m=danger_zone.semi_major_m,
                    zone_danger_semi_minor_m=danger_zone.semi_minor_m,
                    workers=worker_view_states,
                    led_level=hardware.led_level,
                    buzzer_on=hardware.buzzer_on,
                    stop_active=hardware.stop_active,
                    fps=fps,
                    camera_alive=camera_alive,
                    telemetry_alive=health.telemetry_alive,
                    camera_fault_simulated=camera_fault_simulated,
                    recent_transitions=recent_transitions,
                    webcam_frame=webcam_inset,
                    summary=SummaryViewState(
                        caution_events=run_summary.caution_events,
                        danger_events=run_summary.danger_events,
                        time_in_danger_s=run_summary.time_in_danger_s,
                        stop_commands=run_summary.stop_commands,
                        camera_faults=run_summary.camera_faults,
                        telemetry_faults=run_summary.telemetry_faults,
                        latency_avg_ms=run_summary.latency.average_ms,
                        latency_max_ms=run_summary.latency.max_ms,
                    ),
                    closest_distance_m=closest_distance_m,
                    highest_risk_worker_label=highest_risk_worker_label,
                    interlock_action=interlock_action,
                    camera_ground_position=camera_ground_position,
                )
                if hologram_enabled and hologram_view is not None:
                    canvas = hologram_view.render(view_state, show_webcam_inset=not args.no_webcam_inset)
                else:
                    canvas = sim_view.render(view_state)
                sim_view.show(canvas)

                sound_controller.update(assessment.state.name, assessment.buzzer_should_sound, now=now)

                if video_writer is not None:
                    video_writer.write(canvas)

                key = sim_view.poll_keys(wait_ms=1)
                if key == "q":
                    break
                elif key == "h":
                    hologram_enabled = not hologram_enabled
                elif key == "d":
                    # Theme only affects the plain view -- hologram_view's
                    # own dark aesthetic is untouched either way.
                    new_theme = sim_view.toggle_theme()
                    print(f"Theme -> {new_theme.name}")
                elif key == "c":
                    camera_fault_simulated = not camera_fault_simulated
                elif key == "r":
                    # Reset the scenario: arm angle/speed back to the
                    # starting point, and the risk engine's state/hysteresis
                    # timers start clean too.
                    machine.reset(angular_speed_deg_s=DEFAULT_SIM_ANGULAR_SPEED_DEG_S)
                    risk_engine = _build_risk_engine()
                    transition_tracker = TransitionTracker()
                    last_reported_state = None
                    recent_transitions.clear()
                    camera_fault_simulated = False
                elif key == "+":
                    current_speed = abs(machine.speed_deg_s) or DEFAULT_SIM_ANGULAR_SPEED_DEG_S
                    machine.set_speed(current_speed + _keyboard_speed_step(current_speed))
                elif key == "-":
                    current_speed = abs(machine.speed_deg_s) or DEFAULT_SIM_ANGULAR_SPEED_DEG_S
                    machine.set_speed(max(1.0, current_speed - _keyboard_speed_step(current_speed)))
                elif key == "s":
                    snapshot_count += 1
                    snap_path = f"sim_view_snapshot_{snapshot_count}.png"
                    cv2.imwrite(snap_path, canvas)
                    print(f"Saved snapshot: {snap_path}")

            elif ok and not args.no_display:
                color = DISPLAY_COLOR_BY_STATE[assessment.state]
                for t in trusted:
                    x1, y1, x2, y2 = (int(v) for v in t.bbox_xyxy)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"STATE: {assessment.state.name}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.imshow("Smart-Zone Edge Guardian", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        run_summary.print_summary()
        cap.release()
        cv2.destroyAllWindows()
        machine.close()
        if ser is not None:
            ser.close()
        if video_writer is not None:
            video_writer.release()


if __name__ == "__main__":
    main()
