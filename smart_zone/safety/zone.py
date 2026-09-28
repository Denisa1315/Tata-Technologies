"""Dynamic safety zone: an explainable, physics-derived danger ellipse
around the machine, plus a caution ring around that.

Deliberate architectural decision (per project spec, not a placeholder):
the zone is an ellipse, not a fixed circle and not a full swept-path
polygon. It is centered near the machine's slew pivot (offset slightly
toward the swing direction -- see below), oriented along its current
tangential swing direction.

Sizing formula (the "protective distance" -- the danger ellipse's
semi-major length along the swing heading):

    protective_distance = stopping_coeff * tangential_speed
                          + human_speed_mps * reaction_time_s
                          + margin_m

This is a standard stopping-sight-distance style formula, each term
independently explainable:
  - stopping_coeff * tangential_speed: how far the leading edge travels
    during a fixed braking-response window (stopping_coeff acts as a
    seconds-equivalent response/braking-time coefficient) -- this is the
    only speed-dependent term, so the zone grows with swing speed.
  - human_speed_mps * reaction_time_s: how far a worker could still close
    the distance during the system's reaction time, regardless of machine
    speed.
  - margin_m: a fixed safety pad on top of both.

At zero swing speed the ellipse degenerates to a CIRCLE of radius
baseline_radius_m (never zero, never NaN, and independent of the formula
above, which is specifically for the swinging case) -- see
compute_zone_geometry. The semi-minor (lateral) length is always a fixed
fraction of the danger semi-major length, so the ellipse never has a
zero-width lateral extent either.

The ellipse center is offset from the pivot toward the current swing
heading by offset_ratio * tangential_speed meters -- zero at zero speed
(so the stationary baseline circle stays exactly centered on the pivot,
as required), growing as the machine swings faster (the zone leans into
where the arm is actually heading).

The caution zone is the danger ellipse grown by a fixed caution_band_m in
both semi-axes (not a size ratio) -- a uniform-width ring around the
danger boundary, not a rescaled copy of its shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# Legacy defaults, kept for the use_prediction=True path (see risk_engine.py).
DEFAULT_CORE_RATIO = 0.5

DEFAULT_STOPPING_COEFF = 0.3
DEFAULT_HUMAN_SPEED_MPS = 1.6
DEFAULT_REACTION_TIME_S = 0.3
DEFAULT_MARGIN_M = 0.1
DEFAULT_CAUTION_BAND_M = 0.7
DEFAULT_BASELINE_RADIUS_M = 0.58
DEFAULT_OFFSET_RATIO = 0.3

# Lateral (semi-minor) extent of the danger ellipse, as a fraction of its
# semi-major (protective_distance) length. Keeps the ellipse from ever
# having a degenerate zero-width lateral extent, and keeps its shape
# consistent regardless of speed.
DANGER_SEMI_MINOR_RATIO = 0.6


class ZoneLevel(Enum):
    OUTSIDE = "OUTSIDE"
    CAUTION = "CAUTION"
    DANGER = "DANGER"


@dataclass(frozen=True)
class ZoneGeometry:
    center: tuple[float, float]
    orientation_deg: float  # ellipse major-axis direction, world frame (CCW from +x)
    semi_major_m: float
    semi_minor_m: float


def tangential_speed_m_s(angular_speed_deg_s: float, radius_m: float) -> float:
    """Linear (tangential) speed of the leading edge, m/s, from angular speed."""
    return abs(math.radians(angular_speed_deg_s)) * radius_m


def swing_heading_deg(current_angle_deg: float, angular_speed_deg_s: float) -> float:
    """Direction the leading edge is currently swinging toward: tangent to the
    swing circle, rotated +90 deg from the radial arm direction for positive
    (CCW) angular speed, -90 deg for negative (CW) angular speed. If angular
    speed is ~0, heading falls back to the arm's radial direction (no swing
    direction to lead with)."""
    if abs(angular_speed_deg_s) < 1e-6:
        return current_angle_deg
    sign = 1.0 if angular_speed_deg_s > 0 else -1.0
    return current_angle_deg + sign * 90.0


def protective_distance_m(
    tangential_speed_mps: float,
    stopping_coeff: float = DEFAULT_STOPPING_COEFF,
    human_speed_mps: float = DEFAULT_HUMAN_SPEED_MPS,
    reaction_time_s: float = DEFAULT_REACTION_TIME_S,
    margin_m: float = DEFAULT_MARGIN_M,
) -> float:
    """protective_distance = stopping_coeff * tangential_speed
                             + human_speed_mps * reaction_time_s + margin_m
    See module docstring for the rationale behind each term."""
    return stopping_coeff * tangential_speed_mps + human_speed_mps * reaction_time_s + margin_m


def compute_zone_geometry(
    pivot: tuple[float, float],
    current_angle_deg: float,
    angular_speed_deg_s: float,
    radius_m: float,
    stopping_coeff: float = DEFAULT_STOPPING_COEFF,
    human_speed_mps: float = DEFAULT_HUMAN_SPEED_MPS,
    reaction_time_s: float = DEFAULT_REACTION_TIME_S,
    margin_m: float = DEFAULT_MARGIN_M,
    baseline_radius_m: float = DEFAULT_BASELINE_RADIUS_M,
    offset_ratio: float = DEFAULT_OFFSET_RATIO,
) -> ZoneGeometry:
    """Compute the current DANGER ellipse geometry for drawing/point-containment.

    At zero tangential speed this is exactly a circle of radius
    baseline_radius_m, centered exactly on the pivot (offset=0) -- never
    zero-sized, never NaN, independent of the swing-speed formula. As
    tangential speed increases, the ellipse grows along the swing heading
    per protective_distance_m() and its center shifts toward that heading.
    """
    speed_m_s = tangential_speed_m_s(angular_speed_deg_s, radius_m)
    heading_deg = swing_heading_deg(current_angle_deg, angular_speed_deg_s)

    if speed_m_s <= 0.0:
        return ZoneGeometry(
            center=pivot,
            orientation_deg=heading_deg,
            semi_major_m=baseline_radius_m,
            semi_minor_m=baseline_radius_m,
        )

    semi_major = protective_distance_m(
        speed_m_s, stopping_coeff, human_speed_mps, reaction_time_s, margin_m
    )
    semi_minor = semi_major * DANGER_SEMI_MINOR_RATIO

    offset_m = offset_ratio * speed_m_s
    heading_rad = math.radians(heading_deg)
    center = (
        pivot[0] + offset_m * math.cos(heading_rad),
        pivot[1] + offset_m * math.sin(heading_rad),
    )

    return ZoneGeometry(
        center=center,
        orientation_deg=heading_deg,
        semi_major_m=semi_major,
        semi_minor_m=semi_minor,
    )


def compute_caution_zone_geometry(
    danger_zone: ZoneGeometry,
    caution_band_m: float = DEFAULT_CAUTION_BAND_M,
) -> ZoneGeometry:
    """The outer CAUTION ellipse: the danger ellipse grown by a fixed
    caution_band_m in both semi-axes (a uniform-width ring around the
    danger boundary, not a rescaled copy of its shape)."""
    if caution_band_m < 0.0:
        raise ValueError("caution_band_m must be >= 0")
    return ZoneGeometry(
        center=danger_zone.center,
        orientation_deg=danger_zone.orientation_deg,
        semi_major_m=danger_zone.semi_major_m + caution_band_m,
        semi_minor_m=danger_zone.semi_minor_m + caution_band_m,
    )


def compute_core_zone_geometry(
    outer_zone: ZoneGeometry,
    core_ratio: float = DEFAULT_CORE_RATIO,
) -> ZoneGeometry:
    """Legacy helper for the use_prediction=True path: an inset ellipse
    scaled down by core_ratio from `outer_zone`. Not used by the
    position-only (use_prediction=False) zone-level logic, which uses
    compute_caution_zone_geometry's fixed-width ring instead."""
    if not 0.0 < core_ratio <= 1.0:
        raise ValueError("core_ratio must be in (0, 1]")
    return ZoneGeometry(
        center=outer_zone.center,
        orientation_deg=outer_zone.orientation_deg,
        semi_major_m=outer_zone.semi_major_m * core_ratio,
        semi_minor_m=outer_zone.semi_minor_m * core_ratio,
    )


