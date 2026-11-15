import json

import numpy as np
from PIL import Image

from orbyt.modules.pollution_hunter import layers
from orbyt.modules.pollution_hunter.config import load_config


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


def test_palette_holds_the_ramp_and_index_0_is_clear():
    colours = layers.palette()
    assert colours.shape == (256, 4)
    assert colours[0, 3] == 0
    assert tuple(colours[255]) == (0xFD, 0xF6, 0xD8, 255)
    assert (np.diff(colours[:, 3].astype(int)) >= 0).all()
    index = layers.ramp_index(np.array([np.nan, 5.0, 20.0, 250.0, 999.0]))
    assert list(index) == [0, 0, 0, 255, 255]
    # A palette tile shows what the RGBA colouring shows, to within one ramp step.
    values = np.linspace(0.0, 300.0, 500)
    direct = layers.colorize(values).astype(int)
    by_index = colours[layers.ramp_index(values)].astype(int)
    assert np.abs(direct - by_index).max() <= 2


def test_tile_lonlat_corners_and_symmetry():
    size = layers.TILE_SIZE
    lon, lat = layers.tile_lonlat(0, 0, 0)
    assert lon.shape == (size, size)
    assert np.isclose(lon[0, 0], -180 + 0.5 * 360 / size)  # first pixel centre, half a pixel in
    assert np.isclose(lon[0, -1], 180 - 0.5 * 360 / size)
    assert 84.9 < lat[0, 0] < 85.0511 and -85.0511 < lat[-1, 0] < -84.9  # Mercator limit
    assert np.allclose(lat, -lat[::-1])
    lon1, _ = layers.tile_lonlat(1, 1, 0)
    assert lon1[0, 0] > 0 and lon1[0, 0] < 1
    assert np.isclose(layers.tile_pixel_deg(3), 360 / (size * 8))


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


def _patch():
    values = np.arange(20 * 40, dtype="float64").reshape(20, 40)  # 0.5 degree cells
    return layers.Patch(values, west=0.0, north=50.0, step=0.5)


def test_patch_samples_cell_centres_midpoints_and_is_nan_outside():
    patch = _patch()
    assert patch.bounds == (0.0, 40.0, 20.0, 50.0)
    v = patch.values
    assert patch.sample(np.array([3.25]), np.array([48.75]))[0] == v[2, 6]
    assert np.isclose(patch.sample(np.array([3.5]), np.array([48.75]))[0], (v[2, 6] + v[2, 7]) / 2)
    assert np.isnan(patch.sample(np.array([-1.0, 21.0, 5.0]), np.array([45.0, 45.0, 51.0]))).all()


def test_patch_coarsen_takes_block_means_and_skips_nan():
    patch = _patch()
    values = patch.values.copy()
    values[0, 0] = np.nan
    coarse = layers.Patch(values, patch.west, patch.north, patch.step).coarsen(2)
    assert coarse.values.shape == (10, 20) and coarse.step == 1.0
    assert coarse.bounds == patch.bounds
    assert np.isclose(coarse.values[0, 0], np.mean([values[0, 1], values[1, 0], values[1, 1]]))
    assert np.isclose(coarse.values[3, 4], values[6:8, 8:10].mean())
    assert patch.coarsen(1) is patch


def test_smooth_keeps_a_flat_field_fills_a_single_gap_and_leaves_a_large_one():
    flat = np.full((40, 60), 7.0)
    flat[10, 10] = np.nan
    flat[25:35, 30:50] = np.nan
    out = layers.smooth(flat, 1.5, 1.5)
    assert np.isclose(out[10, 10], 7.0)
    assert np.isnan(out[30, 40])
    assert np.allclose(out[np.isfinite(out)], 7.0)
    # A single hot cell is spread out, and its total is kept.
    spike = np.zeros((41, 41))
    spike[20, 20] = 100.0
    spread = layers.smooth(spike, 2.0, 2.0)
    assert spread[20, 20] < 10.0 and np.isclose(spread.sum(), 100.0, rtol=1e-3)
    assert layers.smooth(spike, 0.0, 0.0) is spike


def test_feather_weight_rises_from_the_edge_to_one_inside():
    bounds = (0.0, 40.0, 20.0, 50.0)
    lon = np.array([-1.0, 0.0, 0.5, 1.0, 10.0, 19.5, 10.0])
    lat = np.array([45.0, 45.0, 45.0, 45.0, 45.0, 45.0, 40.25])
    w = layers.feather_weight(lon, lat, bounds, 1.0)
    assert list(w[[0, 1]]) == [0.0, 0.0]
    assert np.isclose(w[2], 0.5) and w[3] == 1.0 and w[4] == 1.0
    assert np.isclose(w[5], 0.5)
    assert 0.0 < w[6] < 0.5


