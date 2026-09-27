"""Live demo: homography-projected worker ground position + mock machine angle.

Runs real webcam detection+tracking (from Section 1), projects each trusted
worker's bounding box to ground-plane (x, y) via homography, and prints it
live alongside the mock machine's current slew angle/speed.

Uses config/calibration.yaml if it already has point correspondences saved
(from running `python -m smart_zone.spatial.calibration` yourself); otherwise
falls back to a placeholder demo homography so this script is runnable
before you've calibrated your real camera. The fallback is for demonstration
only -- ground positions from it are NOT physically meaningful for your
actual room.

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.scripts.test_spatial_machine
"""

from __future__ import annotations

import time

import numpy as np

from smart_zone.machine.mock_telemetry import MockMachineTelemetry
from smart_zone.perception.tracking import PersonTracker
from smart_zone.spatial.homography import (
    CALIBRATION_YAML_PATH,
    bbox_to_ground_position,
    compute_homography,
    load_homography_from_yaml,
)

# Placeholder correspondences used only if calibration.yaml has none yet:
# assumes a 640x480-ish frame where a 4m x 3m floor patch fills roughly the
# lower half of the image. Replace by running the real calibration script.
_PLACEHOLDER_IMAGE_POINTS = [(80.0, 480.0), (560.0, 480.0), (560.0, 240.0), (80.0, 240.0)]
_PLACEHOLDER_WORLD_POINTS = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]


def _load_homography_or_placeholder() -> tuple[np.ndarray, bool]:
    try:
        matrix = load_homography_from_yaml(CALIBRATION_YAML_PATH)
        return matrix, False
    except ValueError:
        matrix = compute_homography(_PLACEHOLDER_IMAGE_POINTS, _PLACEHOLDER_WORLD_POINTS)
        return matrix, True


def main() -> None:
    import cv2

    matrix, is_placeholder = _load_homography_or_placeholder()
    if is_placeholder:
        print(
            "!! No calibration found in config/calibration.yaml -- using a "
            "PLACEHOLDER homography for this demo. Run "
            "`python -m smart_zone.spatial.calibration` to calibrate your real camera.\n"
        )

    tracker = PersonTracker()
    machine = MockMachineTelemetry(angle_min_deg=-45.0, angle_max_deg=45.0, angular_speed_deg_s=20.0)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open default webcam (index 0).")

    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Frame grab failed, stopping.")
                break

            tracked = tracker.update(frame)
            trusted = PersonTracker.trusted_only(tracked)

            worker_positions = [
                (t.track_id, bbox_to_ground_position(matrix, t.bbox_xyxy)) for t in trusted
            ]

            angle = machine.angle_deg
            speed = machine.speed_deg_s
            alive = machine.is_alive()

            worker_str = (
                ", ".join(f"id={tid} ground=({x:.2f},{y:.2f})m" for tid, (x, y) in worker_positions)
                or "none"
            )
            print(
                f"\rmachine: angle={angle:6.1f} deg  speed={speed:6.1f} deg/s  "
                f"alive={alive}  |  workers: {worker_str}          ",
                end="",
                flush=True,
            )

            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()
        machine.close()


if __name__ == "__main__":
    main()
