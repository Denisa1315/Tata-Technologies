"""Scripted (non-live-camera) check of zone sizing against the calibrated
test area: places synthetic workers at the farthest rectangle corner from
the pivot, at the pivot itself, and at the midpoint between them, and
prints the resulting zone_level and system risk state for each -- using
the real safety.zone / safety.risk_engine / safety.confidence modules and
the actual config/thresholds.yaml values, not guessed numbers.

Useful any time you recalibrate or retune zone sizing (margin_m,
caution_band_m, baseline_radius_m, pivot_m, radius_m) and want to sanity
check the result before testing live in front of the camera.

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.scripts.check_zone_fit
    python -m smart_zone.scripts.check_zone_fit --corner 1.5 0.0 --speed 20
"""

from __future__ import annotations

import argparse
import math

import yaml

from smart_zone.safety.confidence import assess_confidence, apply_confidence_to_zone_level, range_based_margin_m
from smart_zone.safety.risk_engine import HealthStatus, RiskEngine, WorkerObservation
from smart_zone.safety.zone import (
    compute_caution_zone_geometry,
    compute_zone_geometry,
    tangential_speed_m_s,
    zone_level_for_point,
)
from smart_zone.spatial.homography import CALIBRATION_YAML_PATH, load_homography_from_yaml

THRESHOLDS_PATH = "smart_zone/config/thresholds.yaml"
FRAME_HEIGHT_PX = 1080.0  # only used for the confidence check's feet-visibility test; irrelevant here
HIGH_CONFIDENCE_BBOX = (900.0, 300.0, 1000.0, 700.0)  # a plausible, well-formed box for a HIGH-confidence read

HEALTHY = HealthStatus(camera_alive=True, telemetry_alive=True, fps=30.0)


def _load_thresholds() -> dict:
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


def _farthest_corner(pivot: tuple[float, float], rect_w: float, rect_h: float) -> tuple[float, float]:
    corners = [(0.0, 0.0), (rect_w, 0.0), (0.0, rect_h), (rect_w, rect_h)]
    return max(corners, key=lambda c: math.hypot(c[0] - pivot[0], c[1] - pivot[1]))


