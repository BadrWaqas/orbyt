"""Tests for the panel evidence: colours, the north-up frame, image files and the contract."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from orbyt.modules.pollution_hunter import evidence
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.detect import day_plane
from orbyt.modules.pollution_hunter.observe import grid

CFG = load_config()
OBS, DET, EVI = CFG["observe"], CFG["detect"], CFG["evidence"]
LAT0, LON0 = 35.0, 26.0
X_KM, YR_KM = grid(DET["x_km"]), grid(OBS["crosswind_km"])


def test_colourise_glow_ends_and_no_data():
    img = evidence.colourise_glow(np.array([[-5.0, 0.0, 100.0, 400.0, np.nan]]), 100.0)
    assert tuple(img[0, 0]) == evidence.BASE_RGB  # below background shows the base
    assert tuple(img[0, 1]) == evidence.BASE_RGB  # the ramp starts fully clear
    assert tuple(img[0, 2]) == (0xFD, 0xF6, 0xD8)  # top of the ramp, opaque
    assert tuple(img[0, 3]) == (0xFD, 0xF6, 0xD8)  # clipped at full scale
    assert tuple(img[0, 4]) == evidence.NO_DATA_RGB


def test_colourise_glow_gets_brighter_all_the_way_up():
    img = evidence.colourise_glow(np.linspace(0.0, 100.0, 21)[None, :], 100.0).astype(int)
    assert np.all(np.diff(img[0].sum(axis=1)) > 0)


def test_nice_full_scale():
    steps = EVI["stack"]["full_scale_steps_umol_m2"]
    assert evidence.nice_full_scale(7.6, steps) == 10.0
    assert evidence.nice_full_scale(20.0, steps) == 20.0
    assert evidence.nice_full_scale(900.0, steps) == 200.0


def test_stack_enhancement_divides_by_speed_and_needs_enough_days():
    flux = np.full((4, 2, 3), np.nan)
    flux[:, 0, :] = np.array([2.0, 4.0, 6.0, 8.0])[:, None]  # column of 1 times each speed
    flux[0, 1, 0] = 5.0  # seen on one day of four only
    out = evidence.stack_enhancement(flux, [2.0, 4.0, 6.0, 8.0], 0.3)
    assert out[0] == pytest.approx([1.0, 1.0, 1.0])
    assert np.isnan(out[1]).all()


def test_plane_coefficients_round_trip():
    plane = 3.0 + 0.02 * X_KM[None, :] - 0.05 * YR_KM[:, None]
    assert evidence.plane_coefficients(plane, X_KM, YR_KM) == pytest.approx((3.0, 0.02, -0.05))


def _field(u_ms: float, v_ms: float):
    """A tilted background with a plume that follows the wind from the source, in mol/m2."""
    lats = np.arange(LAT0 - 2.0, LAT0 + 2.0, 0.03)
    lons = np.arange(LON0 - 2.5, LON0 + 2.5, 0.03)
    east = np.radians(lons[None, :] - LON0) * 6371.0088 * np.cos(np.radians(LAT0))
    north = np.radians(lats[:, None] - LAT0) * 6371.0088
    speed = np.hypot(u_ms, v_ms)
    along = (u_ms * east + v_ms * north) / speed
    across = (-v_ms * east + u_ms * north) / speed
    plume = 60e-6 * np.exp(-(across**2) / (2 * 6.0**2)) * np.exp(-np.clip(along, 0, None) / 40.0)
    background = 30e-6 + 4e-8 * east - 6e-8 * north
    return background + np.where(along > 0, plume, 0.0), lats, lons


@pytest.mark.parametrize("u_ms,v_ms", [(0.0, -6.0), (4.0, 4.0)])
def test_north_up_frame_points_where_the_wind_blows(u_ms, v_ms):
    field, lats, lons = _field(u_ms, v_ms)
    scene, plane = day_plane(field, lats, lons, LAT0, LON0, u_ms, v_ms, X_KM, YR_KM, OBS)
    axis = np.arange(-80.0, 81.0, 2.0)
    frame = evidence.north_up_enhancement(
        field, lats, lons, LAT0, LON0, u_ms, v_ms,
        evidence.plane_coefficients(plane, X_KM, YR_KM), axis, axis,
    )  # fmt: skip
    assert frame.shape == (81, 81)
    # The tilted background is gone: far from the plume the frame is flat and near zero.
    upwind = (axis[None, :] * u_ms + axis[:, None] * v_ms) < -20 * np.hypot(u_ms, v_ms)
    assert np.abs(frame[upwind]).max() < 2e-6
    # The centre of mass of the plume lies downwind of the source, in map coordinates.
    w = np.clip(frame, 0, None)
    east_c = (w * axis[None, :]).sum() / w.sum()
    north_c = (w * axis[:, None]).sum() / w.sum()
    assert east_c * u_ms + north_c * v_ms > 10 * np.hypot(u_ms, v_ms)
    assert abs(-v_ms * east_c + u_ms * north_c) < 3 * np.hypot(u_ms, v_ms)


def test_render_stack_is_true_to_scale_and_reports_its_range(tmp_path):
    t, yr = grid(OBS["travel_hours"]), grid(OBS["crosswind_km"])
    enh = np.zeros((len(yr), len(t)))
    enh[40, 20:30] = 18e-6
    enh[:, :200] += 1e-6
    out = evidence.render_stack(tmp_path / "s.webp", enh, t, yr, 8.0, EVI["stack"])
    with Image.open(tmp_path / "s.webp") as im:
        assert im.size == (out["width"], out["height"])
    # 8 h at 8 m/s is 230.4 km of travel against 160 km across the wind.
    assert out["width"] / out["height"] == pytest.approx(230.4 / 160.0, rel=0.01)
    assert out["full_scale_umol_m2"] in EVI["stack"]["full_scale_steps_umol_m2"]
    assert len(out["fan_half_width_km"]) == len(t) and out["fan_half_width_km"][20] == 20.0


def test_render_flipbook_grid(tmp_path):
    frames = [np.full((81, 81), k * 1e-5) for k in range(5)]
    out = evidence.render_flipbook(tmp_path / "f.webp", frames, EVI["flipbook"])
    up = EVI["flipbook"]["upscale"]
    assert (out["frame_w"], out["frame_h"]) == (81 * up, 81 * up)
    assert (out["columns"], out["rows"], out["n_frames"]) == (3, 2, 5)
    with Image.open(tmp_path / "f.webp") as im:
        assert im.size == (3 * 81 * up, 2 * 81 * up)


def _contract(tmp_path, label="2024"):
    finding = {
        "id": f"ph-eu-x-{label}",
        "subject": {"id": "ph-eu-x"},
        "period": {"label": label},
        "claimed": {"value": 7600.0},
        "observed": None,
    }
    path = tmp_path / "findings.json"
    path.write_text(json.dumps({"findings": [finding]}), encoding="utf-8")
    (tmp_path / "finding").mkdir()
    detail = {"id": finding["id"], "reported_series": [{"year": 2024}], "sources": ["EEA"]}
    (tmp_path / "finding" / f"{finding['id']}.json").write_text(json.dumps(detail), "utf-8")
    return path


def test_merge_keeps_the_reported_side_and_adds_the_satellite_side(tmp_path):
    path = _contract(tmp_path)
    observed = {"value": 9124, "lo": 7832, "hi": 11269}
    out = evidence.merge_into_contract(path, "ph-eu-x", "2024", observed, {"days": []})
    assert json.loads(path.read_text("utf-8"))["findings"][0]["observed"] == observed
    doc = json.loads(out.read_text("utf-8"))
    assert doc["reported_series"] == [{"year": 2024}] and doc["days"] == []
    assert doc["observed"] == observed
    assert doc["sources"] == ["EEA", "Copernicus Sentinel-5P", "ERA5"]
    # A second run does not repeat the sources.
    evidence.merge_into_contract(path, "ph-eu-x", "2024", observed, {"days": []})
    assert json.loads(out.read_text("utf-8"))["sources"] == doc["sources"]


def test_merge_refuses_a_different_year_or_an_unknown_subject(tmp_path):
    path = _contract(tmp_path, label="2023")
    with pytest.raises(ValueError):
        evidence.merge_into_contract(path, "ph-eu-x", "2024", {}, {})
    with pytest.raises(KeyError):
        evidence.merge_into_contract(path, "ph-eu-y", "2023", {}, {})


def test_failed_gates_are_not_published(tmp_path):
    (tmp_path / "ph-eu-x").mkdir()
    est = {"gates_failed": ["source_offset"], "observed": {"nox_t_yr": 1.0}, "method": "m"}
    (tmp_path / "ph-eu-x" / "estimate.json").write_text(json.dumps(est), "utf-8")
    with pytest.raises(SystemExit, match="inconclusive"):
        evidence.publish_subject("ph-eu-x", interim_dir=tmp_path, web_public=tmp_path)
    assert not (tmp_path / "img").exists()


def test_showcase_is_named_only_once_it_has_an_estimate(tmp_path):
    path = _contract(tmp_path)
    evidence.merge_into_contract(path, "ph-eu-x", "2024", {"value": 1}, {}, showcase="ph-eu-z")
    assert "showcase" not in json.loads(path.read_text("utf-8"))
    evidence.merge_into_contract(path, "ph-eu-x", "2024", {"value": 1}, {}, showcase="ph-eu-x")
    assert json.loads(path.read_text("utf-8"))["showcase"] == "ph-eu-x"
