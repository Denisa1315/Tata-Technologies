"""Live demo: Kalman-filtered worker trajectory + dynamic ellipse safety zone.

Runs real webcam detection+tracking, projects trusted workers to ground-plane
position via homography, filters each through a per-track Kalman filter,
computes the mock machine's current dynamic zone, and renders everything as
a 2D top-down OpenCV plot: worker position (dot), filtered velocity vector
(arrow) with forecast position, and the zone ellipse -- which visibly
reshapes as the mock telemetry's angular speed changes.

Uses config/calibration.yaml if already calibrated; otherwise falls back to
the same placeholder homography as scripts/test_spatial_machine.py (NOT
physically meaningful for your room -- for demo purposes only).

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.scripts.test_prediction_zone
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from smart_zone.machine.mock_telemetry import MockMachineTelemetry
from smart_zone.perception.tracking import PersonTracker
from smart_zone.prediction.kalman import WorkerKalmanBank
from smart_zone.prediction.ttc import time_to_collision_s
from smart_zone.safety.zone import compute_zone_geometry, is_point_inside_zone
from smart_zone.spatial.homography import (
    CALIBRATION_YAML_PATH,
    bbox_to_ground_position,
    compute_homography,
    load_homography_from_yaml,
)

_PLACEHOLDER_IMAGE_POINTS = [(80.0, 480.0), (560.0, 480.0), (560.0, 240.0), (80.0, 240.0)]
_PLACEHOLDER_WORLD_POINTS = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]

PIVOT = (2.0, 1.5)  # placeholder machine location, ground-plane meters
ARM_RADIUS_M = 3.0

PLOT_SIZE_PX = 700
PLOT_SCALE_PX_PER_M = 40.0  # pixels per meter
PLOT_ORIGIN_PX = (PLOT_SIZE_PX // 2, PLOT_SIZE_PX // 2)

COLOR_ZONE_SAFE = (80, 200, 80)
COLOR_ZONE_WARN = (0, 165, 255)
COLOR_WORKER = (255, 255, 255)
COLOR_VELOCITY = (255, 200, 0)
COLOR_TEXT = (255, 255, 255)


def _load_homography_or_placeholder() -> tuple[np.ndarray, bool]:
    try:
        return load_homography_from_yaml(CALIBRATION_YAML_PATH), False
    except ValueError:
        return compute_homography(_PLACEHOLDER_IMAGE_POINTS, _PLACEHOLDER_WORLD_POINTS), True


def _world_to_plot_px(point: tuple[float, float]) -> tuple[int, int]:
    x, y = point
    ox, oy = PLOT_ORIGIN_PX
    px = int(ox + x * PLOT_SCALE_PX_PER_M)
    py = int(oy - y * PLOT_SCALE_PX_PER_M)  # flip y so "up" on screen = +y world
    return px, py


def _draw_ellipse(canvas: np.ndarray, zone, color) -> None:
    center_px = _world_to_plot_px(zone.center)
    axes_px = (
        int(zone.semi_major_m * PLOT_SCALE_PX_PER_M),
        int(zone.semi_minor_m * PLOT_SCALE_PX_PER_M),
    )
    cv2.ellipse(canvas, center_px, axes_px, -zone.orientation_deg, 0, 360, color, 2)


def main() -> None:
    matrix, is_placeholder = _load_homography_or_placeholder()
    if is_placeholder:
        print(
            "!! No calibration found -- using a PLACEHOLDER homography for this demo.\n"
            "   Run `python -m smart_zone.spatial.calibration` to calibrate your real camera.\n"
        )

    tracker = PersonTracker()
    kalman_bank = WorkerKalmanBank()
    machine = MockMachineTelemetry(angle_min_deg=-60.0, angle_max_deg=60.0, angular_speed_deg_s=40.0)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open default webcam (index 0).")

    prev_time = time.time()
    print("Press 'q' in the plot window to quit.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            now = time.time()
            dt = max(now - prev_time, 1e-3)
            prev_time = now

            tracked = tracker.update(frame)
            trusted = PersonTracker.trusted_only(tracked)

            zone = compute_zone_geometry(
                pivot=PIVOT,
                current_angle_deg=machine.angle_deg,
                angular_speed_deg_s=machine.speed_deg_s,
                radius_m=ARM_RADIUS_M,
            )

            canvas = np.zeros((PLOT_SIZE_PX, PLOT_SIZE_PX, 3), dtype=np.uint8)
            any_inside = False

            active_ids = {t.track_id for t in trusted}
            for stale_id in kalman_bank.active_track_ids() - active_ids:
                kalman_bank.drop(stale_id)

            for t in trusted:
                ground_pos = bbox_to_ground_position(matrix, t.bbox_xyxy)
                estimate = kalman_bank.update(t.track_id, ground_pos, dt)

                inside = is_point_inside_zone(zone, (estimate.x, estimate.y))
                any_inside = any_inside or inside
                ttc = time_to_collision_s(
                    (estimate.x, estimate.y), (estimate.vx, estimate.vy), zone
                )

                pos_px = _world_to_plot_px((estimate.x, estimate.y))
                forecast_px = _world_to_plot_px((estimate.forecast_x, estimate.forecast_y))

                cv2.circle(canvas, pos_px, 8, COLOR_WORKER, -1)
                cv2.arrowedLine(canvas, pos_px, forecast_px, COLOR_VELOCITY, 2, tipLength=0.2)
                ttc_str = f"{ttc:.1f}s" if ttc is not None else "--"
                cv2.putText(
                    canvas, f"id={t.track_id} ttc={ttc_str}",
                    (pos_px[0] + 12, pos_px[1] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1,
                )

            zone_color = COLOR_ZONE_WARN if any_inside else COLOR_ZONE_SAFE
            _draw_ellipse(canvas, zone, zone_color)
            cv2.circle(canvas, _world_to_plot_px(zone.center), 5, zone_color, -1)

            speed = machine.speed_deg_s
            cv2.putText(
                canvas,
                f"angle={machine.angle_deg:5.1f}deg  ang_speed={speed:6.1f}deg/s  "
                f"semi_major={zone.semi_major_m:.2f}m  semi_minor={zone.semi_minor_m:.2f}m",
                (10, PLOT_SIZE_PX - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1,
            )

            cv2.imshow("Smart-Zone Edge Guardian - Prediction + Zone (top-down)", canvas)
            cv2.imshow("Camera", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        machine.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