def _evaluate_point(
    label: str,
    position: tuple[float, float],
    pivot: tuple[float, float],
    radius_m: float,
    angle_deg: float,
    angular_speed_deg_s: float,
    camera_ground_position: tuple[float, float],
    zone_cfg: dict,
    confidence_cfg: dict,
    risk_engine: RiskEngine,
) -> None:
    danger = compute_zone_geometry(
        pivot, angle_deg, angular_speed_deg_s, radius_m,
        stopping_coeff=zone_cfg["stopping_coeff"], human_speed_mps=zone_cfg["human_speed_mps"],
        reaction_time_s=zone_cfg["reaction_time_s"], margin_m=zone_cfg["margin_m"],
        baseline_radius_m=zone_cfg["baseline_radius_m"], offset_ratio=zone_cfg["offset_ratio"],
    )
    caution = compute_caution_zone_geometry(danger, caution_band_m=zone_cfg["caution_band_m"])

    raw_level = zone_level_for_point(danger, caution, position)
    conf = assess_confidence(
        HIGH_CONFIDENCE_BBOX, position, camera_ground_position, pivot, FRAME_HEIGHT_PX,
        edge_margin_px=confidence_cfg["edge_margin_px"],
        height_disagreement_ratio_threshold=confidence_cfg["height_disagreement_ratio"],
        reference_height_px_at_1m=confidence_cfg["reference_height_px_at_1m"],
    )
    margin = range_based_margin_m(
        conf.distance_to_camera_m,
        slope_m_per_m=confidence_cfg["range_margin_slope_m_per_m"],
        max_margin_m=confidence_cfg["range_margin_max_m"],
    )
    widened = compute_caution_zone_geometry(danger, caution_band_m=zone_cfg["caution_band_m"] + margin)
    level_with_margin = zone_level_for_point(danger, widened, position)
    zone_level = apply_confidence_to_zone_level(raw_level, conf.confidence, level_with_margin)

    machine_speed = tangential_speed_m_s(angular_speed_deg_s, radius_m)
    obs = WorkerObservation(position=position, zone_level=zone_level, distance_from_pivot_m=conf.distance_to_machine_m)
    assessment = risk_engine.evaluate([obs], HEALTHY, machine_speed)

    dist_from_pivot = math.hypot(position[0] - pivot[0], position[1] - pivot[1])
    print(
        f"{label:28s} pos={position!s:16s} dist_from_pivot={dist_from_pivot:.3f}m "
        f"zone_level={zone_level.value:8s} confidence={conf.confidence.value:5s} "
        f"-> system_state={assessment.state.name}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Check zone sizing against a calibrated test rectangle")
    parser.add_argument("--rect-w", type=float, default=1.5, help="Test rectangle width, meters (default 1.5)")
    parser.add_argument("--rect-h", type=float, default=1.0, help="Test rectangle height, meters (default 1.0)")
    parser.add_argument("--speed", type=float, default=20.0, help="Swing speed, deg/s (default 20, the demo default)")
    parser.add_argument("--corner", type=float, nargs=2, metavar=("X", "Y"), default=None,
                         help="Override the farthest corner (default: auto-computed from the pivot and rectangle)")
    args = parser.parse_args()

    cfg = _load_thresholds()
    pivot = tuple(cfg["machine_geometry"]["pivot_m"])
    radius_m = cfg["machine_geometry"]["radius_m"]
    camera_ground_position = tuple(cfg["camera_geometry"]["ground_position_m"])
    zone_cfg = cfg["safety"]["zone"]
    risk_cfg = cfg["safety"]["risk_engine"]
    confidence_cfg = cfg["safety"]["confidence"]

    try:
        load_homography_from_yaml(CALIBRATION_YAML_PATH)
        print(f"Using real calibration from {CALIBRATION_YAML_PATH}\n")
    except ValueError:
        print(f"!! No calibration found at {CALIBRATION_YAML_PATH} -- this check only "
              f"exercises zone/risk math, so it still runs, but note the pivot/rectangle "
              f"numbers below aren't tied to a real calibrated frame.\n")

    farthest_corner = tuple(args.corner) if args.corner else _farthest_corner(pivot, args.rect_w, args.rect_h)
    midpoint = ((pivot[0] + farthest_corner[0]) / 2.0, (pivot[1] + farthest_corner[1]) / 2.0)

    print(f"pivot_m = {pivot}, radius_m = {radius_m}")
    print(f"test rectangle = {args.rect_w}m x {args.rect_h}m, swing speed = {args.speed} deg/s")
    print(f"farthest corner from pivot = {farthest_corner}")
    print(f"midpoint (pivot <-> farthest corner) = {midpoint}\n")

    risk_engine = RiskEngine(
        use_prediction=risk_cfg["use_prediction"],
        ttc_warning_s=risk_cfg["ttc_warning_s"], ttc_critical_s=risk_cfg["ttc_critical_s"],
        debounce_s=risk_cfg["debounce_s"], fps_floor=risk_cfg["fps_floor"],
        quiet_when_stationary=risk_cfg["quiet_when_stationary"],
        stationary_speed_threshold_m_s=risk_cfg["stationary_speed_threshold_m_s"],
        arm_reach_m=radius_m,
    )

    # Each point gets a fresh engine instance so escalation/debounce from
    # one point can't leak into the next -- these are independent checks,
    # not a continuous scenario.
    for label, position in [
        ("(a) farthest corner", farthest_corner),
        ("(b) at the pivot", pivot),
        ("(c) midpoint", midpoint),
    ]:
        fresh_engine = RiskEngine(
            use_prediction=risk_cfg["use_prediction"],
            ttc_warning_s=risk_cfg["ttc_warning_s"], ttc_critical_s=risk_cfg["ttc_critical_s"],
            debounce_s=risk_cfg["debounce_s"], fps_floor=risk_cfg["fps_floor"],
            quiet_when_stationary=risk_cfg["quiet_when_stationary"],
            stationary_speed_threshold_m_s=risk_cfg["stationary_speed_threshold_m_s"],
            arm_reach_m=radius_m,
        )
        _evaluate_point(
            label, position, pivot, radius_m, angle_deg=0.0, angular_speed_deg_s=args.speed,
            camera_ground_position=camera_ground_position, zone_cfg=zone_cfg,
            confidence_cfg=confidence_cfg, risk_engine=fresh_engine,
        )


if __name__ == "__main__":
    main()
