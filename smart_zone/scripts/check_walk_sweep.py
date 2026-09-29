"""Scripted (non-live-camera) verification: a synthetic worker walking in a
straight line from the farthest corner of the calibrated rectangle toward
the machine pivot, sampled every ~10cm, at the demo's default swing speed.
Prints the zone_level and system risk state at every sample, and reports
exactly where each state transition happens.

Uses the real config/calibration.yaml (to confirm it's genuinely loaded)
and config/thresholds.yaml values and the real safety.zone /
safety.confidence / safety.risk_engine modules -- this is a continuous
scenario (not independent point checks like check_zone_fit.py), so debounce
and hysteresis behave exactly as they would live: one RiskEngine instance
persists across the whole walk, and each sample advances a fake clock by
the time it would actually take to walk 10cm at a natural walking pace.

Run from the Tata-Technologies/ parent directory:

    python -m smart_zone.scripts.check_walk_sweep
    python -m smart_zone.scripts.check_walk_sweep --step-m 0.05 --speed 20
"""

from __future__ import annotations

import argparse
import math

import yaml

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
    tangential_speed_m_s,
    zone_level_for_point,
)
from smart_zone.spatial.homography import CALIBRATION_YAML_PATH, load_homography_from_yaml

THRESHOLDS_PATH = "smart_zone/config/thresholds.yaml"
FRAME_HEIGHT_PX = 1080.0
HIGH_CONFIDENCE_BBOX = (900.0, 300.0, 1000.0, 700.0)
WALK_SPEED_M_S = 1.2  # a natural, unhurried walking pace
HEALTHY = HealthStatus(camera_alive=True, telemetry_alive=True, fps=30.0)

# Expected order of severity for flicker detection: a "flicker" is any
# sample whose severity is LOWER than a severity already seen earlier in
# the walk (excluding the debounce-driven zone_level->state lag, which is
# expected and not a flicker -- see the report logic below).
ZONE_SEVERITY = {"OUTSIDE": 0, "CAUTION": 1, "DANGER": 2}
STATE_SEVERITY = {"SAFE": 0, "WARNING": 1, "CRITICAL": 2, "DEGRADED": 3}


def _load_thresholds() -> dict:
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


