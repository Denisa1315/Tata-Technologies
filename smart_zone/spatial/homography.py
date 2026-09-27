"""Pixel <-> ground-plane homography for mapping detections to world coordinates."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

CALIBRATION_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "calibration.yaml"
MIN_CORRESPONDENCES = 4


def compute_homography(
    image_points: list[tuple[float, float]],
    world_points: list[tuple[float, float]],
) -> np.ndarray:
    """Compute the 3x3 homography mapping image pixel coords to ground-plane
    world coords (meters), from point correspondences.

    Requires at least 4 non-collinear correspondences. Uses RANSAC so a
    slightly noisy click/measurement doesn't wreck the whole fit.
    """
    if len(image_points) != len(world_points):
        raise ValueError("image_points and world_points must be the same length")
    if len(image_points) < MIN_CORRESPONDENCES:
        raise ValueError(
            f"Need at least {MIN_CORRESPONDENCES} point correspondences, "
            f"got {len(image_points)}"
        )

    src = np.array(image_points, dtype=np.float64)
    dst = np.array(world_points, dtype=np.float64)

    matrix, _mask = cv2.findHomography(src, dst, method=cv2.RANSAC)
    if matrix is None:
        raise ValueError("Homography computation failed (degenerate/collinear points?)")
    return matrix


def pixel_to_ground(matrix: np.ndarray, pixel_point: tuple[float, float]) -> tuple[float, float]:
    """Project a single pixel (x, y) to ground-plane (x, y) meters via the homography."""
    point = np.array([[pixel_point]], dtype=np.float64)  # shape (1, 1, 2) for perspectiveTransform
    projected = cv2.perspectiveTransform(point, matrix)
    x, y = projected[0, 0]
    return float(x), float(y)


def bbox_to_ground_position(
    matrix: np.ndarray,
    bbox_xyxy: tuple[float, float, float, float],
) -> tuple[float, float]:
    """Estimate a worker's ground-plane (x, y) position from their bounding box.

    Uses the bottom-center of the box as the ground-contact point (feet),
    which is the point on the person actually touching the floor plane —
    the box center or top would be off-plane and give a wrong projection.
    """
    x1, y1, x2, y2 = bbox_xyxy
    bottom_center = ((x1 + x2) / 2.0, y2)
    return pixel_to_ground(matrix, bottom_center)


def load_homography_from_yaml(path: Path = CALIBRATION_YAML_PATH) -> np.ndarray:
    """Load calibration.yaml and return the homography matrix.

    Recomputes from stored point correspondences if no cached matrix is
    present, so a hand-edited correspondence list still works without
    re-running the interactive calibration script.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    homography_cfg = data.get("homography", {}) if data else {}
    cached_matrix = homography_cfg.get("matrix")
    if cached_matrix is not None:
        return np.array(cached_matrix, dtype=np.float64)

    image_points = homography_cfg.get("ground_plane_points_image", [])
    world_points = homography_cfg.get("ground_plane_points_world", [])
    if not image_points or not world_points:
        raise ValueError(f"No homography matrix or point correspondences found in {path}")

    return compute_homography(
        [tuple(p) for p in image_points],
        [tuple(p) for p in world_points],
    )
