"""Unit tests for safety.zone: explainable danger-ellipse sizing formula,
caution ring, and point-classification (OUTSIDE/CAUTION/DANGER)."""

from __future__ import annotations

import math

import pytest

from smart_zone.safety.zone import (
    DEFAULT_BASELINE_RADIUS_M,
    DEFAULT_CAUTION_BAND_M,
    DEFAULT_HUMAN_SPEED_MPS,
    DEFAULT_MARGIN_M,
    DEFAULT_REACTION_TIME_S,
    DEFAULT_STOPPING_COEFF,
    ZoneGeometry,
    ZoneLevel,
    compute_caution_zone_geometry,
    compute_zone_geometry,
    is_point_inside_zone,
    protective_distance_m,
    swing_heading_deg,
    tangential_speed_m_s,
    zone_level_for_point,
)

PIVOT = (0.0, 0.0)
RADIUS_M = 3.0


class TestSwingHeading:
    def test_positive_angular_speed_leads_90_ccw(self):
        assert swing_heading_deg(0.0, 20.0) == pytest.approx(90.0)

    def test_negative_angular_speed_leads_90_cw(self):
        assert swing_heading_deg(0.0, -20.0) == pytest.approx(-90.0)

    def test_stationary_falls_back_to_radial_direction(self):
        assert swing_heading_deg(30.0, 0.0) == pytest.approx(30.0)


class TestTangentialSpeed:
    def test_zero_angular_speed_is_zero(self):
        assert tangential_speed_m_s(0.0, RADIUS_M) == pytest.approx(0.0)

    def test_known_angular_speed_gives_expected_linear_speed(self):
        speed = tangential_speed_m_s(180.0, RADIUS_M)
        assert speed == pytest.approx(RADIUS_M * math.pi, rel=1e-6)

    def test_sign_independent(self):
        assert tangential_speed_m_s(-30.0, RADIUS_M) == tangential_speed_m_s(30.0, RADIUS_M)


class TestProtectiveDistanceFormula:
    def test_matches_explicit_formula(self):
        v = 1.2
        expected = DEFAULT_STOPPING_COEFF * v + DEFAULT_HUMAN_SPEED_MPS * DEFAULT_REACTION_TIME_S + DEFAULT_MARGIN_M
        assert protective_distance_m(v) == pytest.approx(expected)

    def test_zero_speed_gives_reaction_plus_margin_only(self):
        expected = DEFAULT_HUMAN_SPEED_MPS * DEFAULT_REACTION_TIME_S + DEFAULT_MARGIN_M
        assert protective_distance_m(0.0) == pytest.approx(expected)

    def test_grows_with_speed(self):
        low = protective_distance_m(0.5)
        high = protective_distance_m(2.0)
        assert high > low

    def test_never_zero_or_negative_for_nonnegative_speed(self):
        for v in [0.0, 0.1, 5.0, 50.0]:
            assert protective_distance_m(v) > 0.0


class TestComputeZoneGeometryBaseline:
    def test_zero_speed_is_a_circle_of_baseline_radius(self):
        zone = compute_zone_geometry(PIVOT, current_angle_deg=10.0, angular_speed_deg_s=0.0, radius_m=RADIUS_M)
        assert zone.semi_major_m == pytest.approx(DEFAULT_BASELINE_RADIUS_M)
        assert zone.semi_minor_m == pytest.approx(DEFAULT_BASELINE_RADIUS_M)
        assert zone.semi_major_m == zone.semi_minor_m  # circle, not an ellipse

    def test_zero_speed_is_never_zero_sized_or_nan(self):
        zone = compute_zone_geometry(PIVOT, 0.0, 0.0, RADIUS_M)
        assert zone.semi_major_m > 0.0
        assert zone.semi_minor_m > 0.0
        assert not math.isnan(zone.semi_major_m)
        assert not math.isnan(zone.semi_minor_m)

    def test_zero_speed_center_is_exactly_the_pivot(self):
        pivot = (3.5, -2.0)
        zone = compute_zone_geometry(pivot, 0.0, 0.0, RADIUS_M)
        assert zone.center == pivot


class TestComputeZoneGeometryMoving:
    def test_danger_size_grows_with_speed(self):
        slow = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=5.0, radius_m=RADIUS_M)
        fast = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=40.0, radius_m=RADIUS_M)
        assert fast.semi_major_m > slow.semi_major_m
        assert fast.semi_minor_m > slow.semi_minor_m

    def test_semi_major_matches_protective_distance(self):
        angular_speed = 20.0
        zone = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=angular_speed, radius_m=RADIUS_M)
        v = tangential_speed_m_s(angular_speed, RADIUS_M)
        assert zone.semi_major_m == pytest.approx(protective_distance_m(v))

    def test_center_offsets_toward_swing_heading_when_moving(self):
        zone = compute_zone_geometry(PIVOT, current_angle_deg=0.0, angular_speed_deg_s=20.0, radius_m=RADIUS_M)
        # heading is +90 deg (along +y) for positive angular speed at angle 0
        assert zone.center[0] == pytest.approx(0.0, abs=1e-9)
        assert zone.center[1] > 0.0

    def test_never_zero_or_nan_at_high_speed(self):
        zone = compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=200.0, radius_m=RADIUS_M)
        assert zone.semi_major_m > 0.0
        assert not math.isnan(zone.semi_major_m)
        assert not math.isnan(zone.center[0])
        assert not math.isnan(zone.center[1])


