"""Unit tests for spatial.homography: point-correspondence fitting and projection."""

from __future__ import annotations

import pytest

from smart_zone.spatial.homography import (
    bbox_to_ground_position,
    compute_homography,
    pixel_to_ground,
)

TOLERANCE_M = 0.05


@pytest.fixture
def square_correspondences():
    """A simple axis-aligned square: 100px in image = 2m on the ground,
    with a known, easy-to-verify-by-hand mapping."""
    image_points = [
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 100.0),
        (0.0, 100.0),
    ]
    world_points = [
        (0.0, 0.0),
        (2.0, 0.0),
        (2.0, 2.0),
        (0.0, 2.0),
    ]
    return image_points, world_points


class TestComputeHomography:
    def test_computes_matrix_of_correct_shape(self, square_correspondences):
        image_points, world_points = square_correspondences
        matrix = compute_homography(image_points, world_points)
        assert matrix.shape == (3, 3)

    def test_raises_on_mismatched_lengths(self):
        with pytest.raises(ValueError):
            compute_homography([(0, 0), (1, 1)], [(0, 0)])

    def test_raises_on_too_few_points(self):
        with pytest.raises(ValueError):
            compute_homography([(0, 0), (1, 1), (2, 2)], [(0, 0), (1, 1), (2, 2)])


class TestPixelToGround:
    def test_known_corners_map_correctly(self, square_correspondences):
        image_points, world_points = square_correspondences
        matrix = compute_homography(image_points, world_points)

        for img_pt, world_pt in zip(image_points, world_points):
            projected = pixel_to_ground(matrix, img_pt)
            assert projected[0] == pytest.approx(world_pt[0], abs=TOLERANCE_M)
            assert projected[1] == pytest.approx(world_pt[1], abs=TOLERANCE_M)

    def test_known_midpoint_maps_to_expected_ground_point(self, square_correspondences):
        image_points, world_points = square_correspondences
        matrix = compute_homography(image_points, world_points)

        # Center of the image square (50, 50) -> should map to center of the
        # world square (1.0, 1.0) since this is a pure affine scale (no skew/perspective).
        projected = pixel_to_ground(matrix, (50.0, 50.0))
        assert projected[0] == pytest.approx(1.0, abs=TOLERANCE_M)
        assert projected[1] == pytest.approx(1.0, abs=TOLERANCE_M)


class TestBboxToGroundPosition:
    def test_uses_bottom_center_as_ground_contact_point(self, square_correspondences):
        image_points, world_points = square_correspondences
        matrix = compute_homography(image_points, world_points)

        # bbox spanning x:[25,75], y:[0,100] -> bottom-center = (50, 100)
        bbox = (25.0, 0.0, 75.0, 100.0)
        projected = bbox_to_ground_position(matrix, bbox)

        # bottom-center pixel (50, 100) should map near world (1.0, 2.0)
        assert projected[0] == pytest.approx(1.0, abs=TOLERANCE_M)
        assert projected[1] == pytest.approx(2.0, abs=TOLERANCE_M)

    def test_ignores_box_top_not_center(self, square_correspondences):
        image_points, world_points = square_correspondences
        matrix = compute_homography(image_points, world_points)

        # A very tall box should still project via its bottom edge, not its
        # vertical center -- top at y=0 must not affect the result.
        short_box = (40.0, 90.0, 60.0, 100.0)
        tall_box = (40.0, 0.0, 60.0, 100.0)

        short_result = bbox_to_ground_position(matrix, short_box)
        tall_result = bbox_to_ground_position(matrix, tall_box)

        assert short_result[0] == pytest.approx(tall_result[0], abs=1e-9)
        assert short_result[1] == pytest.approx(tall_result[1], abs=1e-9)
