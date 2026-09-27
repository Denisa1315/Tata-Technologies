"""Dynamic safety zone: a heading-and-speed-scaled ellipse around the machine.

Deliberate architectural decision (per project spec, not a placeholder):
the zone is an ellipse, not a fixed circle and not a full swept-path
polygon. It is centered on the machine's slew pivot, oriented along its
current tangential swing direction, and elongated in that direction as
tangential speed increases -- so the zone reaches further, faster, in the
direction the arm is currently swinging toward, and shrinks back down when
the machine is still.

Heading here means the instantaneous direction of leading-edge motion
(tangent to the swing circle, sign given by angular_speed_deg_s), not the
static direction the arm currently points -- see machine/kinematics.py for
the underlying radial arm model this is derived from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SEMI_MAJOR_M = 1.5   # zone extent straight ahead even when stationary
MIN_SEMI_MINOR_M = 1.0   # lateral zone extent even when stationary
SPEED_TO_MAJOR_GAIN = 0.6  # extra meters of semi-major length per m/s of tangential speed
SPEED_TO_MINOR_GAIN = 0.15  # extra meters of semi-minor length per m/s of tangential speed

DEFAULT_CORE_RATIO = 0.5  # core (CRITICAL) ellipse size relative to the outer margin (WARNING) ellipse


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


def compute_zone_geometry(
    pivot: tuple[float, float],
    current_angle_deg: float,
    angular_speed_deg_s: float,
    radius_m: float,
) -> ZoneGeometry:
    """Compute the current ellipse geometry for drawing/point-containment."""
    speed_m_s = tangential_speed_m_s(angular_speed_deg_s, radius_m)
    heading_deg = swing_heading_deg(current_angle_deg, angular_speed_deg_s)

    semi_major = MIN_SEMI_MAJOR_M + SPEED_TO_MAJOR_GAIN * speed_m_s
    semi_minor = MIN_SEMI_MINOR_M + SPEED_TO_MINOR_GAIN * speed_m_s

    return ZoneGeometry(
        center=pivot,
        orientation_deg=heading_deg,
        semi_major_m=semi_major,
        semi_minor_m=semi_minor,
    )


def compute_core_zone_geometry(
    outer_zone: ZoneGeometry,
    core_ratio: float = DEFAULT_CORE_RATIO,
) -> ZoneGeometry:
    """The inner "core" ellipse (CRITICAL boundary): same center/orientation
    as the outer margin ellipse (WARNING boundary), scaled down by
    core_ratio. This is the immediate-danger zone right around the machine;
    the outer margin is the early-warning buffer around that."""
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
