"""Interactive one-time camera calibration helper.

Opens the webcam, freezes on a single frame, lets the operator click known
floor-marker points in the image, prompts for each point's real-world (x, y)
in meters, computes the homography, and saves everything to
config/calibration.yaml.

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.spatial.calibration
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

from smart_zone.spatial.homography import (
    CALIBRATION_YAML_PATH,
    MIN_CORRESPONDENCES,
    compute_homography,
)

WINDOW_NAME = "Smart-Zone Calibration - click floor markers, press 'q' when done"
POINT_COLOR = (0, 200, 0)


def _capture_calibration_frame() -> np.ndarray:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open default webcam (index 0).")
    try:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Failed to read a frame from the webcam.")
        return frame
    finally:
        cap.release()


def _collect_image_points(frame: np.ndarray) -> list[tuple[float, float]]:
    image_points: list[tuple[float, float]] = []
    display = frame.copy()

    def on_click(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            image_points.append((float(x), float(y)))
            cv2.circle(display, (x, y), 6, POINT_COLOR, -1)
            cv2.putText(
                display, str(len(image_points)), (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, POINT_COLOR, 2,
            )
            cv2.imshow(WINDOW_NAME, display)

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, on_click)
    cv2.imshow(WINDOW_NAME, display)

    print(
        "Click each floor-marker point in the window, in the same order you'll "
        "enter their real-world coordinates. Press 'q' when you've placed all "
        f"points (minimum {MIN_CORRESPONDENCES})."
    )
    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
    cv2.destroyAllWindows()

    return image_points


def _collect_world_points(n_points: int) -> list[tuple[float, float]]:
    world_points: list[tuple[float, float]] = []
    print("\nNow enter the measured real-world ground-plane coordinates (in meters).")
    for i in range(n_points):
        while True:
            raw = input(f"Point {i + 1}/{n_points} - world x,y (meters, e.g. 1.5,3.0): ").strip()
            try:
                x_str, y_str = raw.split(",")
                world_points.append((float(x_str), float(y_str)))
                break
            except ValueError:
                print("  Could not parse. Enter as: x,y  e.g.  1.5,3.0")
    return world_points


def _save_calibration(
    path: Path,
    image_points: list[tuple[float, float]],
    world_points: list[tuple[float, float]],
    matrix: np.ndarray,
) -> None:
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    data.setdefault("camera", {"intrinsics": None, "extrinsics": None})
    data["homography"] = {
        "matrix": matrix.tolist(),
        "ground_plane_points_image": [list(p) for p in image_points],
        "ground_plane_points_world": [list(p) for p in world_points],
    }

    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def run_calibration(save_path: Path = CALIBRATION_YAML_PATH) -> None:
    frame = _capture_calibration_frame()
    image_points = _collect_image_points(frame)

    if len(image_points) < MIN_CORRESPONDENCES:
        raise RuntimeError(
            f"Need at least {MIN_CORRESPONDENCES} points, got {len(image_points)}. "
            "Re-run and click more floor markers."
        )

    world_points = _collect_world_points(len(image_points))
    matrix = compute_homography(image_points, world_points)

    _save_calibration(save_path, image_points, world_points, matrix)
    print(f"\nSaved {len(image_points)} point correspondences and homography to {save_path}")


if __name__ == "__main__":
    run_calibration()
