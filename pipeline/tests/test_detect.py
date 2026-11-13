"""Tests for the single-day plume test and the flipbook."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.detect import (
    NO_DATA_RGB,
    DayTest,
    aligned_enhancement,
    clear_frame_indices,
    colourise,
    compass_name,
    draw_flipbook,
)
from orbyt.modules.pollution_hunter.detect import (
    test_day as plume_test,
)
from orbyt.modules.pollution_hunter.observe import grid

CFG = load_config()
OBS, DET = CFG["observe"], CFG["detect"]
LAT0, LON0 = 35.0, 26.0
X_KM, YR_KM = grid(DET["x_km"]), grid(OBS["crosswind_km"])
WIND_MS = 5.0  # blowing towards the east


def _scene(amplitude: float, seed: int, noise: float = 4e-6):
    """A column field in mol/m2 with a plume running east from the source, plus noise.

    The noise is smoothed to about one real pixel (19 km2), the size the test assumes.
    """
    rng = np.random.default_rng(seed)
    lats = np.arange(LAT0 - 2.0, LAT0 + 2.0, 0.03)
    lons = np.arange(LON0 - 2.5, LON0 + 2.5, 0.03)
    east = np.radians(lons[None, :] - LON0) * 6371.0 * np.cos(np.radians(LAT0))
    north = np.radians(lats[:, None] - LAT0) * 6371.0
    plume = amplitude * np.exp(-(north**2) / (2 * 6.0**2)) * np.exp(-np.clip(east, 0, None) / 40.0)
    plume = np.where(east > 0, plume, 0.0)
    smooth = gaussian_filter(rng.standard_normal((lats.size, lons.size)), 0.5)
    smooth *= noise / smooth.std()
    return 30e-6 + plume + smooth, lats, lons


def _test(field, lats, lons):
    enh = aligned_enhancement(field, lats, lons, LAT0, LON0, WIND_MS, 0.0, X_KM, YR_KM, OBS)
    assert enh is not None
    return enh, plume_test(enh, X_KM, YR_KM, WIND_MS, OBS["flank_km"], DET)


def test_strong_plume_is_detected():
    field, lats, lons = _scene(60e-6, seed=0)
    _, r = _test(field, lats, lons)
    assert r["testable"] and r["detected"]
    assert r["z"] >= DET["z_min"] and r["down"] > r["up"]


def test_noise_only_days_are_rarely_detected():
    hits = 0
    for seed in range(20):
        field, lats, lons = _scene(0.0, seed=seed)
        hits += _test(field, lats, lons)[1]["detected"]
    assert hits <= 2


def test_covered_downwind_box_is_not_tested():
    field, lats, lons = _scene(60e-6, seed=1)
    east = np.radians(lons[None, :] - LON0) * 6371.0 * np.cos(np.radians(LAT0))
    field = np.where((east > 0) & (east < 70), np.nan, field)
    _, r = _test(field, lats, lons)
    assert not r["testable"] and not r["detected"] and r["z"] is None
    assert r["valid_down"] < DET["min_valid_frac"]


def test_background_gradient_is_not_a_plume():
    field, lats, lons = _scene(0.0, seed=2)
    field = field + 10e-6 * (lons[None, :] - LON0)  # 10 micromol/m2 per degree of longitude
    _, r = _test(field, lats, lons)
    assert not r["detected"]


def test_colourise_ends_and_no_data():
    img = colourise(np.array([[0.0, 100.0, 500.0, np.nan]]), 100.0)
    assert tuple(img[0, 0]) == (0x4F, 0x1C, 0x00)
    assert tuple(img[0, 1]) == (0xFD, 0xF6, 0xD8)
    assert tuple(img[0, 2]) == (0xFD, 0xF6, 0xD8)  # clipped at full scale
    assert tuple(img[0, 3]) == NO_DATA_RGB


def test_compass_name():
    assert [compass_name(d) for d in (0, 44, 90, 225, 350)] == ["N", "NE", "E", "SW", "N"]


def test_clear_frames_need_valid_shown_part():
    clear = np.zeros((len(YR_KM), len(X_KM)))
    cloudy = clear.copy()
    cloudy[:, X_KM >= -20.0] = np.nan
    assert clear_frame_indices([clear, None, cloudy], X_KM, -20.0, 0.8) == [0]


def test_flipbook_sheet_geometry_and_manifest(tmp_path):
    fcfg = dict(DET["flipbook"], columns=2)
    imgs = [np.zeros((len(YR_KM), len(X_KM))) for _ in range(3)]
    tests = [
        DayTest(f"2024-05-0{i + 1}", 5.0, 270.0, True, i == 0, 4.0 - i, 5.0, 0.0, 0.5, 1.0, 1.0)
        for i in range(3)
    ]
    path = tmp_path / "flipbook.png"
    man = draw_flipbook(path, imgs, tests, X_KM, YR_KM, fcfg)
    n_cols = int((X_KM >= fcfg["show_from_km"]).sum())
    assert man["frame_w"] == n_cols * fcfg["scale_px"]
    assert man["frame_h"] == len(YR_KM) * fcfg["scale_px"] + fcfg["label_px"]
    assert (man["columns"], man["rows"]) == (2, 2)
    with Image.open(path) as sheet:
        assert sheet.size == (2 * man["frame_w"], 2 * man["frame_h"])
    assert [(f["col"], f["row"]) for f in man["frames"]] == [(0, 0), (1, 0), (0, 1)]
    assert [f["detected"] for f in man["frames"]] == [True, False, False]


@pytest.mark.parametrize("hours,cap", [(2.0, 60.0)])
def test_config_matches_plan(hours, cap):
    """PLAN.md 4.4: box of 2 h of travel, at most 60 km, 60% valid, z of at least 3."""
    assert DET["box_hours"] == hours and DET["box_max_km"] == cap
    assert DET["min_valid_frac"] == 0.6 and DET["z_min"] == 3.0
