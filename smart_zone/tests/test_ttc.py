"""Unit tests for prediction.ttc: time-to-collision against the zone ellipse."""

from __future__ import annotations

import pytest

from smart_zone.prediction.ttc import time_to_collision_s
from smart_zone.safety.zone import ZoneGeometry

# Axis-aligned ellipse: x in [-4, 4], y in [-2, 2] around the origin.
ZONE = ZoneGeometry(center=(0.0, 0.0), orientation_deg=0.0, semi_major_m=4.0, semi_minor_m=2.0)


class TestTimeToCollision:
    def test_approaching_head_on_gives_expected_ttc(self):
        # worker at x=10, moving at -2 m/s toward the zone -> boundary at x=4,
        # distance = 6m, speed = 2 m/s -> ttc = 3s
        ttc = time_to_collision_s(worker_position=(10.0, 0.0), worker_velocity=(-2.0, 0.0), zone=ZONE)
        assert ttc == pytest.approx(3.0, abs=1e-6)

    def test_moving_away_returns_none(self):
        ttc = time_to_collision_s(worker_position=(10.0, 0.0), worker_velocity=(2.0, 0.0), zone=ZONE)
        assert ttc is None

    def test_stationary_returns_none(self):
        ttc = time_to_collision_s(worker_position=(10.0, 0.0), worker_velocity=(0.0, 0.0), zone=ZONE)
        assert ttc is None

    def test_already_inside_returns_zero(self):
        ttc = time_to_collision_s(worker_position=(1.0, 0.0), worker_velocity=(1.0, 0.0), zone=ZONE)
        assert ttc == pytest.approx(0.0)

    def test_parallel_path_missing_the_zone_returns_none(self):
        # moving along y=10 in +x direction, never crosses an ellipse capped at y in [-2,2]
        ttc = time_to_collision_s(worker_position=(-10.0, 10.0), worker_velocity=(1.0, 0.0), zone=ZONE)
        assert ttc is None

    def test_diagonal_approach_gives_positive_finite_ttc(self):
        ttc = time_to_collision_s(worker_position=(10.0, 10.0), worker_velocity=(-1.0, -1.0), zone=ZONE)
        assert ttc is not None
        assert ttc > 0.0

    def test_faster_approach_gives_shorter_ttc(self):
        slow_ttc = time_to_collision_s((10.0, 0.0), (-1.0, 0.0), ZONE)
        fast_ttc = time_to_collision_s((10.0, 0.0), (-4.0, 0.0), ZONE)
        assert fast_ttc < slow_ttc
