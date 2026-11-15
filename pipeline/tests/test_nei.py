"""Tests for the NEI loader and the footprint sum of unmonitored NOx (M4.4)."""

from __future__ import annotations

import numpy as np
import pytest

from orbyt.sources import nei

HEADER = (
    '"site name","primary naics code","site latitude","site longitude","pollutant code",'
    '"total emissions","emissions uom"'
)


def _csv(tmp_path, rows):
    path = tmp_path / "fac.csv"
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_load_keeps_nox_converts_short_tons_and_sums_facility_rows(tmp_path):
    path = _csv(
        tmp_path,
        [
            '"Refinery",324110,30.0,-93.0,"NOX",1000,"TON"',
            '"Refinery",324110,30.0,-93.0,"NOX",100,"TON"',
            '"Refinery",324110,30.0,-93.0,"SO2",5000,"TON"',
            '"Plant",221112,30.1,-93.0,"NOX",2000,"TON"',
        ],
    )
    fac = nei.load_facilities(path)
    got = dict(zip(fac.name, fac.nox_t, strict=True))
    assert set(got) == {"Refinery", "Plant"}
    assert abs(got["Refinery"] - 1100 * nei.SHORT_TON_T) < 1e-9
    assert list(fac.power[[fac.name.index("Plant"), fac.name.index("Refinery")]]) == [True, False]


def test_load_refuses_unknown_units(tmp_path):
    path = _csv(tmp_path, ['"X",324110,30.0,-93.0,"NOX",1000,"LB"'])
    with pytest.raises(ValueError):
        nei.load_facilities(path)


def _fac():
    # Source at (30, -93). Refinery 5 km east, kiln 30 km north (outside), power plant on site.
    dlon = 5.0 / (111.195 * np.cos(np.radians(30.0)))
    return nei.Facilities(
        name=["Refinery", "Kiln", "Power"],
        naics=["324110", "327310", "221112"],
        lat=np.array([30.0, 30.0 + 30.0 / 111.195, 30.0]),
        lon=np.array([-93.0 + dlon, -93.0, -93.0]),
        nox_t=np.array([3000.0, 900.0, 5000.0]),
    )


def test_footprint_counts_non_power_inside_the_radius_only():
    got = nei.footprint(_fac(), 30.0, -93.0, 20.0, cems_t=5000.0)
    assert got["other_t"] == 3000.0
    assert got["power_gap_t"] == 0.0
    assert got["unmonitored_t"] == 3000.0
    assert [f["name"] for f in got["largest"]] == ["Refinery"]
    assert abs(got["largest"][0]["km"] - 5.0) < 0.05


def test_footprint_adds_power_plants_above_the_monitor_total():
    got = nei.footprint(_fac(), 30.0, -93.0, 20.0, cems_t=3000.0)
    assert got["power_gap_t"] == 2000.0
    assert got["unmonitored_t"] == 5000.0
    below = nei.footprint(_fac(), 30.0, -93.0, 20.0, cems_t=6000.0)
    assert below["power_gap_t"] == 0.0
