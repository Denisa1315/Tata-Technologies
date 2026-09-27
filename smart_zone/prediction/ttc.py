"""Time-to-collision: worker's ground-plane distance to the nearest edge of
the current dynamic safety zone, divided by the component of the worker's
Kalman-filtered velocity directed toward that edge.

"Nearest edge" is resolved along the worker's own velocity direction: we
find where the ray from the worker's position, in the direction it's
actually moving, crosses the zone ellipse boundary. That is the edge point
relevant to a collision, not necessarily the geometrically closest boundary
point (which could be off to the side, in a direction the worker isn't
moving toward at all).

If the worker isn't moving, or is moving away from the zone (the ray never
crosses the boundary in the direction of travel), returns None -- no
collision is imminent along the current trajectory.
"""

from __future__ import annotations

import math

from smart_zone.safety.zone import ZoneGeometry, is_point_inside_zone

MIN_SPEED_M_S = 1e-6  # below this, treat the worker as stationary


def _ray_ellipse_intersection_distance(
    zone: ZoneGeometry,
    origin: tuple[float, float],
    direction: tuple[float, float],
) -> float | None:
    """Distance along `direction` (a unit vector) from `origin` to the first
    forward intersection with the zone ellipse boundary, or None if the ray
    never crosses it going forward."""
    ox, oy = origin
    cx, cy = zone.center
    dx0, dy0 = ox - cx, oy - cy
    dirx, diry = direction

    theta = math.radians(-zone.orientation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    # Rotate origin-relative-to-center and direction into the ellipse's own
    # (axis-aligned) frame, then scale by semi-axis lengths so the ellipse
    # becomes a unit circle -- reduces the problem to a quadratic in t.
    ox_r = (dx0 * cos_t - dy0 * sin_t) / zone.semi_major_m
    oy_r = (dx0 * sin_t + dy0 * cos_t) / zone.semi_minor_m
    dx_r = (dirx * cos_t - diry * sin_t) / zone.semi_major_m
    dy_r = (dirx * sin_t + diry * cos_t) / zone.semi_minor_m

    a = dx_r**2 + dy_r**2
    b = 2 * (ox_r * dx_r + oy_r * dy_r)
    c = ox_r**2 + oy_r**2 - 1.0

    if a < 1e-12:
        return None  # zero-length direction, shouldn't happen with a unit vector

    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        return None  # ray's line never touches the ellipse

    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)

    # Note: t is the parameter in the *rotated-and-scaled* frame, but since
    # direction was scaled by the same semi-axis factors as origin, t is
    # still in real-world distance units along the original unit direction.
    forward_ts = [t for t in (t1, t2) if t > 0]
    if not forward_ts:
        return None
    return min(forward_ts)


def time_to_collision_s(
    worker_position: tuple[float, float],
    worker_velocity: tuple[float, float],
    zone: ZoneGeometry,
) -> float | None:
    """Seconds until the worker's Kalman-filtered trajectory crosses the
    nearest edge of the zone ellipse, or None if they're stationary, moving
    away, or on a path that never reaches the boundary. Returns 0.0 if the
    worker's current position is already inside the zone -- the collision
    condition is already true now, not at some future exit time."""
    if is_point_inside_zone(zone, worker_position):
        return 0.0

    vx, vy = worker_velocity
    speed = math.hypot(vx, vy)
    if speed < MIN_SPEED_M_S:
        return None

    direction = (vx / speed, vy / speed)
    distance_m = _ray_ellipse_intersection_distance(zone, worker_position, direction)
    if distance_m is None:
        return None

    return distance_m / speed
