"""Tests for the 500 m wind (pressure levels) and the wind-level file names."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from orbyt.modules.pollution_hunter import batch, observe
from orbyt.sources import era5, era5_levels


def test_target_pressure_is_55_hpa_below_the_surface_pressure():
    assert era5_levels.target_pressure_hpa(101_300.0, 55.0) == 1013.0 - 55.0


def test_interpolation_is_linear_in_pressure():
    levels = np.array([1000.0, 975.0, 950.0])
    u = np.array([2.0, 4.0, 6.0])
    assert era5_levels.interp_to_pressure(levels, u, 962.5) == 5.0
    # unsorted input gives the same answer
    assert era5_levels.interp_to_pressure(levels[::-1], u[::-1], 962.5) == 5.0


def test_interpolation_outside_the_levels_takes_the_nearest_one():
    levels = np.array([1000.0, 975.0])
    u = np.array([2.0, 4.0])
    assert era5_levels.interp_to_pressure(levels, u, 1020.0) == 2.0
    assert era5_levels.interp_to_pressure(levels, u, 900.0) == 4.0


def test_interpolation_with_a_gap_is_none():
    levels = np.array([1000.0, 975.0])
    assert era5_levels.interp_to_pressure(levels, np.array([1.0, np.nan]), 990.0) is None
    assert era5_levels.interp_to_pressure(levels, np.array([1.0, 2.0]), float("nan")) is None


def test_cell_is_the_nearest_quarter_degree():
    assert era5_levels._cell(40.13, -88.37) == (40.25, -88.25)
    assert era5_levels._cell(40.12, -88.38) == (40.0, -88.5)


def test_level_names_leave_the_100m_files_unchanged(tmp_path: Path):
    assert era5.wind_path(tmp_path, "s").name == "wind.json"
    assert era5.wind_path(tmp_path, "s", "500m").name == "wind-500m.json"
    assert observe.estimate_name(2024) == "estimate-2024.json"
    assert observe.estimate_name(2024, level="500m") == "estimate-2024-500m.json"
    assert observe.estimate_name(None, "diagnostic", ".png", "500m") == "diagnostic-500m.png"


def test_wind_covers_checks_the_years(tmp_path: Path):
    path = tmp_path / "wind.json"
    assert not batch._wind_covers(path, [2024])
    path.write_text(json.dumps({"days": [{"day": "2024-05-01"}]}), encoding="utf-8")
    assert batch._wind_covers(path, [2024])
    assert not batch._wind_covers(path, [2023, 2024])