class TestCautionZone:
    @pytest.fixture
    def danger_zone(self):
        return compute_zone_geometry(PIVOT, 0.0, angular_speed_deg_s=20.0, radius_m=RADIUS_M)

    def test_caution_zone_is_danger_zone_plus_fixed_band(self, danger_zone):
        caution = compute_caution_zone_geometry(danger_zone, caution_band_m=0.7)
        assert caution.semi_major_m == pytest.approx(danger_zone.semi_major_m + 0.7)
        assert caution.semi_minor_m == pytest.approx(danger_zone.semi_minor_m + 0.7)

    def test_caution_zone_shares_center_and_orientation(self, danger_zone):
        caution = compute_caution_zone_geometry(danger_zone, caution_band_m=0.7)
        assert caution.center == danger_zone.center
        assert caution.orientation_deg == pytest.approx(danger_zone.orientation_deg)

    def test_raises_on_negative_band(self, danger_zone):
        with pytest.raises(ValueError):
            compute_caution_zone_geometry(danger_zone, caution_band_m=-0.1)

    def test_default_band_matches_constant(self, danger_zone):
        caution = compute_caution_zone_geometry(danger_zone)
        assert caution.semi_major_m == pytest.approx(danger_zone.semi_major_m + DEFAULT_CAUTION_BAND_M)


class TestIsPointInsideZone:
    @pytest.fixture
    def axis_aligned_zone(self):
        return ZoneGeometry(center=(0.0, 0.0), orientation_deg=0.0, semi_major_m=4.0, semi_minor_m=2.0)

    def test_center_is_inside(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (0.0, 0.0)) is True

    def test_known_inside_point(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (2.0, 1.0)) is True

    def test_known_outside_point(self, axis_aligned_zone):
        assert is_point_inside_zone(axis_aligned_zone, (10.0, 10.0)) is False

    def test_rotated_zone_containment(self):
        zone = ZoneGeometry(center=(0.0, 0.0), orientation_deg=90.0, semi_major_m=4.0, semi_minor_m=2.0)
        assert is_point_inside_zone(zone, (0.0, 3.0)) is True
        assert is_point_inside_zone(zone, (3.0, 0.0)) is False

    def test_offset_center(self):
        zone = ZoneGeometry(center=(10.0, 10.0), orientation_deg=0.0, semi_major_m=2.0, semi_minor_m=1.0)
        assert is_point_inside_zone(zone, (10.0, 10.0)) is True
        assert is_point_inside_zone(zone, (0.0, 0.0)) is False


class TestZoneLevelForPoint:
    @pytest.fixture
    def zones(self):
        danger = ZoneGeometry(center=(0.0, 0.0), orientation_deg=0.0, semi_major_m=1.0, semi_minor_m=0.6)
        caution = compute_caution_zone_geometry(danger, caution_band_m=0.7)
        return danger, caution

    def test_point_in_danger(self, zones):
        danger, caution = zones
        assert zone_level_for_point(danger, caution, (0.0, 0.0)) == ZoneLevel.DANGER

    def test_point_in_caution_ring(self, zones):
        danger, caution = zones
        # x=1.3 is outside danger's semi_major=1.0 but inside caution's semi_major=1.7
        assert zone_level_for_point(danger, caution, (1.3, 0.0)) == ZoneLevel.CAUTION

    def test_point_outside_both(self, zones):
        danger, caution = zones
        assert zone_level_for_point(danger, caution, (10.0, 10.0)) == ZoneLevel.OUTSIDE

    def test_rotated_and_offset_danger_point(self):
        danger = ZoneGeometry(center=(5.0, 5.0), orientation_deg=90.0, semi_major_m=1.0, semi_minor_m=0.6)
        caution = compute_caution_zone_geometry(danger, caution_band_m=0.7)
        # major axis now along +y from center (5,5) -> (5, 6) is inside danger
        assert zone_level_for_point(danger, caution, (5.0, 6.0)) == ZoneLevel.DANGER

    def test_rotated_and_offset_caution_point(self):
        danger = ZoneGeometry(center=(5.0, 5.0), orientation_deg=90.0, semi_major_m=1.0, semi_minor_m=0.6)
        caution = compute_caution_zone_geometry(danger, caution_band_m=0.7)
        # (5, 6.5) is beyond danger's major axis (1.0) but within caution's (1.7)
        assert zone_level_for_point(danger, caution, (5.0, 6.5)) == ZoneLevel.CAUTION

    def test_rotated_and_offset_outside_point(self):
        danger = ZoneGeometry(center=(5.0, 5.0), orientation_deg=90.0, semi_major_m=1.0, semi_minor_m=0.6)
        caution = compute_caution_zone_geometry(danger, caution_band_m=0.7)
        assert zone_level_for_point(danger, caution, (5.0, -10.0)) == ZoneLevel.OUTSIDE