def test_sample_layer_uses_the_region_inside_and_the_world_outside():
    world = np.full((180, 360), 30.0)
    region = layers.Patch(np.full((20, 40), 200.0), west=0.0, north=50.0, step=0.5)
    lon = np.array([10.0, 0.5, -5.0, 30.0])
    lat = np.array([45.0, 45.0, 45.0, 45.0])
    out = layers.sample_layer(world, region, 1.0, lon, lat)
    assert out[0] == 200.0
    assert np.isclose(out[1], 115.0)  # half way through the feather
    assert out[2] == 30.0 and out[3] == 30.0
    assert (layers.sample_layer(world, None, 1.0, lon, lat) == 30.0).all()
    # Where the region has no data the world's value stays.
    holed = layers.Patch(np.full((20, 40), np.nan), west=0.0, north=50.0, step=0.5)
    assert layers.sample_layer(world, holed, 1.0, lon, lat)[0] == 30.0


def test_region_tile_range_and_layer_tiles():
    europe = (-12.0, 33.0, 36.0, 70.0)
    assert layers.region_tile_range(europe, 4) == (7, 3, 9, 6)
    assert layers.region_tile_range(europe, 5) == (14, 7, 19, 12)
    # A region that ends exactly on a tile edge does not take the next tile.
    assert layers.region_tile_range((0.0, 0.0, 90.0, 66.51326), 2) == (2, 1, 2, 1)
    world_only = layers.layer_tiles(3, None, 3)
    assert len(world_only) == 1 + 4 + 16 + 64
    tiles = layers.layer_tiles(3, europe, 5)
    assert len(tiles) == 85 + 3 * 4 + 6 * 6
    assert (4, 8, 5) in tiles and (4, 0, 0) not in tiles


def test_cut_layer_writes_palette_tiles_with_the_region_on_top(tmp_path):
    world = np.full((90, 180), 5.0)  # clear everywhere
    region = layers.Patch(np.full((40, 80), 300.0), west=0.0, north=40.0, step=0.5)
    stats = layers.cut_layer(
        world, region, tmp_path, global_max_zoom=1, region_max_zoom=2, feather_deg=1.0, size=64
    )
    x0, y0, x1, y1 = layers.region_tile_range(region.bounds, 2)
    n_region = (x1 - x0 + 1) * (y1 - y0 + 1)
    assert stats["tiles"] == 5 + n_region == len(list(tmp_path.rglob("*.png")))
    assert stats["empty"] == 5  # the world's own tiles hold nothing above 20
    with Image.open(tmp_path / "2" / str(x0) / f"{y1}.png") as im:
        assert im.size == (64, 64) and im.mode == "P"
        rgba = np.asarray(im.convert("RGBA"))
    assert rgba[..., 3].max() == 255
    assert tuple(rgba[rgba[..., 3] == 255][0]) == (0xFD, 0xF6, 0xD8, 255)
    with Image.open(tmp_path / "0" / "0" / "0.png") as im:
        assert np.asarray(im.convert("RGBA"))[..., 3].max() == 0


def test_manifest_lists_the_layers_on_disk(tmp_path):
    cfg = load_config()["layers"]
    tiles_dir = tmp_path / "tiles"
    for period in (str(cfg["annual_year"]), "2022-07", "2022-08", "notes"):
        (tiles_dir / period).mkdir(parents=True)
    out = tmp_path / "data" / "layers.json"
    manifest = layers.write_manifest(cfg, tiles_dir, out)
    assert json.loads(out.read_text(encoding="utf-8")) == manifest
    assert manifest["annual"]["period"] == str(cfg["annual_year"])
    assert manifest["monthly"]["periods"] == ["2022-07", "2022-08"]
    assert set(manifest["annual"]["region_tiles"]) == {"4", "5", "6"}
    assert set(manifest["monthly"]["region_tiles"]) == {"4"}
    assert manifest["tile_size"] == layers.TILE_SIZE
    assert manifest["attribution"].endswith(f"2022 to {cfg['annual_year']}")
    # With nothing on disk both layers are null.
    empty = layers.write_manifest(cfg, tmp_path / "none", tmp_path / "empty.json")
    assert empty["annual"] is None and empty["monthly"] is None
