"""Kinematic model: projects the machine's current angle/angular speed into
predicted leading-edge ground-plane positions over a short time horizon.

The machine is modeled as a rigid arm of length `radius_m` rotating about a
fixed pivot point in ground-plane coordinates (the excavator's slew axis).
Only angle and angular speed come from telemetry (real or mock) -- pivot
location and radius are calibration/config values describing the physical
machine, supplied by the caller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LeadingEdgePoint:
    t_s: float  # seconds from now
    x: float
    y: float
    angle_deg: float


def predict_leading_edge_positions(
    current_angle_deg: float,
    angular_speed_deg_s: float,
    pivot: tuple[float, float],
    radius_m: float,
    horizon_s: float = 1.0,
    n_steps: int = 10,
) -> list[LeadingEdgePoint]:
    """Predict the leading edge's ground-plane (x, y) at n_steps evenly spaced
    times over [0, horizon_s], assuming constant angular speed (matches the
    constant-velocity model used elsewhere in this project -- no acceleration
    term, since telemetry only reports instantaneous angle/speed).

    angle_deg is measured counterclockwise from the +x world axis, consistent
    with the ground-plane coordinate frame established by the homography.
    """
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")
    if radius_m <= 0:
        raise ValueError("radius_m must be > 0")

    pivot_x, pivot_y = pivot
    points: list[LeadingEdgePoint] = []

    for step in range(n_steps + 1):
        t_s = horizon_s * step / n_steps
        angle_deg = current_angle_deg + angular_speed_deg_s * t_s
        angle_rad = math.radians(angle_deg)

        x = pivot_x + radius_m * math.cos(angle_rad)
        y = pivot_y + radius_m * math.sin(angle_rad)

        points.append(LeadingEdgePoint(t_s=t_s, x=x, y=y, angle_deg=angle_deg))

    return points


def current_leading_edge_position(
    current_angle_deg: float,
    pivot: tuple[float, float],
    radius_m: float,
) -> tuple[float, float]:
    """Convenience wrapper: leading-edge ground-plane position right now (t=0)."""
    points = predict_leading_edge_positions(
        current_angle_deg=current_angle_deg,
        angular_speed_deg_s=0.0,
        pivot=pivot,
        radius_m=radius_m,
        horizon_s=0.0,
        n_steps=1,
    )
    return points[0].x, points[0].y