def is_point_inside_zone(zone: ZoneGeometry, point: tuple[float, float]) -> bool:
    """True if `point` (ground-plane x, y meters) lies inside the ellipse."""
    px, py = point
    cx, cy = zone.center

    dx = px - cx
    dy = py - cy

    theta = math.radians(-zone.orientation_deg)
    # Rotate the point into the ellipse's own (major-axis-aligned) frame.
    x_rot = dx * math.cos(theta) - dy * math.sin(theta)
    y_rot = dx * math.sin(theta) + dy * math.cos(theta)

    normalized = (x_rot / zone.semi_major_m) ** 2 + (y_rot / zone.semi_minor_m) ** 2
    return normalized <= 1.0


def zone_level_for_point(
    danger_zone: ZoneGeometry,
    caution_zone: ZoneGeometry,
    point: tuple[float, float],
) -> ZoneLevel:
    """Classify a ground-plane point as OUTSIDE, CAUTION, or DANGER relative
    to the given danger/caution ellipses (caution_zone must be the danger
    ellipse grown by compute_caution_zone_geometry, i.e. it always contains
    the danger ellipse)."""
    if is_point_inside_zone(danger_zone, point):
        return ZoneLevel.DANGER
    if is_point_inside_zone(caution_zone, point):
        return ZoneLevel.CAUTION
    return ZoneLevel.OUTSIDE
