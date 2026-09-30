"""Unit tests for app.py's per-worker camera-overlay color selection.

Regression coverage for a bug where the webcam-overlay bounding box color
was derived once from the aggregate risk_engine state and reused for every
worker, so one worker going CRITICAL/DANGER silently painted every other
worker's box red too. _worker_box_color must key off each worker's OWN
zone_level, read from a track_id-keyed dict, never a list index and never
the aggregate risk_engine state.
"""

from __future__ import annotations

from smart_zone.app import DISPLAY_COLOR_BY_ZONE_LEVEL, _worker_box_color


class TestWorkerBoxColorIndependence:
    def test_three_workers_get_three_distinct_colors_matching_their_own_zone(self):
        zone_level_by_track_id = {1: "OUTSIDE", 2: "CAUTION", 3: "DANGER"}

        color_1 = _worker_box_color(zone_level_by_track_id, 1)
        color_2 = _worker_box_color(zone_level_by_track_id, 2)
        color_3 = _worker_box_color(zone_level_by_track_id, 3)

        assert color_1 == DISPLAY_COLOR_BY_ZONE_LEVEL["OUTSIDE"]
        assert color_2 == DISPLAY_COLOR_BY_ZONE_LEVEL["CAUTION"]
        assert color_3 == DISPLAY_COLOR_BY_ZONE_LEVEL["DANGER"]
        assert len({color_1, color_2, color_3}) == 3  # all distinct, none overwritten

    def test_outside_worker_is_green_even_when_another_worker_is_in_danger(self):
        """The exact bug reported: one worker is in DANGER (which would
        drive the aggregate risk_state to CRITICAL), but another worker who
        is themselves OUTSIDE the zone must still render green, not red."""
        zone_level_by_track_id = {1: "OUTSIDE", 2: "DANGER"}
        color = _worker_box_color(zone_level_by_track_id, 1)
        assert color == DISPLAY_COLOR_BY_ZONE_LEVEL["OUTSIDE"]
        assert color != DISPLAY_COLOR_BY_ZONE_LEVEL["DANGER"]

    def test_changing_one_workers_state_does_not_change_another_workers_color(self):
        """Regression guard for the exact reported symptom: worker 3 turning
        DANGER must not affect worker 1's or worker 2's rendered color."""
        before = {1: "OUTSIDE", 2: "CAUTION", 3: "OUTSIDE"}
        after = {1: "OUTSIDE", 2: "CAUTION", 3: "DANGER"}

        color_1_before = _worker_box_color(before, 1)
        color_2_before = _worker_box_color(before, 2)

        color_1_after = _worker_box_color(after, 1)
        color_2_after = _worker_box_color(after, 2)
        color_3_after = _worker_box_color(after, 3)

        assert color_1_after == color_1_before
        assert color_2_after == color_2_before
        assert color_3_after == DISPLAY_COLOR_BY_ZONE_LEVEL["DANGER"]

    def test_lookup_is_by_track_id_not_list_position(self):
        """A dict keyed by track_id must still resolve correctly when
        workers are looked up out of insertion order or with gaps (as
        happens when a low track_id drops out mid-session) -- unlike an
        index-based lookup, which would silently misattribute here."""
        zone_level_by_track_id = {7: "DANGER", 12: "OUTSIDE", 3: "CAUTION"}

        assert _worker_box_color(zone_level_by_track_id, 12) == DISPLAY_COLOR_BY_ZONE_LEVEL["OUTSIDE"]
        assert _worker_box_color(zone_level_by_track_id, 7) == DISPLAY_COLOR_BY_ZONE_LEVEL["DANGER"]
        assert _worker_box_color(zone_level_by_track_id, 3) == DISPLAY_COLOR_BY_ZONE_LEVEL["CAUTION"]

    def test_unknown_track_id_defaults_to_outside_not_aggregate_state(self):
        """A track_id with no known zone_level defaults to OUTSIDE/green --
        the same never-derive-a-worker's-color-from-the-aggregate-state rule
        applies to the fallback path too."""
        zone_level_by_track_id: dict[int, str] = {}
        color = _worker_box_color(zone_level_by_track_id, 99)
        assert color == DISPLAY_COLOR_BY_ZONE_LEVEL["OUTSIDE"]
