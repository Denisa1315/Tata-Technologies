"""Unit tests for machine.kinematics: angle/angular-speed -> ground-plane projection."""

from __future__ import annotations

import math

import pytest

from smart_zone.machine.kinematics import (
    current_leading_edge_position,
    predict_leading_edge_positions,
)

PIVOT = (0.0, 0.0)
RADIUS_M = 5.0
TOLERANCE_M = 1e-6


class TestCurrentLeadingEdgePosition:
    def test_angle_zero_points_along_positive_x(self):
        x, y = current_leading_edge_position(0.0, PIVOT, RADIUS_M)
        assert x == pytest.approx(RADIUS_M, abs=TOLERANCE_M)
        assert y == pytest.approx(0.0, abs=TOLERANCE_M)

    def test_angle_90_points_along_positive_y(self):
        x, y = current_leading_edge_position(90.0, PIVOT, RADIUS_M)
        assert x == pytest.approx(0.0, abs=TOLERANCE_M)
        assert y == pytest.approx(RADIUS_M, abs=TOLERANCE_M)

    def test_respects_pivot_offset(self):
        pivot = (10.0, -3.0)
        x, y = current_leading_edge_position(0.0, pivot, RADIUS_M)
        assert x == pytest.approx(10.0 + RADIUS_M, abs=TOLERANCE_M)
        assert y == pytest.approx(-3.0, abs=TOLERANCE_M)


class TestPredictLeadingEdgePositions:
    def test_zero_angular_speed_stays_constant(self):
        points = predict_leading_edge_positions(
            current_angle_deg=0.0, angular_speed_deg_s=0.0,
            pivot=PIVOT, radius_m=RADIUS_M, horizon_s=1.0, n_steps=4,
        )
        for p in points:
            assert p.x == pytest.approx(RADIUS_M, abs=TOLERANCE_M)
            assert p.y == pytest.approx(0.0, abs=TOLERANCE_M)

    def test_constant_angular_speed_sweeps_expected_angle(self):
        points = predict_leading_edge_positions(
            current_angle_deg=0.0, angular_speed_deg_s=90.0,
            pivot=PIVOT, radius_m=RADIUS_M, horizon_s=1.0, n_steps=1,
        )
        # after 1s at 90 deg/s from 0 deg -> 90 deg -> (0, radius)
        last = points[-1]
        assert last.angle_deg == pytest.approx(90.0, abs=1e-9)
        assert last.x == pytest.approx(0.0, abs=TOLERANCE_M)
        assert last.y == pytest.approx(RADIUS_M, abs=TOLERANCE_M)

    def test_returns_n_steps_plus_one_points(self):
        points = predict_leading_edge_positions(
            current_angle_deg=0.0, angular_speed_deg_s=10.0,
            pivot=PIVOT, radius_m=RADIUS_M, horizon_s=1.0, n_steps=5,
        )
        assert len(points) == 6
        assert points[0].t_s == pytest.approx(0.0)
        assert points[-1].t_s == pytest.approx(1.0)

    def test_negative_angular_speed_sweeps_backward(self):
        points = predict_leading_edge_positions(
            current_angle_deg=90.0, angular_speed_deg_s=-90.0,
            pivot=PIVOT, radius_m=RADIUS_M, horizon_s=1.0, n_steps=1,
        )
        last = points[-1]
        assert last.angle_deg == pytest.approx(0.0, abs=1e-9)
        assert last.x == pytest.approx(RADIUS_M, abs=TOLERANCE_M)
        assert last.y == pytest.approx(0.0, abs=TOLERANCE_M)

    def test_raises_on_invalid_n_steps(self):
        with pytest.raises(ValueError):
            predict_leading_edge_positions(0.0, 0.0, PIVOT, RADIUS_M, n_steps=0)

    def test_raises_on_non_positive_radius(self):
        with pytest.raises(ValueError):
            predict_leading_edge_positions(0.0, 0.0, PIVOT, radius_m=0.0)
