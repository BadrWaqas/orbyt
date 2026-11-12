"""Colour the global NO2 grid with the plume ramp and cut it into web map PNG tiles.

M1.3: PLAN.md 9.2. Values run from 20 to 250 micromol/m2 on a square-root scale and are clipped
at both ends. Tiles are 256 px Web Mercator PNGs for zoom 0 to 4 (341 tiles), in the usual
``{z}/{x}/{y}.png`` layout that a MapLibre raster source reads.

    uv run python -m orbyt.modules.pollution_hunter.layers
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TIF = REPO_ROOT / "data" / "raw" / "no2_annual_mean_2024_0p1deg.tif"
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "tiles" / "no2-2024"

TILE_SIZE = 256
LO_UMOL = 20.0  # at or below: fully transparent
HI_UMOL = 250.0  # at or above: the top of the ramp
MOL_TO_UMOL = 1e6

# PLAN.md 9.2: position, colour, opacity. Lightness rises at every step.
RAMP: tuple[tuple[float, str, float], ...] = (
    (0.00, "#4F1C00", 0.00),
    (0.15, "#7D3501", 0.35),
    (0.35, "#AF5504", 0.60),
    (0.55, "#D97A05", 0.80),
    (0.75, "#F5A420", 0.90),
    (0.90, "#FCD583", 0.95),
    (1.00, "#FDF6D8", 1.00),
)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ramp_position(umol: np.ndarray) -> np.ndarray:
    """Map micromol/m2 to a 0 to 1 ramp position on a square-root scale, clipped at both ends.

    NaN stays NaN. The scale is linear in sqrt(value) between sqrt(20) and sqrt(250).
    """
    v = np.asarray(umol, dtype="float64")
    lo, hi = np.sqrt(LO_UMOL), np.sqrt(HI_UMOL)
    t = (np.sqrt(np.clip(v, 0.0, None)) - lo) / (hi - lo)
    return np.clip(t, 0.0, 1.0)


def colorize(umol: np.ndarray) -> np.ndarray:
    """RGBA uint8 image [..., 4] for an array of micromol/m2. NaN and values <= 20 are clear."""
    t = ramp_position(umol)
    pos = [p for p, _, _ in RAMP]
    rgb = np.array([_rgb(c) for _, c, _ in RAMP], dtype="float64")
    alpha = np.array([a for _, _, a in RAMP], dtype="float64")
    out = np.zeros(t.shape + (4,), dtype="uint8")
    safe = np.nan_to_num(t, nan=0.0)
    for k in range(3):
        out[..., k] = np.rint(np.interp(safe, pos, rgb[:, k])).astype("uint8")
    out[..., 3] = np.rint(np.interp(safe, pos, alpha) * 255).astype("uint8")
    out[np.isnan(t), 3] = 0
    return out


def tile_lonlat(z: int, x: int, y: int, size: int = TILE_SIZE) -> tuple[np.ndarray, np.ndarray]:
    """Pixel centre longitude and latitude (degrees) of a Web Mercator tile, each [size, size]."""
    world = size * 2**z
    px = x * size + np.arange(size) + 0.5
    py = y * size + np.arange(size) + 0.5
    lon = px / world * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * py / world))))
    return np.broadcast_to(lon[None, :], (size, size)), np.broadcast_to(lat[:, None], (size, size))


def sample_global(grid: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear sample of a global north-up lat/lon grid. Longitude wraps, latitude clamps.

    ``grid`` is [rows, cols] covering -180..180 and -90..90, with cell centres at half steps.
    NaN in any of the four neighbours gives NaN.
    """
    rows, cols = grid.shape
    x = (lon + 180.0) / (360.0 / cols) - 0.5
    y = (90.0 - lat) / (180.0 / rows) - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    xa, xb = x0 % cols, (x0 + 1) % cols
    ya, yb = np.clip(y0, 0, rows - 1), np.clip(y0 + 1, 0, rows - 1)
    top = grid[ya, xa] * (1 - fx) + grid[ya, xb] * fx
    bottom = grid[yb, xa] * (1 - fx) + grid[yb, xb] * fx
    return top * (1 - fy) + bottom * fy


def tile_count(max_zoom: int) -> int:
    return sum(4**z for z in range(max_zoom + 1))


def cut_tiles(grid_umol: np.ndarray, out_dir: Path, max_zoom: int = 4) -> int:
    """Write every tile from zoom 0 to ``max_zoom`` under ``out_dir``. Returns the tile count."""
    n = 0
    for z in range(max_zoom + 1):
        for x in range(2**z):
            for y in range(2**z):
                lon, lat = tile_lonlat(z, x, y)
                rgba = colorize(sample_global(grid_umol, lon, lat))
                path = out_dir / str(z) / str(x) / f"{y}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(rgba, "RGBA").save(path, optimize=True)
                n += 1
    return n


def read_grid_umol(tif: Path) -> np.ndarray:
    """Read the global GeoTIFF from sources.gee and convert mol/m2 to micromol/m2."""
    with rasterio.open(tif) as src:
        b = src.bounds
        if (b.left, b.bottom, b.right, b.top) != (-180.0, -90.0, 180.0, 90.0):
            raise ValueError(f"{tif} is not a global grid: {tuple(b)}")
        return src.read(1).astype("float64") * MOL_TO_UMOL


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut the NO2 grid into PNG map tiles")
    parser.add_argument("--tif", type=Path, default=DEFAULT_TIF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-zoom", type=int, default=4)
    args = parser.parse_args()
    n = cut_tiles(read_grid_umol(args.tif), args.out, args.max_zoom)
    print(f"wrote {n} tiles to {args.out}")


if __name__ == "__main__":
    main()
