"""Earth Engine session and gridded NO2 downloads.

M1.2: the annual mean tropospheric NO2 column on a regular lat/lon grid, pulled in chunks
with ``ee.data.computePixels`` and written as a GeoTIFF.

    uv run python -m orbyt.sources.gee --year 2024
"""

from __future__ import annotations

import argparse
import hashlib
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np
import rasterio
from rasterio.transform import from_origin

PROJECT = "orbyt-earth"
COLLECTION = "COPERNICUS/S5P/OFFL/L3_NO2"
BAND = "tropospheric_NO2_column_number_density"  # mol/m2, qa 0.75 filter already applied
NODATA = -9999.0

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"

# (west, south, east, north) in degrees
WORLD = (-180.0, -90.0, 180.0, 90.0)

Fetch = Callable[[int, int, int, int], np.ndarray]


def init(project: str = PROJECT) -> None:
    """Start an Earth Engine session. Run ``earthengine authenticate`` once beforehand."""
    ee.Initialize(project=project)


def annual_mean_no2(year: int) -> ee.Image:
    """Mean tropospheric NO2 column over one calendar year, in mol/m2."""
    return (
        ee.ImageCollection(COLLECTION)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select(BAND)
        .mean()
    )


def grid_shape(bounds: tuple[float, float, float, float], step: float) -> tuple[int, int]:
    """(width, height) of a grid with square cells of ``step`` degrees covering ``bounds``."""
    west, south, east, north = bounds
    return round((east - west) / step), round((north - south) / step)


def chunk_windows(width: int, height: int, size: int) -> Iterator[tuple[int, int, int, int]]:
    """Yield (col, row, w, h) windows that tile a width x height grid without overlap."""
    for row in range(0, height, size):
        for col in range(0, width, size):
            yield col, row, min(size, width - col), min(size, height - row)


def _ee_fetch(image: ee.Image, bounds: tuple[float, float, float, float], step: float) -> Fetch:
    """Build the function that downloads one window as float32, north row first."""
    west, _, _, north = bounds
    expression = image.unmask(NODATA)

    def fetch(col: int, row: int, w: int, h: int) -> np.ndarray:
        request = {
            "expression": expression,
            "fileFormat": "NUMPY_NDARRAY",
            "grid": {
                "dimensions": {"width": w, "height": h},
                "affineTransform": {
                    "scaleX": step,
                    "shearX": 0,
                    "translateX": west + col * step,
                    "shearY": 0,
                    "scaleY": -step,
                    "translateY": north - row * step,
                },
                "crsCode": "EPSG:4326",
            },
        }
        return ee.data.computePixels(request)[BAND].astype("float32")

    return fetch


def _with_retries(fetch: Fetch, attempts: int = 4, wait_s: float = 5.0) -> Fetch:
    def wrapped(col: int, row: int, w: int, h: int) -> np.ndarray:
        for attempt in range(1, attempts + 1):
            try:
                return fetch(col, row, w, h)
            except ee.EEException:
                if attempt == attempts:
                    raise
                time.sleep(wait_s * attempt)
        raise AssertionError("unreachable")

    return wrapped


def fetch_grid(
    fetch: Fetch,
    width: int,
    height: int,
    chunk: int = 300,
    workers: int = 8,
    cache_dir: Path | None = None,
    cache_key: str = "",
    log: Callable[[str], None] | None = None,
) -> np.ndarray:
    """Download a width x height grid window by window and stitch it together.

    Returns float32 [row, col] with the north row first and NaN where there is no data.
    Each window is cached as .npy under ``cache_dir`` so a failed run resumes where it stopped.
    """
    out = np.full((height, width), np.nan, dtype="float32")
    windows = list(chunk_windows(width, height, chunk))
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)

    def load(window: tuple[int, int, int, int]) -> np.ndarray:
        col, row, w, h = window
        cached = None
        if cache_dir is not None:
            digest = hashlib.sha256(f"{cache_key}|{col}|{row}|{w}|{h}".encode()).hexdigest()[:16]
            cached = cache_dir / f"{digest}.npy"
        if cached is not None and cached.exists():
            return np.load(cached)
        arr = fetch(col, row, w, h)
        if arr.shape != (h, w):
            raise ValueError(f"window {col},{row}: expected {(h, w)}, got {arr.shape}")
        if cached is not None:
            np.save(cached, arr)
        return arr

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (window, arr) in enumerate(zip(windows, pool.map(load, windows), strict=True), 1):
            col, row, w, h = window
            arr = arr.astype("float32")
            arr[arr == NODATA] = np.nan
            out[row : row + h, col : col + w] = arr
            if log is not None:
                log(f"window {i}/{len(windows)}")
    return out


def save_geotiff(
    arr: np.ndarray, path: Path, bounds: tuple[float, float, float, float], step: float
) -> Path:
    """Write a north-up float32 grid as a single band GeoTIFF in EPSG:4326, NaN as nodata."""
    west, _, _, north = bounds
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(west, north, step, step),
        nodata=float("nan"),
        compress="deflate",
        predictor=3,
    ) as dst:
        dst.write(arr.astype("float32"), 1)
        dst.set_band_description(1, BAND)
        dst.update_tags(source=COLLECTION, units="mol/m2")
    return path


def download_annual_mean(
    year: int,
    step: float = 0.1,
    bounds: tuple[float, float, float, float] = WORLD,
    out_dir: Path = RAW_DIR,
    chunk: int = 300,
) -> Path:
    """Annual mean NO2 for ``year`` on a ``step`` degree grid, saved under ``out_dir``."""
    init()
    width, height = grid_shape(bounds, step)
    fetch = _with_retries(_ee_fetch(annual_mean_no2(year), bounds, step))
    arr = fetch_grid(
        fetch,
        width,
        height,
        chunk=chunk,
        cache_dir=out_dir / "gee_cache",
        cache_key=f"{COLLECTION}|{BAND}|annual-mean|{year}|{step}|{bounds}",
        log=print,
    )
    name = f"no2_annual_mean_{year}_{str(step).replace('.', 'p')}deg.tif"
    return save_geotiff(arr, out_dir / name, bounds, step)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the annual mean NO2 grid as GeoTIFF")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--step", type=float, default=0.1, help="cell size in degrees")
    args = parser.parse_args()
    path = download_annual_mean(args.year, step=args.step)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
