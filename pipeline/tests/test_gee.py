import numpy as np
import rasterio

from orbyt.sources import gee


def test_grid_shape_world_at_tenth_degree():
    assert gee.grid_shape(gee.WORLD, 0.1) == (3600, 1800)


def test_chunk_windows_tile_the_grid_exactly():
    width, height = 1000, 450
    covered = np.zeros((height, width), dtype=int)
    for col, row, w, h in gee.chunk_windows(width, height, 400):
        covered[row : row + h, col : col + w] += 1
    assert (covered == 1).all()


def test_fetch_grid_stitches_windows_and_masks_nodata(tmp_path):
    width, height = 50, 30
    truth = np.arange(width * height, dtype="float32").reshape(height, width)
    truth[3, 7] = gee.NODATA
    calls = []

    def fake_fetch(col, row, w, h):
        calls.append((col, row, w, h))
        return truth[row : row + h, col : col + w].copy()

    out = gee.fetch_grid(fake_fetch, width, height, chunk=20, cache_dir=tmp_path, cache_key="t")
    assert np.isnan(out[3, 7])
    expected = truth.copy()
    expected[3, 7] = np.nan
    np.testing.assert_array_equal(out, expected)

    # A second run is served from the cache without calling the fetcher again.
    n_calls = len(calls)
    again = gee.fetch_grid(fake_fetch, width, height, chunk=20, cache_dir=tmp_path, cache_key="t")
    assert len(calls) == n_calls
    np.testing.assert_array_equal(again, expected)


def test_save_geotiff_round_trip(tmp_path):
    arr = np.random.default_rng(0).random((18, 36), dtype="float32")
    arr[0, 0] = np.nan
    path = gee.save_geotiff(arr, tmp_path / "x.tif", gee.WORLD, 10.0)
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 4326
        assert (src.width, src.height) == (36, 18)
        assert src.bounds.left == -180 and src.bounds.top == 90
        assert src.bounds.right == 180 and src.bounds.bottom == -90
        np.testing.assert_array_equal(src.read(1), arr)
