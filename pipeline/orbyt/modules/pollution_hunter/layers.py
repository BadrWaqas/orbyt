"""Colour the mean NO2 grids with the plume ramp and cut them into web map tiles.

M1.3 and M6.2: PLAN.md 9.2. Values run from 20 to 250 micromol/m2 on a square-root scale and are
clipped at both ends. A layer is one period, the annual mean or one month, and has two parts:

    global   the whole world from the 0.1 degree grid, zoom 0 to 3
    region   Europe from its finer grid, from zoom 4 down to 1.2 km a pixel for the annual mean

Tiles are 512 px Web Mercator PNGs in the usual ``{z}/{x}/{y}.png`` layout, under
``web/public/tiles/no2/<period>``. They are 8 bit palette images: the colour and the opacity of
a pixel are one function of its place on the ramp, so 256 palette entries hold the ramp without
loss and a tile is a quarter of the size of an RGBA one. ``layers.json`` (PLAN.md 2.5) tells the
site which periods and which tiles exist.

    uv run python -m orbyt.modules.pollution_hunter.layers annual
    uv run python -m orbyt.modules.pollution_hunter.layers monthly
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from scipy.ndimage import gaussian_filter

from orbyt.modules.pollution_hunter import grids
from orbyt.modules.pollution_hunter.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TIF = REPO_ROOT / "data" / "raw" / "no2_annual_mean_2024_0p1deg.tif"
TILES_DIR = REPO_ROOT / "web" / "public" / "tiles" / "no2"
MANIFEST = REPO_ROOT / "web" / "public" / "data" / "v1" / "pollution-hunter" / "layers.json"
TILES_URL = "/tiles/no2/{period}/{z}/{x}/{y}.png"

TILE_SIZE = 512
LO_UMOL = 20.0  # at or below: fully transparent
HI_UMOL = 250.0  # at or above: the top of the ramp
MOL_TO_UMOL = 1e6
KM_PER_DEG = 111.2

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

Bounds = tuple[float, float, float, float]  # west, south, east, north


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


def _ramp_rgba(t: np.ndarray) -> np.ndarray:
    """RGBA uint8 for ramp positions from 0 to 1."""
    pos = [p for p, _, _ in RAMP]
    rgb = np.array([_rgb(c) for _, c, _ in RAMP], dtype="float64")
    alpha = np.array([a for _, _, a in RAMP], dtype="float64")
    out = np.zeros(t.shape + (4,), dtype="uint8")
    for k in range(3):
        out[..., k] = np.rint(np.interp(t, pos, rgb[:, k])).astype("uint8")
    out[..., 3] = np.rint(np.interp(t, pos, alpha) * 255).astype("uint8")
    return out


def colorize(umol: np.ndarray) -> np.ndarray:
    """RGBA uint8 image [..., 4] for an array of micromol/m2. NaN and values <= 20 are clear."""
    t = ramp_position(umol)
    out = _ramp_rgba(np.nan_to_num(t, nan=0.0))
    out[np.isnan(t), 3] = 0
    return out


def ramp_index(umol: np.ndarray) -> np.ndarray:
    """Palette index, 0 to 255, for an array of micromol/m2. NaN and values <= 20 are index 0."""
    t = np.nan_to_num(ramp_position(umol), nan=0.0)
    return np.rint(t * 255).astype("uint8")


def palette() -> np.ndarray:
    """The 256 RGBA colours the palette indices stand for. Index 0 is clear."""
    return _ramp_rgba(np.arange(256) / 255.0)


def tile_lonlat(z: int, x: int, y: int, size: int = TILE_SIZE) -> tuple[np.ndarray, np.ndarray]:
    """Pixel centre longitude and latitude (degrees) of a Web Mercator tile, each [size, size]."""
    world = size * 2**z
    px = x * size + np.arange(size) + 0.5
    py = y * size + np.arange(size) + 0.5
    lon = px / world * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * py / world))))
    return np.broadcast_to(lon[None, :], (size, size)), np.broadcast_to(lat[:, None], (size, size))


def tile_pixel_deg(z: int, size: int = TILE_SIZE) -> float:
    """Width of one tile pixel in degrees of longitude."""
    return 360.0 / (size * 2**z)


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


@dataclass(frozen=True)
class Patch:
    """A north-up lat/lon grid over part of the world, in micromol/m2."""

    values: np.ndarray  # [rows, cols], north row first, cell centres at half steps
    west: float
    north: float
    step: float

    @property
    def bounds(self) -> Bounds:
        rows, cols = self.values.shape
        return (self.west, self.north - rows * self.step, self.west + cols * self.step, self.north)

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Bilinear sample. NaN outside the patch and where a neighbour is NaN."""
        rows, cols = self.values.shape
        x = (lon - self.west) / self.step - 0.5
        y = (self.north - lat) / self.step - 0.5
        inside = (x >= 0) & (x <= cols - 1) & (y >= 0) & (y <= rows - 1)
        x0 = np.clip(np.floor(x).astype(int), 0, cols - 2)
        y0 = np.clip(np.floor(y).astype(int), 0, rows - 2)
        fx, fy = np.clip(x - x0, 0.0, 1.0), np.clip(y - y0, 0.0, 1.0)
        v = self.values
        top = v[y0, x0] * (1 - fx) + v[y0, x0 + 1] * fx
        bottom = v[y0 + 1, x0] * (1 - fx) + v[y0 + 1, x0 + 1] * fx
        return np.where(inside, top * (1 - fy) + bottom * fy, np.nan)

    def coarsen(self, factor: int) -> Patch:
        """Mean over ``factor`` by ``factor`` blocks, skipping NaN. Cells left over are dropped."""
        if factor <= 1:
            return self
        rows, cols = (n // factor * factor for n in self.values.shape)
        blocks = self.values[:rows, :cols].reshape(rows // factor, factor, cols // factor, factor)
        ok = np.isfinite(blocks)
        n = ok.sum(axis=(1, 3))
        total = np.where(ok, blocks, 0.0).sum(axis=(1, 3))
        mean = np.where(n > 0, total / np.maximum(n, 1), np.nan)
        return Patch(mean, self.west, self.north, self.step * factor)


def smooth(
    values: np.ndarray, sigma_rows: float, sigma_cols: float, wrap_cols: bool = False
) -> np.ndarray:
    """Gaussian smoothing that skips NaN. Sigmas are in cells.

    A cell keeps a value where at least half of the kernel's weight fell on valid cells, so a
    single missing cell is filled from its neighbours and the rim of a large gap stays empty.
    """
    if sigma_rows <= 0 and sigma_cols <= 0:
        return values
    ok = np.isfinite(values)
    mode = ("nearest", "wrap" if wrap_cols else "nearest")
    sigma = (sigma_rows, sigma_cols)
    total = gaussian_filter(np.where(ok, values, 0.0), sigma, mode=mode)
    weight = gaussian_filter(ok.astype("float64"), sigma, mode=mode)
    return np.where(weight >= 0.5, total / np.maximum(weight, 1e-9), np.nan)


def smooth_km(patch: Patch, sigma_km: float) -> Patch:
    """Smooth a patch by ``sigma_km`` on the ground, at the latitude of its middle."""
    _, south, _, north = patch.bounds
    cos_mid = np.cos(np.radians((south + north) / 2))
    rows = sigma_km / (KM_PER_DEG * patch.step)
    return Patch(smooth(patch.values, rows, rows / cos_mid), patch.west, patch.north, patch.step)


def feather_weight(lon: np.ndarray, lat: np.ndarray, bounds: Bounds, width_deg: float):
    """Share of the region's own grid: 0 at its edge and outside, 1 from ``width_deg`` inside."""
    west, south, east, north = bounds
    inside = np.minimum(np.minimum(lon - west, east - lon), np.minimum(lat - south, north - lat))
    t = np.clip(inside / width_deg, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sample_layer(
    world: np.ndarray, region: Patch | None, feather_deg: float, lon: np.ndarray, lat: np.ndarray
) -> np.ndarray:
    """The layer's value at each point: the region's grid where there is one, blended into the
    global grid towards the region's edge, and the global grid everywhere else."""
    lo = sample_global(world, lon, lat)
    if region is None:
        return lo
    w = feather_weight(lon, lat, region.bounds, feather_deg)
    if not (w > 0).any():
        return lo
    hi = region.sample(lon, lat)
    blend = np.where(np.isfinite(lo), w * hi + (1.0 - w) * lo, hi)
    return np.where((w > 0) & np.isfinite(hi), blend, lo)


def region_tile_range(bounds: Bounds, z: int) -> tuple[int, int, int, int]:
    """The tiles at zoom ``z`` that touch ``bounds``, as x0, y0, x1, y1, all included."""
    west, south, east, north = bounds
    n = 2**z

    def col(lon: float) -> float:
        return (lon + 180.0) / 360.0 * n

    def row(lat: float) -> float:
        return (1.0 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2.0 * n

    return (
        int(np.floor(col(west))),
        int(np.floor(row(north))),
        int(np.ceil(col(east))) - 1,
        int(np.ceil(row(south))) - 1,
    )


def layer_tiles(
    global_max_zoom: int, region_bounds: Bounds | None, region_max_zoom: int
) -> list[tuple[int, int, int]]:
    """Every tile of a layer as (z, x, y): the whole world, then the region at deeper zooms."""
    tiles = [
        (z, x, y) for z in range(global_max_zoom + 1) for x in range(2**z) for y in range(2**z)
    ]
    if region_bounds is not None:
        for z in range(global_max_zoom + 1, region_max_zoom + 1):
            x0, y0, x1, y1 = region_tile_range(region_bounds, z)
            tiles += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return tiles


def write_tile(index: np.ndarray, path: Path) -> int:
    """Save a tile of palette indices as an 8 bit PNG. Returns its size in bytes."""
    colours = palette()
    image = Image.fromarray(index, "P")
    image.putpalette(colours[:, :3].tobytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True, transparency=colours[:, 3].tobytes())
    return path.stat().st_size


def cut_layer(
    world: np.ndarray,
    region: Patch | None,
    out_dir: Path,
    global_max_zoom: int = 3,
    region_max_zoom: int = 3,
    feather_deg: float = 1.0,
    size: int = TILE_SIZE,
) -> dict[str, int]:
    """Write every tile of one layer under ``out_dir``. Returns counts and the total size.

    ``world`` is the global grid and ``region`` the finer one, both in micromol/m2. For each
    zoom the region's grid is first averaged down to about the size of a tile pixel, so a tile
    never skips cells.
    """
    bounds = region.bounds if region is not None else None
    stats = {"tiles": 0, "empty": 0, "bytes": 0}
    coarse: dict[int, Patch] = {}
    for z, x, y in layer_tiles(global_max_zoom, bounds, region_max_zoom):
        lon, lat = tile_lonlat(z, x, y, size)
        patch = None
        if region is not None and z > global_max_zoom:
            if z not in coarse:
                factor = int(tile_pixel_deg(z, size) / region.step + 0.25)
                coarse[z] = region.coarsen(max(1, factor))
            patch = coarse[z]
        index = ramp_index(sample_layer(world, patch, feather_deg, lon, lat))
        stats["bytes"] += write_tile(index, out_dir / str(z) / str(x) / f"{y}.png")
        stats["tiles"] += 1
        stats["empty"] += int(not index.any())
    return stats


def read_grid_umol(tif: Path) -> np.ndarray:
    """Read the global GeoTIFF from sources.gee and convert mol/m2 to micromol/m2."""
    with rasterio.open(tif) as src:
        b = src.bounds
        if (b.left, b.bottom, b.right, b.top) != (-180.0, -90.0, 180.0, 90.0):
            raise ValueError(f"{tif} is not a global grid: {tuple(b)}")
        return src.read(1).astype("float64") * MOL_TO_UMOL


def read_patch_umol(tif: Path) -> Patch:
    """Read a regional GeoTIFF from grids.py as a patch in micromol/m2."""
    with rasterio.open(tif) as src:
        values = src.read(1).astype("float64") * MOL_TO_UMOL
        return Patch(values, src.bounds.left, src.bounds.top, src.res[0])


def write_manifest(cfg: dict, tiles_dir: Path = TILES_DIR, path: Path = MANIFEST) -> dict:
    """Write ``layers.json`` from the layers that are on disk (PLAN.md 2.5)."""
    found = tiles_dir.iterdir() if tiles_dir.exists() else []
    periods = sorted(p.name for p in found if p.is_dir())
    months = [p for p in periods if re.fullmatch(r"\d{4}-\d{2}", p)]
    year = str(cfg["annual_year"])
    region = tuple(cfg["region_bounds_deg"])
    g = cfg["global_max_zoom"]

    def ranges(max_zoom: int) -> dict[str, list[int]]:
        return {str(z): list(region_tile_range(region, z)) for z in range(g + 1, max_zoom + 1)}

    years = sorted({year, *(m[:4] for m in months)})
    span = years[0] if len(years) == 1 else f"{years[0]} to {years[-1]}"
    manifest = {
        "module": "pollution-hunter",
        "tiles": TILES_URL,
        "tile_size": cfg["tile_size_px"],
        "units": "micromol/m2",
        "scale": {"kind": "sqrt", "lo": LO_UMOL, "hi": HI_UMOL},
        "ramp": [[p, c, a] for p, c, a in RAMP],
        "global_max_zoom": g,
        "region_bounds": list(region),
        "annual": (
            {
                "period": year,
                "max_zoom": cfg["region_max_zoom_annual"],
                "region_tiles": ranges(cfg["region_max_zoom_annual"]),
            }
            if year in periods
            else None
        ),
        "monthly": (
            {
                "periods": months,
                "max_zoom": cfg["region_max_zoom_monthly"],
                "region_tiles": ranges(cfg["region_max_zoom_monthly"]),
            }
            if months
            else None
        ),
        "attribution": f"Contains modified Copernicus Sentinel data {span}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def cut_annual(cfg: dict, year: int, tiles_dir: Path = TILES_DIR) -> dict[str, int]:
    world = read_grid_umol(DEFAULT_TIF.with_name(f"no2_annual_mean_{year}_0p1deg.tif"))
    region = read_patch_umol(grids.grid_path(str(year), "region", cfg["region_step_annual_deg"]))
    region = smooth_km(region, cfg["smooth_sigma_annual_region_km"])
    return cut_layer(
        world,
        region,
        tiles_dir / str(year),
        cfg["global_max_zoom"],
        cfg["region_max_zoom_annual"],
        cfg["feather_deg"],
        cfg["tile_size_px"],
    )


def cut_month(cfg: dict, month: str, tiles_dir: Path = TILES_DIR) -> dict[str, int]:
    step = cfg["global_step_deg"]
    world = read_grid_umol(grids.grid_path(month, "global", step))
    sigma = cfg["smooth_sigma_monthly_global_deg"] / step
    world = smooth(world, sigma, sigma, wrap_cols=True)
    region = read_patch_umol(grids.grid_path(month, "region", cfg["region_step_monthly_deg"]))
    region = smooth_km(region, cfg["smooth_sigma_monthly_region_km"])
    return cut_layer(
        world,
        region,
        tiles_dir / month,
        cfg["global_max_zoom"],
        cfg["region_max_zoom_monthly"],
        cfg["feather_deg"],
        cfg["tile_size_px"],
    )


def main() -> None:
    cfg = load_config()["layers"]
    parser = argparse.ArgumentParser(description="Cut the NO2 grids into PNG map tiles")
    sub = parser.add_subparsers(dest="kind", required=True)
    annual = sub.add_parser("annual")
    annual.add_argument("--year", type=int, default=cfg["annual_year"])
    monthly = sub.add_parser("monthly")
    monthly.add_argument("--from", dest="first", default=cfg["first_month"])
    monthly.add_argument("--to", dest="last", default="9999-12")
    monthly.add_argument("--force", action="store_true", help="cut months that are already there")
    args = parser.parse_args()
    if args.kind == "annual":
        stats = cut_annual(cfg, args.year)
        print(f"{args.year}: {stats}")
    else:
        step = cfg["global_step_deg"]
        pattern = f"no2_mean_*_global_{grids.step_tag(step)}.tif"
        have = sorted(p.name.split("_")[2] for p in grids.GRID_DIR.glob(pattern))
        for month in have:
            if not re.fullmatch(r"\d{4}-\d{2}", month) or not args.first <= month <= args.last:
                continue
            if not grids.grid_path(month, "region", cfg["region_step_monthly_deg"]).exists():
                continue
            if (TILES_DIR / month).exists() and not args.force:
                continue
            print(f"{month}: {cut_month(cfg, month)}", flush=True)
    write_manifest(cfg)
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
