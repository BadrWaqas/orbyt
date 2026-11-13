"""Tests for the isolation check: geometry, city lookup, footprints, hotspot test."""

from __future__ import annotations

import numpy as np
import pytest

from orbyt.core.geo import haversine_km, offsets_km
from orbyt.modules.pollution_hunter.candidates import Window, footprints, hotspot_check
from orbyt.sources.cities import Cities

CFG = {
    "window_km": 200,
    "background_km": [130, 200],
    "own_km": 12,
    "peak_cells": 5,
    "min_km": 20,
    "max_km": 100,
    "frac": 0.25,
    "noise_sigmas": 3,
}


def _window(extra: list[tuple[float, float, float]], own: float, noise: float = 0.0, seed=0):
    """A flat 0.1 degree field at 10 with a facility peak at (50, 10) plus extra peaks."""
    lats = np.arange(48.0, 52.0, 0.1)
    lons = np.arange(7.0, 13.0, 0.1)
    rng = np.random.default_rng(seed)
    field = 10.0 + noise * rng.standard_normal((lats.size, lons.size))
    li, lj = np.argmin(np.abs(lats - 50.0)), np.argmin(np.abs(lons - 10.0))
    field[li, lj] += own
    for dlat, dlon, amp in extra:
        i, j = np.argmin(np.abs(lats - (50.0 + dlat))), np.argmin(np.abs(lons - (10.0 + dlon)))
        field[i, j] += amp
    return Window(field=field, lats=lats, lons=lons)


def test_haversine_one_degree_of_latitude():
    assert haversine_km(50.0, 10.0, 51.0, 10.0) == pytest.approx(111.19, abs=0.1)


def test_offsets_east_north_signs():
    east, north = offsets_km(50.0, 10.0, np.array([50.5]), np.array([10.5]))
    assert east[0] > 0 and north[0] > 0
    assert north[0] == pytest.approx(55.6, abs=0.2)


def test_footprints_chain_merges():
    # A 0.1 degree step in latitude is about 11 km: 0, 11, 22 km chain at a 15 km radius.
    rows = [{"lat": 50.0 + 0.1 * k, "lon": 10.0} for k in range(3)] + [{"lat": 53.0, "lon": 10.0}]
    groups = sorted(sorted(g) for g in footprints(rows, 15.0))
    assert groups == [[0, 1, 2], [3]]


def test_cities_near_filters_by_distance_and_population():
    c = Cities(
        name=np.array(["Big", "Small", "Far"]),
        country=np.array(["X", "X", "X"]),
        lat=np.array([50.1, 50.1, 52.0]),
        lon=np.array([10.0, 10.0, 10.0]),
        population=np.array([900_000.0, 50_000.0, 2_000_000.0]),
    )
    hits = c.near(50.0, 10.0, 30.0, 200_000)
    assert [h["name"] for h in hits] == ["Big"]
    assert hits[0]["distance_km"] == pytest.approx(11.1, abs=0.3)


def test_hotspot_check_finds_neighbour_and_ignores_own_ridge():
    win = _window([(0.0, 0.5, 30.0)], own=40.0)  # neighbour about 36 km east
    out = hotspot_check(win, 50.0, 10.0, CFG)
    assert out["own"] == pytest.approx(40.0)
    assert out["other"] == pytest.approx(30.0)
    assert out["background"] == pytest.approx(10.0)


def test_hotspot_check_clean_scene_has_no_other():
    out = hotspot_check(_window([], own=40.0), 50.0, 10.0, CFG)
    assert out["other"] == 0.0


def test_hotspot_check_reports_map_noise():
    out = hotspot_check(_window([], own=40.0, noise=2.0), 50.0, 10.0, CFG)
    assert out["noise"] == pytest.approx(2.0, rel=0.3)


def test_hotspot_check_too_little_ring_returns_none():
    win = Window(
        field=np.full((10, 10), 5.0),
        lats=np.linspace(49.9, 50.1, 10),
        lons=np.linspace(9.9, 10.1, 10),
    )
    out = hotspot_check(win, 50.0, 10.0, CFG)
    assert out["own"] is None and out["noise"] is None
