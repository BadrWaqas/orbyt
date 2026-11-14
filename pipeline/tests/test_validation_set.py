"""Tests for the US validation plant selection: tiers, quality and the footprint totals."""

from __future__ import annotations

import json

import duckdb
import pytest

from orbyt.modules.pollution_hunter import validation_set as vs
from orbyt.modules.pollution_hunter.config import load_config

VCFG = load_config()["validation"]
FLAGS = ("flag_sources", "flag_city_near", "flag_city_far", "flag_hotspot")


def _r(good=True, **fails):
    r = {k: False for k in FLAGS} | {"good_monitors": good}
    r.update({f"flag_{k}": v for k, v in fails.items()})
    return r


def test_tier_one_passes_everything_and_tier_two_may_fail_only_the_relaxed_checks():
    assert vs.tier_of(_r(), VCFG) == 1
    assert vs.tier_of(_r(city_far=True), VCFG) == 2
    assert vs.tier_of(_r(hotspot=True, city_far=True), VCFG) == 2
    assert vs.tier_of(_r(city_near=True), VCFG) == 0
    assert vs.tier_of(_r(sources=True, hotspot=True), VCFG) == 0
    assert vs.tier_of(_r(good=False), VCFG) == 0  # bad monitors are out whatever the tier


def test_config_keeps_the_two_hard_checks_out_of_tier_two():
    assert set(VCFG["tier2_may_fail"]) == {"city_far", "hotspot"}
    assert VCFG["years"] == [2023, 2024] and VCFG["min_footprint_t"] == 2000


def test_footprint_quality_sums_tonnes_and_weights_the_measured_share():
    rows = [
        {
            "nox_t_by_year": {2023: 3000.0, 2024: 3000.0},
            "measured_share_by_year": {2023: 1.0, 2024: 1.0},
            "op_gap_by_year": {2023: 0.0, 2024: 0.002},
        },
        {
            "nox_t_by_year": {2023: 1000.0, 2024: 1000.0},
            "measured_share_by_year": {2023: 0.6, 2024: 0.2},
            "op_gap_by_year": {2023: 0.01, 2024: 0.0},
        },
    ]
    q = vs.footprint_quality([0, 1], rows, (2023, 2024))
    assert q["nox_t_2023"] == 4000.0
    assert q["measured_share_2023"] == pytest.approx((3000 + 600) / 4000)
    assert q["measured_share_2024"] == pytest.approx((3000 + 200) / 4000)
    assert q["op_gap_2023"] == 0.01 and q["op_gap_2024"] == 0.002  # the worst plant counts


def test_load_rows_needs_both_years_and_uses_the_later_year_as_the_size(tmp_path):
    path = tmp_path / "annual.parquet"
    con = duckdb.connect()
    con.execute(
        """
        create table a as
        select plant_id_eia, year, nox_t::double as nox_t, measured_share::double as measured_share,
               unit_hours_operating, operating_nox_missing, name, county, state,
               lat::double as lat, lon::double as lon
        from (values
          (1, 2023, 2500.0, 0.95, 1000, 5, 'Alpha', 'Lee', 'TX', 31.0, -97.0),
          (1, 2024, 2600.0, 0.96, 1000, 0, 'Alpha', 'Lee', 'TX', 31.0, -97.0),
          (2, 2024, 9000.0, 1.0, 1000, 0, 'Beta', 'Ray', 'MO', 38.0, -90.0)
        ) t(plant_id_eia, year, nox_t, measured_share, unit_hours_operating,
            operating_nox_missing, name, county, state, lat, lon)
        """
    )
    con.execute(f"copy a to '{path.as_posix()}' (format parquet)")
    rows = vs.load_rows(path, (2023, 2024))
    assert [r["register_id"] for r in rows] == ["1"]  # plant 2 has no 2023
    r = rows[0]
    assert r["release_t"] == 2600.0 and r["nox_t_by_year"] == {2024: 2600.0, 2023: 2500.0}
    assert r["op_gap_by_year"] == {2024: 0.0, 2023: pytest.approx(0.005)}
    assert r["city"] == "Lee, TX" and r["country"] == "United States"


def test_write_plants_keeps_the_tiers_sorted_and_drops_the_rest(tmp_path):
    def result(anchor, t24, **fails):
        return _r(**fails) | {
            "subject_anchor": anchor,
            "name": f"Plant {anchor}",
            "city": "Lee, TX",
            "lat": 31.0,
            "lon": -97.0,
            "plant_ids": anchor,
            "n_facilities": 1,
            "nox_t_2023": t24,
            "nox_t_2024": t24,
            "measured_share_2023": 0.97,
            "measured_share_2024": 0.99,
            "nearest_big_city": "",
            "own_detectable": True,
            "reported_t": t24,
        }

    results = [
        result("1", 3000.0, city_far=True),
        result("2", 2500.0),
        result("3", 9000.0),
        result("4", 8000.0, city_near=True),
    ]
    out = tmp_path / "plants.json"
    chosen = vs.write_plants(results, VCFG, out)
    # Tier 1 first, largest first inside a tier. Plant 4 fails city_near and is dropped.
    assert [(c["subject_id"], c["tier"]) for c in chosen] == [
        ("ph-us-3", 1),
        ("ph-us-2", 1),
        ("ph-us-1", 2),
    ]
    assert json.loads(out.read_text(encoding="utf-8")) == chosen
    assert chosen[2]["flags_failed"] == ["city_far"] and chosen[0]["measured_share"] == 0.97
