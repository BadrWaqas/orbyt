"""Tests for the US validation plants on the public map (PLAN.md 1.7)."""

from __future__ import annotations

import json

from orbyt.modules.pollution_hunter import us_public

CFG = {
    "candidates": {"footprint_km": 20, "reliable_min_t": 6000},
    "verdict": {"u_sys": 0.35},
}


def _row(year, est, gates, v1=9000.0, v2=9100.0, unmon=300.0):
    return {
        "subject_id": "ph-us-1", "year": str(year), "level": "100m",
        "est_t_yr": "" if est is None else str(est), "lo": "7000", "hi": "12000",
        "gates_failed": gates, "days_used": "150", "v1_ref_t_yr": str(v1),
        "v2_ref_t_yr": str(v2), "v2_fp_ref_t_yr": str(v2 + unmon),
        "nei_unmonitored_t_yr": str(unmon), "nei_largest": "",
    }  # fmt: skip


PLANT = {"subject_id": "ph-us-1", "tier": 1, "name": "Test Plant", "county_state": "Rusk, TX",
         "lat": 32.26, "lon": -94.57, "n_plants": 1, "plant_ids_eia": [6146]}  # fmt: skip


def test_shown_year_is_the_latest_passing_year_else_the_latest():
    assert (
        us_public.shown_year({2023: _row(2023, 9000, ""), 2024: _row(2024, 9000, "poor_fit")})
        == 2023
    )
    assert us_public.shown_year({2023: _row(2023, 9000, "x"), 2024: _row(2024, 9000, "y")}) == 2024


def test_validation_entry_gives_ratios_only_for_passing_years():
    ok = us_public.validation_entry(_row(2024, 9900, ""))
    assert ok["passed"] and ok["ratio_at_pass"] == 1.1 and ok["footprint_t"] == 9400
    bad = us_public.validation_entry(_row(2024, 20000, "source_offset,poor_fit"))
    assert not bad["passed"] and bad["ratio_at_pass"] is None
    assert bad["gates_failed"] == ["source_offset", "poor_fit"]


def test_build_writes_monitors_as_claimed_and_labels_detection():
    table = {"ph-us-1": {2023: _row(2023, 9000, ""), 2024: _row(2024, 3000, "x", v2=4000.0)}}
    ((finding, detail, publish),) = us_public.build([PLANT], table, [1], CFG)
    assert finding["id"] == "ph-us-1-2023" and publish
    assert finding["claimed"] == {"value": 9100.0, "unit": "t NOx/yr", "basis": "measured",
                                  "source": us_public.CLAIMED_SOURCE}  # fmt: skip
    assert finding["detection"]["reliable"] and finding["validation_site"]
    assert finding["subject"]["register"] == "EPA CAMPD"
    assert [y["year"] for y in detail["validation"]["years"]] == [2023, 2024]
    assert [p["value"] for p in detail["reported_series"]] == [9100.0, 4000.0]


def test_build_skips_other_tiers():
    table = {"ph-us-1": {2024: _row(2024, 9000, "")}}
    assert us_public.build([{**PLANT, "tier": 2}], table, [1], CFG) == []


def test_merge_replaces_us_findings_and_keeps_european_ones(tmp_path):
    path = tmp_path / "findings.json"
    (tmp_path / "finding").mkdir()
    eu = {"id": "ph-eu-1-2024", "subject": {"id": "ph-eu-1", "register": "EEA"}}
    old_us = {"id": "ph-us-9-2024", "subject": {"id": "ph-us-9", "register": "EPA CAMPD"}}
    path.write_text(json.dumps({"findings": [eu, old_us], "count": 2}), encoding="utf-8")
    (tmp_path / "finding" / "ph-us-9-2024.json").write_text("{}", encoding="utf-8")
    table = {"ph-us-1": {2024: _row(2024, 9000, "")}}
    us_public.merge(path, us_public.build([PLANT], table, [1], CFG))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [f["id"] for f in data["findings"]] == ["ph-eu-1-2024", "ph-us-1-2024"]
    assert data["count"] == 2
    assert sorted(p.name for p in (tmp_path / "finding").iterdir()) == ["ph-us-1-2024.json"]