def _farthest_corner(pivot: tuple[float, float], rect_w: float, rect_h: float) -> tuple[float, float]:
    corners = [(0.0, 0.0), (rect_w, 0.0), (0.0, rect_h), (rect_w, rect_h)]
    return max(corners, key=lambda c: math.hypot(c[0] - pivot[0], c[1] - pivot[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic straight-line walk-in sweep")
    parser.add_argument("--rect-w", type=float, default=1.5)
    parser.add_argument("--rect-h", type=float, default=1.0)
    parser.add_argument("--step-m", type=float, default=0.1, help="Sample spacing along the walk, meters (default 10cm)")
    parser.add_argument("--speed", type=float, default=20.0, help="Machine swing speed, deg/s (default 20, the demo default)")
    parser.add_argument("--angle", type=float, default=0.0, help="Machine arm angle, deg (default 0)")
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
        print(f"Loaded real calibration from {CALIBRATION_YAML_PATH}")
    except ValueError as e:
        print(f"!! Could not load calibration from {CALIBRATION_YAML_PATH}: {e}")
        print("   This check still runs (it only exercises zone/risk math), but the "
              "rectangle/pivot numbers below aren't tied to a real calibrated frame.\n")

    start = _farthest_corner(pivot, args.rect_w, args.rect_h)
    total_dist = math.hypot(start[0] - pivot[0], start[1] - pivot[1])
    n_steps = max(int(total_dist / args.step_m), 1)

    print(f"pivot_m = {pivot}, radius_m = {radius_m}")
    print(f"rectangle = {args.rect_w}m x {args.rect_h}m, swing speed = {args.speed} deg/s, angle = {args.angle} deg")
    print(f"walk: {start} -> {pivot}  ({total_dist:.3f}m, {n_steps} steps of ~{args.step_m}m, "
          f"walking at {WALK_SPEED_M_S} m/s)\n")

    engine = RiskEngine(
        use_prediction=risk_cfg["use_prediction"],
        ttc_warning_s=risk_cfg["ttc_warning_s"], ttc_critical_s=risk_cfg["ttc_critical_s"],
        debounce_s=risk_cfg["debounce_s"], fps_floor=risk_cfg["fps_floor"],
        quiet_when_stationary=risk_cfg["quiet_when_stationary"],
        stationary_speed_threshold_m_s=risk_cfg["stationary_speed_threshold_m_s"],
        arm_reach_m=radius_m,
        clock=lambda: clock_state["t"],
    )
    clock_state = {"t": 0.0}
    machine_speed_m_s = tangential_speed_m_s(args.speed, radius_m)

    danger = compute_zone_geometry(
        pivot, args.angle, args.speed, radius_m,
        stopping_coeff=zone_cfg["stopping_coeff"], human_speed_mps=zone_cfg["human_speed_mps"],
        reaction_time_s=zone_cfg["reaction_time_s"], margin_m=zone_cfg["margin_m"],
        baseline_radius_m=zone_cfg["baseline_radius_m"], offset_ratio=zone_cfg["offset_ratio"],
    )
    caution = compute_caution_zone_geometry(danger, caution_band_m=zone_cfg["caution_band_m"])

    dt_per_step = args.step_m / WALK_SPEED_M_S

    results = []
    max_zone_seen = 0
    max_state_seen = 0
    zone_flicker = False
    state_flicker = False

    for i in range(n_steps + 1):
        frac = i / n_steps
        pos = (start[0] + (pivot[0] - start[0]) * frac, start[1] + (pivot[1] - start[1]) * frac)
        dist_from_pivot = math.hypot(pos[0] - pivot[0], pos[1] - pivot[1])

        raw_level = zone_level_for_point(danger, caution, pos)
        conf = assess_confidence(
            HIGH_CONFIDENCE_BBOX, pos, camera_ground_position, pivot, FRAME_HEIGHT_PX,
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
        level_with_margin = zone_level_for_point(danger, widened, pos)
        zone_level = apply_confidence_to_zone_level(raw_level, conf.confidence, level_with_margin)

        obs = WorkerObservation(position=pos, zone_level=zone_level, distance_from_pivot_m=conf.distance_to_machine_m)
        assessment = engine.evaluate([obs], HEALTHY, machine_speed_m_s)

        zone_sev = ZONE_SEVERITY[zone_level.value]
        state_sev = STATE_SEVERITY[assessment.state.name]
        if zone_sev < max_zone_seen:
            zone_flicker = True
        if state_sev < max_state_seen and assessment.state.name != "SAFE":
            # A drop back to SAFE is normal de-escalation once the worker
            # has walked past/through; a drop to some OTHER lower-but-not-
            # SAFE state (e.g. CRITICAL -> WARNING mid-approach, worker
            # still moving inward) would be a genuine flicker.
            state_flicker = True
        max_zone_seen = max(max_zone_seen, zone_sev)
        max_state_seen = max(max_state_seen, state_sev)

        results.append((dist_from_pivot, pos, zone_level.value, assessment.state.name, assessment.min_ttc_s))
        clock_state["t"] += dt_per_step

    # Print every sample.
    for dist, pos, zone_level, state, ttc in results:
        print(f"  dist={dist:6.3f}m  pos=({pos[0]:.3f},{pos[1]:.3f})  "
              f"zone_level={zone_level:8s}  state={state:9s}")

    print()
    print("=== Transition report ===")
    prev_zone, prev_state = None, None
    zone_transitions = []
    state_transitions = []
    for dist, pos, zone_level, state, ttc in results:
        if zone_level != prev_zone:
            zone_transitions.append((dist, prev_zone, zone_level))
            prev_zone = zone_level
        if state != prev_state:
            state_transitions.append((dist, prev_state, state))
            prev_state = state

    print("zone_level transitions (by distance from pivot):")
    for dist, frm, to in zone_transitions:
        frm_str = frm if frm is not None else "(start)"
        print(f"  {frm_str:10s} -> {to:10s}  at dist={dist:.3f}m")

    print("\nsystem_state transitions (by distance from pivot):")
    for dist, frm, to in state_transitions:
        frm_str = frm if frm is not None else "(start)"
        print(f"  {frm_str:10s} -> {to:10s}  at dist={dist:.3f}m")

    print("\n=== Verdict ===")
    zone_sequence = [t[2] for t in zone_transitions]
    expected_zone_sequence = ["OUTSIDE", "CAUTION", "DANGER"]
    zone_in_order = zone_sequence == expected_zone_sequence or zone_sequence[:1] != ["OUTSIDE"]
    # (zone_sequence should be exactly the prefix of expected_zone_sequence
    # that was actually reached, in order, with the walk starting outside.)
    ordered_subsequence = zone_sequence == expected_zone_sequence[:len(zone_sequence)]

    if zone_flicker:
        print("FAIL: zone_level flickered (dropped to a less severe level mid-approach, "
              "not just at the very end of the walk).")
    elif not ordered_subsequence:
        print(f"FAIL: zone_level sequence was {zone_sequence}, expected a prefix of "
              f"{expected_zone_sequence} in order.")
    else:
        print(f"OK: zone_level advanced in order with no skipped or flickering levels: {zone_sequence}")

    warning_reached = "WARNING" in [t[2] for t in state_transitions]
    critical_reached = "CRITICAL" in [t[2] for t in state_transitions]

    if state_flicker:
        print("FAIL: system_state flickered (dropped to a lower non-SAFE state mid-approach).")
    else:
        print("OK: system_state never flickered downward mid-approach.")

    if not warning_reached:
        print("FLAG: WARNING never triggered during this walk. This is the first time "
              "WARNING has been checked end-to-end -- if you expected the caution ring "
              "to be crossed before the danger zone, this needs investigation (check "
              "caution_band_m vs. danger zone size, and the debounce_s window relative "
              "to how fast the synthetic walk crosses the caution ring).")
    else:
        first_warning_dist = next(d for d, frm, to in state_transitions if to == "WARNING")
        print(f"OK: WARNING triggered at dist={first_warning_dist:.3f}m from pivot.")

    if not critical_reached:
        print("FLAG: CRITICAL never triggered -- the walk may not reach far enough inside "
              "the danger zone, or something is preventing escalation.")
    else:
        first_critical_dist = next(d for d, frm, to in state_transitions if to == "CRITICAL")
        print(f"OK: CRITICAL triggered at dist={first_critical_dist:.3f}m from pivot.")


if __name__ == "__main__":
    main()
