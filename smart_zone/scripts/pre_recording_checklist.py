"""Pre-recording checklist: verifies the things that would otherwise only
be discovered live, in front of the camera, mid-recording. Run this before
`python -m smart_zone.app --sim --record demo.mp4` and don't record until
it prints READY TO RECORD.

Checks:
  1. config/calibration.yaml has real (non-placeholder-looking) point
     correspondences, not a synthetic/round-number stand-in.
  2. machine_geometry.pivot_m falls within (or very near) the calibrated
     rectangle implied by those correspondences.
  3. The zone-fit check (scripts/check_zone_fit.py's logic) still passes:
     the danger+caution zone fits inside the calibrated area at the demo's
     default swing speed, with room left over for a SAFE margin.
  4. The camera actually opens and warms up (reuses
     spatial.calibration's own warm-up/dark-frame logic, so this exercises
     the exact same path the real calibration script and app.py use).

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.scripts.pre_recording_checklist
"""

from __future__ import annotations

import math
import sys

import yaml

from smart_zone.safety.zone import compute_caution_zone_geometry, compute_zone_geometry, tangential_speed_m_s
from smart_zone.spatial.calibration import _capture_calibration_frame
from smart_zone.spatial.homography import CALIBRATION_YAML_PATH

THRESHOLDS_PATH = "smart_zone/config/thresholds.yaml"
DEFAULT_SIM_SWING_SPEED_DEG_S = 20.0
PIVOT_RECT_TOLERANCE_M = 0.15  # how far outside the rectangle the pivot may sit and still pass


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def check_calibration_is_real() -> tuple[bool, str]:
    data = _load_yaml(str(CALIBRATION_YAML_PATH))
    homography = data.get("homography", {})
    image_points = homography.get("ground_plane_points_image", [])
    world_points = homography.get("ground_plane_points_world", [])

    if not image_points or not world_points:
        return False, "No point correspondences found in calibration.yaml at all."
    if len(image_points) < 4:
        return False, f"Only {len(image_points)} point correspondence(s) found (need at least 4)."

    # Heuristic: a synthetic/placeholder calibration tends to use suspiciously
    # round pixel coordinates (exact multiples of 10, or forming a perfectly
    # axis-aligned rectangle with round corners) -- real clicked points are
    # messy. This is a heuristic, not a certainty; it's here to catch an
    # accidental leftover placeholder, not to cryptographically prove
    # authenticity.
    all_round = all(
        float(coord).is_integer() and int(coord) % 10 == 0
        for point in image_points for coord in point
    )
    if all_round:
        return False, (
            f"Image points look suspiciously round ({image_points}) -- this may still be "
            "a synthetic/placeholder calibration rather than real clicked points. If you "
            "already ran the real calibration and it happened to click very clean pixel "
            "positions, this is a false alarm -- otherwise, re-run "
            "`python -m smart_zone.spatial.calibration`."
        )

    return True, f"{len(image_points)} point correspondences look like real calibration data."


def check_pivot_within_rectangle() -> tuple[bool, str]:
    cal_data = _load_yaml(str(CALIBRATION_YAML_PATH))
    world_points = cal_data.get("homography", {}).get("ground_plane_points_world", [])
    if not world_points:
        return False, "No world points in calibration.yaml -- can't check pivot placement."

    xs = [p[0] for p in world_points]
    ys = [p[1] for p in world_points]
    rect_x0, rect_x1 = min(xs), max(xs)
    rect_y0, rect_y1 = min(ys), max(ys)

    thresholds = _load_yaml(THRESHOLDS_PATH)
    pivot = thresholds.get("machine_geometry", {}).get("pivot_m")
    if pivot is None:
        return False, "machine_geometry.pivot_m is missing from thresholds.yaml."

    px, py = pivot
    within_x = (rect_x0 - PIVOT_RECT_TOLERANCE_M) <= px <= (rect_x1 + PIVOT_RECT_TOLERANCE_M)
    within_y = (rect_y0 - PIVOT_RECT_TOLERANCE_M) <= py <= (rect_y1 + PIVOT_RECT_TOLERANCE_M)

    if within_x and within_y:
        return True, f"pivot_m {pivot} is within the calibrated rectangle [{rect_x0},{rect_x1}] x [{rect_y0},{rect_y1}]."
    return False, (
        f"pivot_m {pivot} is OUTSIDE the calibrated rectangle "
        f"[{rect_x0},{rect_x1}] x [{rect_y0},{rect_y1}] (tolerance {PIVOT_RECT_TOLERANCE_M}m)."
    )


