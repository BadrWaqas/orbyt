"""Tests for the coast and terrain flags (M5.3): the distance geometry and the thresholds."""

from __future__ import annotations

import numpy as np
import pytest

from orbyt.modules.pollution_hunter import site_flags

GRADE = {"coast_km": 15, "terrain_range_m": 300, "terrain_radius_km": 30, "a_min_days": 80}


def test_distance_to_a_line_north_of_the_point():
    lons = np.array([9.0, 11.0])
    lats = np.array([50.1, 50.1])
    assert site_flags.distance_to_line_km(50.0, 10.0, lats, lons) == pytest.approx(11.12, abs=0.05)


def test_distance_uses_the_segment_end_when_the_foot_is_outside_it():
    lons = np.array([10.5, 11.0])
    lats = np.array([50.0, 50.0])
    expected = 0.5 * np.cos(np.radians(50.0)) * site_flags.KM_PER_DEG
    got = site_flags.distance_to_line_km(50.0, 10.0, lats, lons)
    assert got == pytest.approx(expected, abs=0.1)


def test_distance_to_a_single_vertex_and_to_a_bent_line():
    assert site_flags.distance_to_line_km(50.0, 10.0, np.array([50.0]), np.array([10.0])) == 0.0
    lons = np.array([9.0, 10.0, 10.0])
    lats = np.array([50.2, 50.2, 49.0])
    # The bend at (50.2, 10.0) is 22 km away, but the second leg passes through the point.
    assert site_flags.distance_to_line_km(50.0, 10.0, lats, lons) == pytest.approx(0.0, abs=0.01)


def test_flags_follow_the_thresholds_of_plan_4_5():
    assert site_flags.flags_for(14.9, 100, GRADE) == ["coast"]
    assert site_flags.flags_for(15.1, 100, GRADE) == []
    assert site_flags.flags_for(100.0, 301, GRADE) == ["terrain"]
    assert site_flags.flags_for(100.0, 300, GRADE) == []
    assert site_flags.flags_for(1.0, 900, GRADE) == ["coast", "terrain"]


def test_a_missing_number_sets_no_flag():
    assert site_flags.flags_for(None, None, GRADE) == []
