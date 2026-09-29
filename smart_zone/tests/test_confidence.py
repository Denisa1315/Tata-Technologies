"""Unit tests for safety.confidence: distance bookkeeping, feet-visibility,
height-disagreement, range-based margin growth, and confidence-driven zone
level escalation."""

from __future__ import annotations

import pytest

from smart_zone.safety.confidence import (
    PositionConfidence,
    apply_confidence_to_zone_level,
    assess_confidence,
    distance_m,
    expected_box_height_px,
    height_disagreement_ratio,
    is_feet_visible,
    range_based_margin_m,
)
from smart_zone.safety.zone import ZoneLevel

FRAME_HEIGHT_PX = 1080.0
CAMERA_POS = (0.0, -1.0)
PIVOT = (0.0, 0.0)


class TestDistanceM:
    def test_known_distance(self):
        assert distance_m((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)

    def test_zero_distance(self):
        assert distance_m((1.0, 1.0), (1.0, 1.0)) == pytest.approx(0.0)


class TestFeetVisible:
    def test_box_touching_bottom_edge_is_not_visible(self):
        bbox = (100.0, 500.0, 200.0, FRAME_HEIGHT_PX)  # y2 exactly at frame edge
        assert is_feet_visible(bbox, FRAME_HEIGHT_PX, edge_margin_px=8) is False

    def test_box_within_margin_of_bottom_edge_is_not_visible(self):
        bbox = (100.0, 500.0, 200.0, FRAME_HEIGHT_PX - 5)  # 5px from edge, margin=8
        assert is_feet_visible(bbox, FRAME_HEIGHT_PX, edge_margin_px=8) is False

    def test_box_well_clear_of_bottom_edge_is_visible(self):
        bbox = (100.0, 500.0, 200.0, FRAME_HEIGHT_PX - 100)
        assert is_feet_visible(bbox, FRAME_HEIGHT_PX, edge_margin_px=8) is True

    def test_box_exactly_at_margin_boundary(self):
        # y2 exactly edge_margin_px from the frame edge -- boundary is
        # exclusive (must be strictly > margin to count as visible)
        bbox = (100.0, 500.0, 200.0, FRAME_HEIGHT_PX - 8)
        assert is_feet_visible(bbox, FRAME_HEIGHT_PX, edge_margin_px=8) is False


class TestExpectedBoxHeight:
    def test_matches_reference_at_1m(self):
        assert expected_box_height_px(1.0, reference_height_px_at_1m=800.0) == pytest.approx(800.0)

    def test_halves_at_double_distance(self):
        assert expected_box_height_px(2.0, reference_height_px_at_1m=800.0) == pytest.approx(400.0)

    def test_doubles_at_half_distance(self):
        assert expected_box_height_px(0.5, reference_height_px_at_1m=800.0) == pytest.approx(1600.0)

    def test_never_divides_by_zero(self):
        result = expected_box_height_px(0.0, reference_height_px_at_1m=800.0)
        assert result > 0
        import math
        assert not math.isinf(result)
        assert not math.isnan(result)


class TestHeightDisagreementRatio:
    def test_zero_when_matching_expected(self):
        # at 1m, expected height = 800px; box exactly 800px tall
        bbox = (0.0, 0.0, 100.0, 800.0)
        assert height_disagreement_ratio(bbox, 1.0, reference_height_px_at_1m=800.0) == pytest.approx(0.0)

    def test_positive_when_box_too_short(self):
        bbox = (0.0, 0.0, 100.0, 400.0)  # half the expected 800px
        ratio = height_disagreement_ratio(bbox, 1.0, reference_height_px_at_1m=800.0)
        assert ratio == pytest.approx(0.5)

    def test_positive_when_box_too_tall(self):
        bbox = (0.0, 0.0, 100.0, 1200.0)  # 1.5x the expected 800px
        ratio = height_disagreement_ratio(bbox, 1.0, reference_height_px_at_1m=800.0)
        assert ratio == pytest.approx(0.5)


class TestRangeBasedMargin:
    def test_zero_at_zero_distance(self):
        assert range_based_margin_m(0.0, slope_m_per_m=0.05, max_margin_m=0.5) == pytest.approx(0.0)

    def test_margin_grows_with_camera_distance(self):
        near = range_based_margin_m(1.0, slope_m_per_m=0.05, max_margin_m=0.5)
        far = range_based_margin_m(5.0, slope_m_per_m=0.05, max_margin_m=0.5)
        assert far > near

    def test_margin_is_linear_in_distance_before_cap(self):
        m1 = range_based_margin_m(2.0, slope_m_per_m=0.05, max_margin_m=10.0)
        m2 = range_based_margin_m(4.0, slope_m_per_m=0.05, max_margin_m=10.0)
        assert m2 == pytest.approx(2 * m1)

    def test_margin_capped_at_max(self):
        margin = range_based_margin_m(1000.0, slope_m_per_m=0.05, max_margin_m=0.5)
        assert margin == pytest.approx(0.5)

    def test_negative_distance_clamped_to_zero_margin(self):
        assert range_based_margin_m(-5.0, slope_m_per_m=0.05, max_margin_m=0.5) == pytest.approx(0.0)


class TestAssessConfidence:
    def test_high_confidence_when_feet_visible_and_height_matches(self):
        ground_pos = (0.0, 1.0)  # 2m from camera at (0,-1)
        # expected height at 2m = 800/2 = 400px
        bbox = (100.0, 100.0, 200.0, 500.0)  # height=400, well clear of bottom edge
        result = assess_confidence(
            bbox, ground_pos, CAMERA_POS, PIVOT, FRAME_HEIGHT_PX,
            edge_margin_px=8, height_disagreement_ratio_threshold=0.35,
            reference_height_px_at_1m=800.0,
        )
        assert result.confidence == PositionConfidence.HIGH
        assert result.feet_visible is True

    def test_low_confidence_when_feet_not_visible(self):
        ground_pos = (0.0, 1.0)
        bbox = (100.0, 100.0, 200.0, FRAME_HEIGHT_PX)  # touching bottom edge
        result = assess_confidence(
            bbox, ground_pos, CAMERA_POS, PIVOT, FRAME_HEIGHT_PX,
            edge_margin_px=8, height_disagreement_ratio_threshold=0.35,
            reference_height_px_at_1m=800.0,
        )
        assert result.confidence == PositionConfidence.LOW
        assert result.feet_visible is False

    def test_low_confidence_when_height_disagrees(self):
        ground_pos = (0.0, 1.0)  # 2m -> expected height 400px
        bbox = (100.0, 100.0, 200.0, 900.0)  # height=800, way off from 400 expected
        result = assess_confidence(
            bbox, ground_pos, CAMERA_POS, PIVOT, FRAME_HEIGHT_PX,
            edge_margin_px=8, height_disagreement_ratio_threshold=0.35,
            reference_height_px_at_1m=800.0,
        )
        assert result.confidence == PositionConfidence.LOW

    def test_distances_computed_correctly(self):
        ground_pos = (3.0, 3.0)
        bbox = (100.0, 100.0, 200.0, 300.0)
        result = assess_confidence(
            bbox, ground_pos, camera_ground_position=(0.0, 0.0),
            machine_pivot=(0.0, 4.0), frame_height_px=FRAME_HEIGHT_PX,
        )
        assert result.distance_to_camera_m == pytest.approx(distance_m((3.0, 3.0), (0.0, 0.0)))
        assert result.distance_to_machine_m == pytest.approx(distance_m((3.0, 3.0), (0.0, 4.0)))


class TestApplyConfidenceToZoneLevel:
    def test_high_confidence_leaves_zone_level_unchanged(self):
        for level in [ZoneLevel.OUTSIDE, ZoneLevel.CAUTION, ZoneLevel.DANGER]:
            result = apply_confidence_to_zone_level(level, PositionConfidence.HIGH, level)
            assert result == level

    def test_low_confidence_caution_becomes_danger(self):
        result = apply_confidence_to_zone_level(ZoneLevel.CAUTION, PositionConfidence.LOW, ZoneLevel.CAUTION)
        assert result == ZoneLevel.DANGER

    def test_low_confidence_danger_stays_danger(self):
        result = apply_confidence_to_zone_level(ZoneLevel.DANGER, PositionConfidence.LOW, ZoneLevel.DANGER)
        assert result == ZoneLevel.DANGER

    def test_low_confidence_outside_becomes_caution_when_within_margin(self):
        # zone_level_with_margin says CAUTION (i.e. within caution_band + range margin)
        result = apply_confidence_to_zone_level(ZoneLevel.OUTSIDE, PositionConfidence.LOW, ZoneLevel.CAUTION)
        assert result == ZoneLevel.CAUTION

    def test_low_confidence_outside_stays_outside_when_beyond_margin(self):
        # zone_level_with_margin also says OUTSIDE -- genuinely far away
        result = apply_confidence_to_zone_level(ZoneLevel.OUTSIDE, PositionConfidence.LOW, ZoneLevel.OUTSIDE)
        assert result == ZoneLevel.OUTSIDE