def check_zone_fit() -> tuple[bool, str]:
    cal_data = _load_yaml(str(CALIBRATION_YAML_PATH))
    world_points = cal_data.get("homography", {}).get("ground_plane_points_world", [])
    if not world_points:
        return False, "No world points in calibration.yaml -- can't check zone fit."

    xs = [p[0] for p in world_points]
    ys = [p[1] for p in world_points]
    rect_w = max(xs) - min(xs)
    rect_h = max(ys) - min(ys)

    thresholds = _load_yaml(THRESHOLDS_PATH)
    pivot = tuple(thresholds["machine_geometry"]["pivot_m"])
    radius_m = thresholds["machine_geometry"]["radius_m"]
    zone_cfg = thresholds["safety"]["zone"]

    corners = [(min(xs), min(ys)), (max(xs), min(ys)), (min(xs), max(ys)), (max(xs), max(ys))]
    farthest_corner = max(corners, key=lambda c: math.hypot(c[0] - pivot[0], c[1] - pivot[1]))
    farthest_dist = math.hypot(farthest_corner[0] - pivot[0], farthest_corner[1] - pivot[1])

    danger = compute_zone_geometry(
        pivot, current_angle_deg=0.0, angular_speed_deg_s=DEFAULT_SIM_SWING_SPEED_DEG_S, radius_m=radius_m,
        stopping_coeff=zone_cfg["stopping_coeff"], human_speed_mps=zone_cfg["human_speed_mps"],
        reaction_time_s=zone_cfg["reaction_time_s"], margin_m=zone_cfg["margin_m"],
        baseline_radius_m=zone_cfg["baseline_radius_m"], offset_ratio=zone_cfg["offset_ratio"],
    )
    caution = compute_caution_zone_geometry(danger, caution_band_m=zone_cfg["caution_band_m"])

    v = tangential_speed_m_s(DEFAULT_SIM_SWING_SPEED_DEG_S, radius_m)
    offset = zone_cfg["offset_ratio"] * v
    worst_case_reach = offset + caution.semi_major_m
    margin_left = farthest_dist - worst_case_reach

    if margin_left > 0:
        return True, (
            f"Zone fits: worst-case reach {worst_case_reach:.3f}m at {DEFAULT_SIM_SWING_SPEED_DEG_S} deg/s "
            f"vs. farthest corner {farthest_dist:.3f}m -- {margin_left:.3f}m of SAFE margin remains."
        )
    return False, (
        f"Zone does NOT fit: worst-case reach {worst_case_reach:.3f}m at {DEFAULT_SIM_SWING_SPEED_DEG_S} deg/s "
        f"exceeds the farthest corner ({farthest_dist:.3f}m) by {-margin_left:.3f}m. "
        f"Reduce margin_m/caution_band_m in thresholds.yaml, or keep swing speed below "
        f"{DEFAULT_SIM_SWING_SPEED_DEG_S} deg/s during the recording."
    )


def check_camera(camera_index: int = 0) -> tuple[bool, str]:
    try:
        frame = _capture_calibration_frame(camera_index)
        return True, f"Camera index {camera_index} opened, warmed up, and delivered a usable frame (shape {frame.shape})."
    except RuntimeError as e:
        return False, f"Camera check failed: {e}"


def main() -> None:
    checks = [
        ("Calibration is real (not synthetic/placeholder)", check_calibration_is_real),
        ("Pivot falls within the calibrated rectangle", check_pivot_within_rectangle),
        ("Danger+caution zone fits the calibrated area", check_zone_fit),
        ("Camera opens and warms up correctly", check_camera),
    ]

    print("=" * 70)
    print("Smart-Zone Edge Guardian -- pre-recording checklist")
    print("=" * 70)

    all_passed = True
    for label, check_fn in checks:
        try:
            passed, detail = check_fn()
        except Exception as e:
            passed, detail = False, f"Check raised an exception: {e}"
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {label}")
        print(f"       {detail}")

    print("=" * 70)
    if all_passed:
        print("READY TO RECORD")
    else:
        print("NOT READY -- fix the FAIL items above before recording.")
    print("=" * 70)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
