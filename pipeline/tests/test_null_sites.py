"""Tests for the null-site draw (M4.5): strata, source exclusion, determinism."""

from __future__ import annotations

import numpy as np

from orbyt.modules.pollution_hunter import null_sites
from orbyt.sources.cities import Cities

CFG = {
    "seed": 0,
    "per_cell": 2,
    "max_town_pop": 50_000,
    "source_radius_km": 60,
    "source_min_t": 500,
    "city_near_km": 30,
    "far_km": 100,
    "far_pop": 200_000,
    "shadow_pop": 500_000,
    "min_spacing_km": 150,
}
DE = "Germany"


def _cities(rows: list[tuple[str, float, float, int]]) -> Cities:
    return Cities(
        name=np.array([r[0] for r in rows]),
        country=np.array([DE] * len(rows)),
        lat=np.array([r[1] for r in rows]),
        lon=np.array([r[2] for r in rows]),
        population=np.array([r[3] for r in rows]),
    )


def test_region_of_uses_country_and_box():
    assert null_sites.region_of(DE, 50.0, 10.0) == "europe"
    assert null_sites.region_of(DE, 10.0, 10.0) is None  # outside the box
    assert null_sites.region_of(null_sites.US_NAME, 40.0, -100.0) == "us"
    assert null_sites.region_of("Brazil", 40.0, -100.0) is None


def test_stratum_of_by_distance_to_big_city():
    # a city of 1 million at 50N 10E; 0.1 deg of latitude is about 11 km
    cities = _cities(
        [
            ("Big", 50.0, 10.0, 1_000_000),
            ("Near", 50.1, 10.0, 5_000),  # 11 km: inside city_near
            ("Shadow", 50.5, 10.0, 5_000),  # 55 km: between city_near and far_km
            ("Far", 52.0, 10.0, 5_000),  # 222 km
        ]
    )
    assert null_sites.stratum_of(cities, 50.1, 10.0, CFG)[0] is None
    assert null_sites.stratum_of(cities, 50.5, 10.0, CFG)[0] == "shadow"
    stratum, nearest = null_sites.stratum_of(cities, 52.0, 10.0, CFG)
    assert stratum == "far"
    assert nearest.startswith("Big")


def test_mid_sized_city_nearby_is_not_a_shadow_site():
    # 300,000 people at 55 km: too big for a clean "far" site, too small for the shadow rule
    cities = _cities([("Mid", 50.0, 10.0, 300_000), ("Town", 50.5, 10.0, 5_000)])
    assert null_sites.stratum_of(cities, 50.5, 10.0, CFG)[0] is None


def test_choose_skips_towns_near_a_source_and_big_towns():
    cities = _cities(
        [
            ("Big", 50.0, 10.0, 1_000_000),
            ("NearPlant", 52.0, 10.0, 5_000),
            ("Large", 52.0, 14.0, 80_000),  # above max_town_pop
            ("Clean", 52.0, 18.0, 5_000),
        ]
    )
    # one 2,000 t source 10 km from NearPlant, one 100 t source that is too small to count
    src = (np.array([52.1, 52.0]), np.array([10.0, 18.0]), np.array([2_000.0, 100.0]))
    sites = null_sites.choose(cities, src, CFG, log=lambda *_: None)
    names = {s["name"] for s in sites}
    assert names == {"Clean, Germany"}
    assert sites[0]["stratum"] == "far"
    assert sites[0]["subject_id"] == "ph-null-01"


def test_choose_is_repeatable_and_keeps_sites_apart():
    rng = np.random.default_rng(1)
    rows = [("Big", 50.0, 10.0, 1_000_000)] + [
        (f"T{i}", 45.0 + rng.random() * 9, -5.0 + rng.random() * 30, 5_000) for i in range(60)
    ]
    cities = _cities(rows)
    src = (np.array([0.0]), np.array([0.0]), np.array([1_000.0]))
    a = null_sites.choose(cities, src, CFG, log=lambda *_: None)
    b = null_sites.choose(cities, src, CFG, log=lambda *_: None)
    assert a == b
    assert len(a) > 1
    from orbyt.core.geo import haversine_km

    for i, s in enumerate(a):
        for t in a[i + 1 :]:
            assert haversine_km(s["lat"], s["lon"], t["lat"], t["lon"]) >= CFG["min_spacing_km"]
