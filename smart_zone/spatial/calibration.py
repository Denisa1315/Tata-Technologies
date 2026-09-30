"""Interactive one-time camera calibration helper.

Opens the webcam, freezes on a single frame, lets the operator click known
floor-marker points in the image, prompts for each point's real-world (x, y)
in meters, computes the homography, and saves everything to
config/calibration.yaml.

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.spatial.calibration
    python -m smart_zone.spatial.calibration --camera-index 1
"""

from __future__ import annotations

import argparse
import sys
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

# Most webcams (esp. over USB/UVC) need a handful of frames after opening
# before auto-exposure/auto-white-balance settle -- reading immediately
# after open() often returns a dark, greenish, or otherwise unrepresentative
# frame even though cap.read() reports ok=True. Skipping this many frames
# before freezing one for calibration avoids that.
WARMUP_FRAME_COUNT = 20

# A frame whose mean pixel value is at or below this is treated as
# suspiciously dark (lens cap on, camera not actually initialized yet, or a
# driver returning a black placeholder frame) and flagged rather than
# silently used.
DARK_FRAME_MEAN_THRESHOLD = 5.0


def _capture_calibration_frame(camera_index: int) -> np.ndarray:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {camera_index}. Check that no other "
            "application is using the camera, and try a different --camera-index "
            "if you have multiple cameras (e.g. a built-in one plus a USB webcam)."
        )
    try:
        print(f"Warming up camera index {camera_index} ({WARMUP_FRAME_COUNT} frames)...")
        frame = None
        for i in range(WARMUP_FRAME_COUNT):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(
                    f"cv2.VideoCapture.read() returned False on warm-up frame {i + 1}/"
                    f"{WARMUP_FRAME_COUNT} from camera index {camera_index}. The camera "
                    "opened but isn't delivering frames -- check it isn't in use by "
                    "another application, and that --camera-index is correct."
                )

        mean_brightness = float(frame.mean())
        if mean_brightness <= DARK_FRAME_MEAN_THRESHOLD:
            raise RuntimeError(
                f"Captured frame from camera index {camera_index} is suspiciously dark "
                f"(mean pixel value {mean_brightness:.1f}). Check the lens isn't covered "
                "and the room has some light, then re-run."
            )

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


def run_calibration(save_path: Path = CALIBRATION_YAML_PATH, camera_index: int = 0) -> None:
    frame = _capture_calibration_frame(camera_index)
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive camera calibration")
    parser.add_argument("--camera-index", type=int, default=0,
                         help="Camera index to open (default 0). Try 1, 2, ... if you have "
                              "multiple cameras or the wrong one opens.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run_calibration(camera_index=args.camera_index)
    except RuntimeError as e:
        print(f"\nCalibration failed: {e}", file=sys.stderr)
        sys.exit(1)
