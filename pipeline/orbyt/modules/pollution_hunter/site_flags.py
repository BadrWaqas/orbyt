"""Coast and terrain flags for the confidence grade (PLAN.md 4.5 and 4.8, M5.3).

    uv run python -m orbyt.modules.pollution_hunter.site_flags

PLAN.md 4.5 asks to flag, not fail, a site when the elevation varies by more than 300 m within
30 km or the sea is within 15 km: wind and surface brightness are less reliable there. A flag
lowers the grade (core/verdict.py) and nothing else. Both numbers are written next to the
subject list in ``eu_site_flags.json``.

- Distance to the sea: Natural Earth 1:10m coastline, public domain, the nearest point of any
  coastline segment.
- Elevation range: Copernicus DEM GLO30 in Earth Engine, the highest minus the lowest land cell
  (water body mask 0) inside the circle, read on a 250 m grid.
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import gee

SOURCE = "Natural Earth 1:10m coastline, Copernicus DEM GLO30"
COAST_URL = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip"
RAW_DIR = gee.REPO_ROOT / "data" / "raw" / "coast"
SHAPEFILE = RAW_DIR / "ne_10m_coastline.shp"
FLAGS_JSON = Path(__file__).parent / "eu_site_flags.json"
KM_PER_DEG = 111.195
# The Earth Engine asset COPERNICUS/DEM/GLO30 is deprecated in favour of this one.
DEM_COLLECTION = "COPERNICUS/DEM/GLO30_2024_1"
# Only coastline within this box (degrees) of the site is measured. Far beyond 15 km anyway.
SEARCH_DEG = 1.5


def download_coast(raw_dir: Path = RAW_DIR) -> Path:
    """Fetch and unpack the coastline shapefile once. Returns the .shp path."""
    shp = raw_dir / SHAPEFILE.name
    if shp.exists():
        return shp
    with urllib.request.urlopen(COAST_URL, timeout=120) as resp:  # noqa: S310 (fixed https URL)
        data = resp.read()
    raw_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(raw_dir)
    return shp


def distance_to_line_km(lat0: float, lon0: float, lats: np.ndarray, lons: np.ndarray) -> float:
    """Shortest distance from a point to a polyline, in km, on a local flat projection.

    Accurate to a fraction of a percent within the 165 km search box, which is all that is used.
    """
    x = (np.asarray(lons) - lon0) * np.cos(np.radians(lat0)) * KM_PER_DEG
    y = (np.asarray(lats) - lat0) * KM_PER_DEG
    if len(x) == 1:
        return float(np.hypot(x[0], y[0]))
    ax, ay, bx, by = x[:-1], y[:-1], x[1:], y[1:]
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = np.where(seg2 > 0, np.clip(-(ax * dx + ay * dy) / np.where(seg2 > 0, seg2, 1), 0, 1), 0)
    return float(np.min(np.hypot(ax + t * dx, ay + t * dy)))


def coast_distance_km(lat0: float, lon0: float, shp: Path = SHAPEFILE) -> float | None:
    """Distance to the nearest coastline, or None when none lies within the search box."""
    import shapefile

    reader = shapefile.Reader(str(shp))
    lon_pad = SEARCH_DEG / max(np.cos(np.radians(lat0)), 0.05)
    best: float | None = None
    for shape in reader.iterShapes():
        x0, y0, x1, y1 = shape.bbox
        if x1 < lon0 - lon_pad or x0 > lon0 + lon_pad or y1 < lat0 - SEARCH_DEG:
            continue
        if y0 > lat0 + SEARCH_DEG:
            continue
        pts = np.asarray(shape.points, dtype=float)
        starts = [*list(shape.parts), len(pts)]
        for a, b in zip(starts[:-1], starts[1:], strict=True):
            d = distance_to_line_km(lat0, lon0, pts[a:b, 1], pts[a:b, 0])
            best = d if best is None else min(best, d)
    return best


def terrain_range_m(lat: float, lon: float, radius_km: float) -> dict[str, float | None]:
    """Lowest, highest and range of the land elevation within ``radius_km``, from the DEM."""
    import ee

    dem = ee.ImageCollection(DEM_COLLECTION).select(["DEM", "WBM"]).mosaic()
    land = dem.select("DEM").updateMask(dem.select("WBM").eq(0))
    region = ee.Geometry.Point([lon, lat]).buffer(radius_km * 1000)
    stats = land.reduceRegion(
        reducer=ee.Reducer.minMax(), geometry=region, scale=250, maxPixels=int(1e9)
    ).getInfo()
    lo, hi = stats.get("DEM_min"), stats.get("DEM_max")
    return {
        "min_m": lo,
        "max_m": hi,
        "range_m": None if lo is None or hi is None else float(hi - lo),
    }


def flags_for(
    coast_km: float | None, range_m: float | None, cfg: dict[str, Any] | None = None
) -> list[str]:
    """The flags a site carries: ``coast`` and/or ``terrain``. A missing number sets no flag."""
    g = cfg or load_config()["verdict"]["grade"]
    flags = []
    if coast_km is not None and coast_km <= g["coast_km"]:
        flags.append("coast")
    if range_m is not None and range_m > g["terrain_range_m"]:
        flags.append("terrain")
    return flags


def compute(subjects: list[dict], log=print) -> dict[str, dict[str, Any]]:
    cfg = load_config()["verdict"]["grade"]
    shp = download_coast()
    gee.init()
    out = {}
    for s in subjects:
        coast = coast_distance_km(s["lat"], s["lon"], shp)
        terr = terrain_range_m(s["lat"], s["lon"], cfg["terrain_radius_km"])
        out[s["subject_id"]] = {
            "coast_km": None if coast is None else round(coast, 1),
            "elevation_min_m": terr["min_m"],
            "elevation_max_m": terr["max_m"],
            "elevation_range_m": None if terr["range_m"] is None else round(terr["range_m"]),
            "flags": flags_for(coast, terr["range_m"], cfg),
        }
        log(f"{s['subject_id']} {ascii(s['city'])}: {out[s['subject_id']]}")
    return out


def main() -> None:
    from orbyt.modules.pollution_hunter import eu_set

    parser = argparse.ArgumentParser(description="Coast and terrain flags for the subjects")
    parser.add_argument("--out", type=Path, default=FLAGS_JSON)
    args = parser.parse_args()
    subjects = json.loads(eu_set.SUBJECTS_JSON.read_text(encoding="utf-8"))
    doc = {
        "source": SOURCE,
        "rules": load_config()["verdict"]["grade"],
        "sites": compute(subjects),
    }
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
