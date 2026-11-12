import numpy as np
from PIL import Image

from orbyt.modules.pollution_hunter import layers


def test_ramp_position_is_square_root_scale_clipped_at_20_and_250():
    t = layers.ramp_position(np.array([-5.0, 0.0, 20.0, 250.0, 400.0]))
    assert list(t) == [0.0, 0.0, 0.0, 1.0, 1.0]
    mid = (np.sqrt(20.0) + np.sqrt(250.0)) / 2
    assert np.isclose(layers.ramp_position(np.array([mid**2]))[0], 0.5)
    # Square root scale: the lower half of the values spans more than half of the ramp.
    assert layers.ramp_position(np.array([135.0]))[0] > 0.5


def test_colorize_clear_below_range_and_for_nan_and_opaque_at_top():
    out = layers.colorize(np.array([np.nan, 5.0, 20.0, 250.0, 999.0]))
    assert list(out[:3, 3]) == [0, 0, 0]
    assert tuple(out[3]) == (0xFD, 0xF6, 0xD8, 255)
    assert tuple(out[4]) == (0xFD, 0xF6, 0xD8, 255)


def test_ramp_gets_lighter_and_more_opaque_at_every_step():
    values = np.linspace(layers.LO_UMOL, layers.HI_UMOL, 200)
    rgba = layers.colorize(values).astype(float)
    luma = 0.2126 * rgba[:, 0] + 0.7152 * rgba[:, 1] + 0.0722 * rgba[:, 2]
    assert (np.diff(luma) >= -1).all()
    assert (np.diff(rgba[:, 3]) >= 0).all()


def test_stops_are_hit_exactly():
    for pos, colour, opacity in layers.RAMP[1:]:
        lo, hi = np.sqrt(layers.LO_UMOL), np.sqrt(layers.HI_UMOL)
        umol = (lo + pos * (hi - lo)) ** 2
        px = layers.colorize(np.array([umol]))[0]
        assert tuple(px[:3]) == layers._rgb(colour)
        assert px[3] == round(opacity * 255)


def test_tile_lonlat_corners_and_symmetry():
    lon, lat = layers.tile_lonlat(0, 0, 0)
    assert np.isclose(lon[0, 0], -180 + 0.5 * 360 / 256)  # first pixel centre, half a pixel in
    assert np.isclose(lon[0, -1], 180 - 0.5 * 360 / 256)
    assert 84.9 < lat[0, 0] < 85.0511 and -85.0511 < lat[-1, 0] < -84.9  # Mercator limit
    assert np.allclose(lat, -lat[::-1])
    lon1, _ = layers.tile_lonlat(1, 1, 0)
    assert lon1[0, 0] > 0 and lon1[0, 0] < 1


def test_sample_global_returns_cell_values_and_midpoints_and_wraps():
    rows, cols = 18, 36  # 10 degree cells
    grid = np.arange(rows * cols, dtype="float64").reshape(rows, cols)
    centre = layers.sample_global(grid, np.array([-175.0 + 70.0]), np.array([85.0 - 50.0]))
    assert centre[0] == grid[5, 7]
    mid = layers.sample_global(grid, np.array([-175.0 + 75.0]), np.array([85.0 - 50.0]))
    assert np.isclose(mid[0], (grid[5, 7] + grid[5, 8]) / 2)
    seam = layers.sample_global(grid, np.array([180.0]), np.array([0.0]))
    assert np.isfinite(seam[0])
    assert np.isnan(
        layers.sample_global(np.full((4, 8), np.nan), np.array([0.0]), np.array([0.0]))[0]
    )


def test_tile_count_zoom_0_to_4_is_341():
    assert layers.tile_count(4) == 341


def test_cut_tiles_writes_valid_256px_rgba_pngs(tmp_path):
    grid = np.full((90, 180), 5.0)
    grid[40:50, 90:100] = 300.0  # a hot patch just north-east of the equator and prime meridian
    n = layers.cut_tiles(grid, tmp_path, max_zoom=2)
    assert n == layers.tile_count(2) == 21
    assert len(list(tmp_path.rglob("*.png"))) == 21
    with Image.open(tmp_path / "0" / "0" / "0.png") as im:
        assert im.size == (256, 256) and im.mode == "RGBA"
        arr = np.asarray(im)
    assert arr[..., 3].max() == 255  # the hot patch shows
    assert (arr[..., 3] == 0).mean() > 0.9  # everything else is clear
