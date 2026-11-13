"""Observation glue: grids, day selection, the reported value and the output document."""

import json

import numpy as np
import pytest

from orbyt.modules.pollution_hunter import observe
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.diagnostic import draw_diagnostic
from orbyt.modules.pollution_hunter.extract import Subject
from orbyt.sources.era5 import DayWind

CFG = load_config()["observe"]


def day(date, speed):
    return DayWind(
        date, "img", "", "solar-geometry", "", speed and 1.0, speed and 0.0, speed, 270.0
    )


def test_grids_match_the_core_math_tests():
    yr = observe.grid(CFG["crosswind_km"])
    t = observe.grid(CFG["travel_hours"])
    assert (yr[0], yr[-1], len(yr)) == (-80.0, 80.0, 81)
    assert t[0] == pytest.approx(-2.0) and t[-1] == pytest.approx(6.0) and len(t) == 81


def test_constants_are_the_planned_ones():
    assert (CFG["nox_to_no2"], CFG["amf_correction"]) == (1.38, 1.61)
    assert load_config()["wind"]["min_speed_ms"] == 2.0


def test_select_days_drops_calm_and_missing_wind_and_counts_them():
    days = [day("2024-05-01", 5.0), day("2024-05-02", 1.9), day("2024-05-03", 2.0)]
    days.append(DayWind("2024-05-04", "img", "", "solar-geometry", "", None, None, None, None))
    kept, dropped = observe.select_days(days, 2.0)
    assert [d.day for d in kept] == ["2024-05-01", "2024-05-03"]
    assert dropped == {"no_wind": 1, "calm": 1}


def test_background_constants_reach_the_document():
    assert CFG["flank_km"] == 60.0
    assert CFG["upwind_box_km"] == [-70.0, -20.0]


@pytest.mark.parametrize(
    ("from_deg", "name"),
    [(0.0, "N"), (44.9, "N"), (45.0, "E"), (134.9, "E"), (180.0, "S"), (270.0, "W"), (359.0, "N")],
)
def test_sector_of_covers_the_compass(from_deg, name):
    assert observe.sector_of(from_deg) == name


def test_sector_profiles_only_draw_quarters_with_enough_days():
    t = observe.grid(CFG["travel_hours"])
    yr = observe.grid(CFG["crosswind_km"])
    days = [day(f"2024-05-{i + 1:02d}", 5.0) for i in range(4)]  # all from 270, the west
    flux = np.ones((4, len(yr), len(t)))
    hw = np.full(len(t), 20.0)
    rows = {r["wind_from"]: r for r in observe.sector_profiles(flux, days, yr, hw, min_days=3)}
    assert rows["W"]["n_days"] == 4 and rows["W"]["flux_mol_s"] is not None
    assert rows["W"]["flux_mol_s"][0] == pytest.approx(21 * 2000.0)  # 21 cells of 2 km
    assert rows["N"]["n_days"] == 0 and rows["N"]["flux_mol_s"] is None
    none = observe.sector_profiles(flux, days, yr, hw, min_days=5)
    assert all(r["flux_mol_s"] is None for r in none)


def test_reported_tonnes_reads_the_subject_or_returns_none(tmp_path):
    path = tmp_path / "findings.json"
    assert observe.reported_tonnes("ph-eu-x", path) is None
    doc = {"findings": [{"subject": {"id": "ph-eu-x"}, "claimed": {"value": 1234.5}}]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert observe.reported_tonnes("ph-eu-x", path) == 1234.5
    assert observe.reported_tonnes("ph-eu-y", path) is None


def test_clean_turns_numpy_and_nan_into_json():
    out = observe._clean({"a": np.array([1.0, np.nan]), "b": np.float32(2.0), "c": (np.int64(3),)})
    assert out == {"a": [1.0, None], "b": 2.0, "c": [3]}
    json.dumps(out)


def test_no_fit_is_reported_as_a_failed_gate_and_still_draws(tmp_path):
    t = observe.grid(CFG["travel_hours"])
    yr = observe.grid(CFG["crosswind_km"])
    flux = np.full((3, len(yr), len(t)), np.nan)
    est, gates = observe.run_estimate(flux, t, yr, [4.0, 5.0, 6.0], CFG)
    assert est is None and gates == ["no_fit"]
    subject = Subject("ph-eu-test", "Test plant", 51.0, 19.0)
    profile, hw = observe.profile_of(flux, t, yr, [4.0, 5.0, 6.0])
    doc = observe.build_document(
        subject,
        [day("2024-05-01", 4.0)],
        1,
        {"no_wind": 0, "calm": 0},
        est,
        gates,
        t,
        profile,
        1000.0,
        CFG,
    )
    assert doc["observed"] is None and doc["ratio"] is None
    assert doc["gates_failed"] == ["no_fit"]
    json.dumps(doc)
    png = draw_diagnostic(tmp_path / "d.png", doc, flux, t, yr, hw)
    assert png.stat().st_size > 1000
