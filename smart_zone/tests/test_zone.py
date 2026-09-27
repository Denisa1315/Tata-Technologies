"""Unit tests for safety.zone: ellipse geometry and point-containment."""

from __future__ import annotations

import math

import pytest

from smart_zone.safety.zone import (
    MIN_SEMI_MAJOR_M,
    MIN_SEMI_MINOR_M,
    ZoneGeometry,
    compute_zone_geometry,
    is_point_inside_zone,
    swing_heading_deg,
    tangential_speed_m_s,
)

PIVOT = (0.0, 0.0)
RADIUS_M = 5.0


class TestSwingHeading:
    def test_positive_angular_speed_leads_90_ccw(self):
        heading = swing_heading_deg(current_angle_deg=0.0, angular_speed_deg_s=20.0)
        assert heading == pytest.approx(90.0)

    def test_negative_angular_speed_leads_90_cw(self):
        heading = swing_heading_deg(current_angle_deg=0.0, angular_speed_deg_s=-20.0)
        assert heading == pytest.approx(-90.0)

    def test_stationary_falls_back_to_radial_direction(self):
        heading = swing_heading_deg(current_angle_deg=30.0, angular_speed_deg_s=0.0)
        assert heading == pytest.approx(30.0)


class TestTangentialSpeed:
    def test_zero_angular_speed_is_zero(self):
        assert tangential_speed_m_s(0.0, RADIUS_M) == pytest.approx(0.0)

    def test_known_angular_speed_gives_expected_linear_speed(self):
        # 180 deg/s = pi rad/s; at radius 5m -> 5*pi m/s
        speed = tangential_speed_m_s(180.0, RADIUS_M)
        assert speed == pytest.approx(5.0 * math.pi, rel=1e-6)

    def test_sign_independent(self):
        assert tangential_speed_m_s(-30.0, RADIUS_M) == tangential_speed_m_s(30.0, RADIUS_M)


class TestComputeZoneGeometry:
    def test_stationary_machine_gives_minimum_zone_size(self):
        zone = compute_zone_geometry(PIVOT, current_angle_deg=0.0, angular_speed_deg_s=0.0, radius_m=RADIUS_M)
        assert zone.semi_major_m == pytest.approx(MIN_SEMI_MAJOR_M)
        assert zone.semi_minor_m == pytest.approx(MIN_SEMI_MINOR_M)

    def test_faster_swing_grows_the_zone(self):
        slow_zone = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=5.0, radius_m=RADIUS_M)
        fast_zone = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=50.0, radius_m=RADIUS_M)
        assert fast_zone.semi_major_m > slow_zone.semi_major_m
        assert fast_zone.semi_minor_m > slow_zone.semi_minor_m

    def test_zone_is_centered_on_pivot_not_leading_edge(self):
        pivot = (7.0, -2.0)
        zone = compute_zone_geometry(pivot, 0.0, angular_speed_deg_s=20.0, radius_m=RADIUS_M)
        assert zone.center == pivot


class TestIsPointInsideZone:
    @pytest.fixture
    def axis_aligned_zone(self):
        # orientation 0 -> major axis along +x, so ellipse spans
        # x in [-4, 4], y in [-2, 2] around the origin.
        return ZoneGeometry(center=(0.0, 0.0), orientation_deg=0.0, semi_major_m=4.0, semi_minor_m=2.0)

    def test_center_is_inside(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (0.0, 0.0)) is True

    def test_known_inside_point(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (2.0, 1.0)) is True

    def test_known_outside_point(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (10.0, 10.0)) is False

    def test_point_just_outside_major_axis_tip(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (4.1, 0.0)) is False

    def test_point_just_inside_major_axis_tip(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (3.9, 0.0)) is True

    def test_point_outside_along_minor_axis_but_within_major_range(self, axis_aligned_zone):
        # x=0 is well within the major-axis span, but y=3 exceeds the
        # semi-minor length of 2 -- must be outside despite x looking "safe".
        assert is_point_inside_zone(axis_aligned_zone, (0.0, 3.0)) is False

    def test_rotated_zone_containment(self):
        # Same ellipse rotated 90 deg: major axis now along +y.
        zone = ZoneGeometry(center=(0.0, 0.0), orientation_deg=90.0, semi_major_m=4.0, semi_minor_m=2.0)
        assert is_point_inside_zone(zone, (0.0, 3.0)) is True   # inside along new major axis
        assert is_point_inside_zone(zone, (3.0, 0.0)) is False  # outside along new minor axis

    def test_offset_center(self):
        zone = ZoneGeometry(center=(10.0, 10.0), orientation_deg=0.0, semi_major_m=2.0, semi_minor_m=1.0)
        assert is_point_inside_zone(zone, (10.0, 10.0)) is True
        assert is_point_inside_zone(zone, (0.0, 0.0)) is False
