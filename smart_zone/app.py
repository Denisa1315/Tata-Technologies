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
import time
from pathlib import Path

import cv2
import serial
import yaml

from smart_zone.hardware.mock_outputs import MockHardwareOutputs
from smart_zone.hardware.outputs import HardwareOutputs
from smart_zone.logging.event_logger import EventLogger, EventRecord
from smart_zone.machine.mock_telemetry import MockMachineTelemetry
from smart_zone.machine.telemetry import MachineTelemetry
from smart_zone.perception.tracking import PersonTracker
from smart_zone.prediction.kalman import WorkerKalmanBank
from smart_zone.prediction.ttc import time_to_collision_s
from smart_zone.safety.risk_engine import HealthStatus, RiskEngine, RiskState, WorkerObservation
from smart_zone.safety.zone import (
    compute_core_zone_geometry,
    compute_zone_geometry,
    is_point_inside_zone,
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
    parser.add_argument("--serial-port", default=None,
                         help="Serial device for the ESP32 (e.g. /dev/tty.usbserial-XXXX). Required unless --mock-hardware.")
    parser.add_argument("--baud-rate", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--no-display", action="store_true",
                         help="Don't open a live camera preview window.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.mock_hardware and not args.serial_port:
        raise SystemExit("Either --mock-hardware or --serial-port <device> is required.")

    thresholds = _load_thresholds()
    pivot = tuple(thresholds["machine_geometry"]["pivot_m"])
    radius_m = thresholds["machine_geometry"]["radius_m"]
    core_ratio = thresholds["safety"]["zone"]["core_ratio"]
    risk_cfg = thresholds["safety"]["risk_engine"]

    matrix, _is_placeholder = _load_homography()

    tracker = PersonTracker()
    kalman_bank = WorkerKalmanBank()
    risk_engine = RiskEngine(
        ttc_warning_s=risk_cfg["ttc_warning_s"],
        ttc_critical_s=risk_cfg["ttc_critical_s"],
        debounce_s=risk_cfg["debounce_s"],
        fps_floor=risk_cfg["fps_floor"],
    )
    event_logger = EventLogger()

    ser = None
    if args.mock_hardware:
        machine = MockMachineTelemetry(angle_min_deg=-45.0, angle_max_deg=45.0, angular_speed_deg_s=20.0)
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

    print("Smart-Zone Edge Guardian running. Press Ctrl+C to stop.\n")
    try:
        while True:
            ok, frame = cap.read()
            now = time.time()

            if ok:
                last_frame_time = now
            camera_alive = (now - last_frame_time) <= camera_timeout_s

            loop_dt = max(now - prev_loop_time, 1e-3)
            prev_loop_time = now
            fps = 0.9 * fps + 0.1 * (1.0 / loop_dt) if fps > 0 else (1.0 / loop_dt)

            worker_observations: list[WorkerObservation] = []
            trusted = []

            if ok:
                tracked = tracker.update(frame)
                trusted = PersonTracker.trusted_only(tracked)

                active_ids = {t.track_id for t in trusted}
                for stale_id in kalman_bank.active_track_ids() - active_ids:
                    kalman_bank.drop(stale_id)

                outer_zone = compute_zone_geometry(
                    pivot=pivot,
                    current_angle_deg=machine.angle_deg,
                    angular_speed_deg_s=machine.speed_deg_s,
                    radius_m=radius_m,
                )
                core_zone = compute_core_zone_geometry(outer_zone, core_ratio=core_ratio)

                for t in trusted:
                    ground_pos = bbox_to_ground_position(matrix, t.bbox_xyxy)
                    estimate = kalman_bank.update(t.track_id, ground_pos, loop_dt)
                    position = (estimate.x, estimate.y)

                    in_outer_margin = is_point_inside_zone(outer_zone, position)
                    in_core = is_point_inside_zone(core_zone, position)
                    ttc = time_to_collision_s(position, (estimate.vx, estimate.vy), outer_zone)

                    worker_observations.append(WorkerObservation(
                        position=position, ttc_s=ttc,
                        in_outer_margin=in_outer_margin, in_core=in_core,
                    ))

            health = HealthStatus(
                camera_alive=camera_alive,
                telemetry_alive=machine.is_alive(max_age_s=telemetry_max_age_s),
                fps=fps,
            )
            assessment = risk_engine.evaluate(worker_observations, health)
            hardware.apply_state(assessment.state)

            if assessment.state != last_reported_state:
                print(
                    f"[{time.strftime('%H:%M:%S')}] STATE -> {assessment.state.name}  "
                    f"(ttc={assessment.min_ttc_s}, workers={len(worker_observations)}, "
                    f"angle={machine.angle_deg:.1f}, speed={machine.speed_deg_s:.1f}, "
                    f"fps={fps:.1f}, camera_alive={camera_alive})"
                )
                event_logger.log_transition(EventRecord(
                    state=assessment.state.name,
                    ttc_s=assessment.min_ttc_s,
                    worker_count=len(worker_observations),
                    machine_angle_deg=machine.angle_deg,
                    machine_speed_deg_s=machine.speed_deg_s,
                    camera_health=camera_alive,
                ))
                last_reported_state = assessment.state

            if ok and not args.no_display:
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
        cap.release()
        cv2.destroyAllWindows()
        machine.close()
        if ser is not None:
            ser.close()


if __name__ == "__main__":
    main()
