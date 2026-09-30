"""Localization confidence: per-worker distance bookkeeping and a
position-confidence score (HIGH/LOW) derived purely from the detection
geometry -- never from the risk decision itself.

Two independent signals can mark a worker LOW confidence:
  1. feet not visible: the bounding box's bottom edge sits within
     edge_margin_px of the frame's bottom edge, meaning the person's feet
     (the ground-contact point homography actually projects) are likely
     cropped out of frame -- the projected ground position is then only a
     lower bound on true distance, not a trustworthy fix.
  2. height disagreement: the box's pixel height doesn't match the height
     a person would be expected to have at the projected ground-plane
     distance from the camera. This uses a simple inverse-distance pinhole
     approximation (expected_height_px = reference_height_px_at_1m /
     distance_to_camera_m), calibrated by a single reference measurement
     rather than full camera intrinsics (none are available -- see
     config/thresholds.yaml). A large disagreement usually means the
     detection box is wrong (partial occlusion, a false-positive box, two
     people merged into one box, etc.), so the projected position is
     suspect even though a "feet visible" bottom edge looked fine.

Zone decisions still use only ground-plane position + machine geometry
(safety/zone.py) -- confidence here only decides which zone LEVEL result
to report (see apply_confidence_to_zone_level), it does not touch the
zone geometry itself. Range-based margin growth (widen the caution band
with distance_to_camera_m) is applied separately, before classification,
by the caller passing an adjusted caution_band_m into
safety.zone.compute_caution_zone_geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from smart_zone.safety.zone import ZoneLevel

DEFAULT_EDGE_MARGIN_PX = 8
DEFAULT_HEIGHT_DISAGREEMENT_RATIO = 0.35
DEFAULT_REFERENCE_HEIGHT_PX_AT_1M = 800.0
DEFAULT_RANGE_MARGIN_SLOPE_M_PER_M = 0.05
DEFAULT_RANGE_MARGIN_MAX_M = 0.5


class PositionConfidence(Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class ConfidenceAssessment:
    confidence: PositionConfidence
    feet_visible: bool
    distance_to_camera_m: float
    distance_to_machine_m: float


def distance_m(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def is_feet_visible(
    bbox_xyxy: tuple[float, float, float, float],
    frame_height_px: float,
    edge_margin_px: float = DEFAULT_EDGE_MARGIN_PX,
) -> bool:
    """False if the box's bottom edge is within edge_margin_px of the
    frame's bottom edge -- the person's feet are likely cropped out, so
    the ground-contact point the homography projects from isn't reliable."""
    _x1, _y1, _x2, y2 = bbox_xyxy
    return (frame_height_px - y2) > edge_margin_px


def expected_box_height_px(
    distance_to_camera_m: float,
    reference_height_px_at_1m: float = DEFAULT_REFERENCE_HEIGHT_PX_AT_1M,
) -> float:
    """Simple inverse-distance (pinhole) approximation: apparent height
    scales as 1/distance. reference_height_px_at_1m is a single calibrated
    measurement (a person's box height at exactly 1m from the camera),
    not full camera intrinsics."""
    distance = max(distance_to_camera_m, 1e-3)  # guard against div-by-zero for a worker at the camera
    return reference_height_px_at_1m / distance


def height_disagreement_ratio(
    bbox_xyxy: tuple[float, float, float, float],
    distance_to_camera_m: float,
    reference_height_px_at_1m: float = DEFAULT_REFERENCE_HEIGHT_PX_AT_1M,
) -> float:
    """abs(actual - expected) / expected box height, unitless."""
    _x1, y1, _x2, y2 = bbox_xyxy
    actual_height = max(y2 - y1, 1e-3)
    expected_height = expected_box_height_px(distance_to_camera_m, reference_height_px_at_1m)
    return abs(actual_height - expected_height) / expected_height


def assess_confidence(
    bbox_xyxy: tuple[float, float, float, float],
    ground_position: tuple[float, float],
    camera_ground_position: tuple[float, float],
    machine_pivot: tuple[float, float],
    frame_height_px: float,
    edge_margin_px: float = DEFAULT_EDGE_MARGIN_PX,
    height_disagreement_ratio_threshold: float = DEFAULT_HEIGHT_DISAGREEMENT_RATIO,
    reference_height_px_at_1m: float = DEFAULT_REFERENCE_HEIGHT_PX_AT_1M,
) -> ConfidenceAssessment:
    """Compute distance_to_camera_m, distance_to_machine_m, feet_visible,
    and an overall HIGH/LOW position_confidence for one worker this frame."""
    dist_camera = distance_m(ground_position, camera_ground_position)
    dist_machine = distance_m(ground_position, machine_pivot)

    feet_visible = is_feet_visible(bbox_xyxy, frame_height_px, edge_margin_px)

    disagreement = height_disagreement_ratio(bbox_xyxy, dist_camera, reference_height_px_at_1m)
    height_ok = disagreement <= height_disagreement_ratio_threshold

    confidence = PositionConfidence.HIGH if (feet_visible and height_ok) else PositionConfidence.LOW

    return ConfidenceAssessment(
        confidence=confidence,
        feet_visible=feet_visible,
        distance_to_camera_m=dist_camera,
        distance_to_machine_m=dist_machine,
    )


def range_based_margin_m(
    distance_to_camera_m: float,
    slope_m_per_m: float = DEFAULT_RANGE_MARGIN_SLOPE_M_PER_M,
    max_margin_m: float = DEFAULT_RANGE_MARGIN_MAX_M,
) -> float:
    """Extra caution-band width to account for growing localization error
    at range: grows linearly with distance_to_camera_m, capped at
    max_margin_m so a very distant (and thus low-precision) detection
    doesn't inflate the zone without bound."""
    return min(slope_m_per_m * max(distance_to_camera_m, 0.0), max_margin_m)


def apply_confidence_to_zone_level(
    zone_level: ZoneLevel,
    confidence: PositionConfidence,
    zone_level_with_margin: ZoneLevel,
) -> ZoneLevel:
    """A LOW-confidence worker is assigned the stricter zone level:
      - CAUTION becomes DANGER (the position might actually be closer than
        measured, so don't give it the benefit of the doubt).
      - OUTSIDE becomes CAUTION only if the worker is within the caution
        band PLUS the range-based uncertainty margin -- i.e. only if
        `zone_level_with_margin` (computed by the caller against a caution
        ellipse grown by range_based_margin_m) says CAUTION. A LOW-confidence
        worker who is genuinely far outside even the widened margin stays
        OUTSIDE; the point is to not miss a near-boundary worker whose true
        position might be slightly closer than the noisy detection suggests,
        not to blanket-escalate every LOW-confidence detection regardless of
        distance.
    HIGH-confidence workers are returned unchanged."""
    if confidence == PositionConfidence.HIGH:
        return zone_level
    if zone_level == ZoneLevel.CAUTION:
        return ZoneLevel.DANGER
    if zone_level == ZoneLevel.OUTSIDE and zone_level_with_margin != ZoneLevel.OUTSIDE:
        return ZoneLevel.CAUTION
    return zone_level
