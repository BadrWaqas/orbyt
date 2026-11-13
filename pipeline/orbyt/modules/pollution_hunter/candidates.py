"""Candidate ranking with the isolation rule (PLAN.md 4.5), extended in M3.6 prep.

    uv run python -m orbyt.modules.pollution_hunter.candidates --year 2024

A candidate is a footprint: a facility plus every register facility within 20 km, with the
reported NOx summed. It is isolated when four checks pass:

  sources   no other register source above a quarter of the footprint total, 20 to 60 km away
  city_near no city of 200,000 or more within 30 km (the plan's rule)
  city_far  no city of 500,000 or more within 100 km (added after the Belchatow review)
  hotspot   no other local maximum in the annual mean NO2 map, 20 to 100 km away, that stands
            above the background by a quarter of the facility's own enhancement

The hotspot check is the one that reads the satellite. The city checks are a cheap prefilter and
do not need the map. Every constant is in config.yaml with its source.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from scipy.ndimage import maximum_filter

from orbyt.core.geo import haversine_km, offsets_km
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import cities as cities_src
from orbyt.sources import eea, gee

NO2_MAP = gee.RAW_DIR / "no2_annual_mean_2024_0p1deg.tif"
OUT_PARQUET = eea.WAREHOUSE_DIR / "candidates.parquet"
MOL_TO_UMOL = 1e6


@dataclass(frozen=True)
class Window:
    """A crop of the annual mean map: columns in micromol per m2 on an ascending lat/lon grid."""

    field: np.ndarray  # [lat, lon], NaN = no data
    lats: np.ndarray
    lons: np.ndarray


def read_window(tif: Path, lat0: float, lon0: float, half_km: float) -> Window:
    """Crop of the annual mean map around a point, ``half_km`` each way, south row first."""
    import rasterio
    from rasterio.windows import from_bounds

    dlat = np.degrees(half_km / 6371.0088)
    dlon = dlat / max(np.cos(np.radians(lat0)), 0.05)
    with rasterio.open(tif) as src:
        win = from_bounds(lon0 - dlon, lat0 - dlat, lon0 + dlon, lat0 + dlat, src.transform)
        win = win.round_offsets().round_lengths()
        data = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        tr = src.window_transform(win)
    rows, cols = np.mgrid[0 : data.shape[0], 0 : data.shape[1]]
    lons = tr.c + (cols[0] + 0.5) * tr.a
    lats = tr.f + (rows[:, 0] + 0.5) * tr.e
    data = data * MOL_TO_UMOL
    return Window(data[::-1], lats[::-1], lons)


def hotspot_check(win: Window, lat0: float, lon0: float, cfg: dict[str, Any]) -> dict[str, Any]:
    """Own enhancement and the strongest other hotspot in the ring, in micromol per m2.

    Background is the median of an outer ring. Own enhancement is the highest cell within
    ``own_km``. A hotspot is a cell that is the maximum of its ``peak_cells`` square, between
    ``min_km`` and ``max_km`` away, and not part of the plume ridge of the facility itself:
    a maximum needs its own peak, so a ridge that falls away from the facility is not counted.
    """
    east, north = offsets_km(lat0, lon0, win.lats[:, None], win.lons[None, :])
    dist = np.hypot(east, north)
    ring = (dist >= cfg["background_km"][0]) & (dist <= cfg["background_km"][1])
    ok = np.isfinite(win.field)
    if (ring & ok).sum() < 20:
        return {"background": None, "noise": None, "own": None, "other": None}
    background = float(np.median(win.field[ring & ok]))
    noise = float(1.4826 * np.median(np.abs(win.field[ring & ok] - background)))
    own_cells = (dist <= cfg["own_km"]) & ok
    own = float(win.field[own_cells].max() - background) if own_cells.any() else None
    filled = np.where(ok, win.field, -np.inf)
    is_peak = (filled == maximum_filter(filled, size=cfg["peak_cells"], mode="nearest")) & ok
    in_ring = (dist >= cfg["min_km"]) & (dist <= cfg["max_km"])
    cand = np.argwhere(is_peak & in_ring)
    best, where = 0.0, None
    for i, j in cand:
        enh = float(win.field[i, j] - background)
        if enh > best:
            best, where = enh, (float(win.lats[i]), float(win.lons[j]))
    return {
        "background": background,
        "noise": noise,
        "own": own,
        "other": best if where else 0.0,
        "other_at": where,
    }


def footprints(rows: list[dict], radius_km: float) -> list[list[int]]:
    """Group facilities that lie within ``radius_km`` of each other (chains merge)."""
    n = len(rows)
    lat = np.array([r["lat"] for r in rows])
    lon = np.array([r["lon"] for r in rows])
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        near = np.where(haversine_km(lat[i], lon[i], lat[i + 1 :], lon[i + 1 :]) <= radius_km)[0]
        for k in near + i + 1:
            parent[find(int(k))] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _ratio(num: float | None, den: float | None) -> float | None:
    return None if num is None or not den or den <= 0 else num / den


def score(
    group: list[int],
    rows: list[dict],
    cities: cities_src.Cities,
    win: Window | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Isolation checks for one footprint. The anchor is its largest facility."""
    members = sorted(group, key=lambda i: -rows[i]["release_t"])
    anchor = rows[members[0]]
    lat0, lon0 = anchor["lat"], anchor["lon"]
    total = float(sum(rows[i]["release_t"] for i in members))
    lat = np.array([r["lat"] for r in rows])
    lon = np.array([r["lon"] for r in rows])
    dist = haversine_km(lat0, lon0, lat, lon)
    member_set = set(members)
    neighbours = [
        i
        for i in range(len(rows))
        if i not in member_set
        and cfg["source_min_km"] <= dist[i] <= cfg["source_max_km"]
        and rows[i]["release_t"] > cfg["source_frac"] * total
    ]
    near = cities.near(lat0, lon0, cfg["city_near_km"], cfg["city_near_pop"])
    far = cities.near(lat0, lon0, cfg["city_far_km"], cfg["city_far_pop"])
    hot = (
        hotspot_check(win, lat0, lon0, cfg["hotspot"])
        if win is not None
        else {"background": None, "noise": None, "own": None, "other": None}
    )
    ratio = _ratio(hot.get("other"), hot.get("own"))
    floor = cfg["hotspot"]["noise_sigmas"] * (hot["noise"] or 0.0)
    flags = {
        "sources": bool(neighbours),
        "city_near": bool(near),
        "city_far": bool(far),
        # A hotspot must stand above the scatter of the map as well as above a quarter of ours.
        "hotspot": ratio is not None and ratio >= cfg["hotspot"]["frac"] and hot["other"] >= floor,
    }
    return {
        "subject_anchor": anchor["register_id"],
        "name": anchor["name"],
        "city": anchor["city"],
        "country": anchor["country"],
        "sector": anchor["sector"],
        "lat": lat0,
        "lon": lon0,
        "year": anchor["year"],
        "n_facilities": len(members),
        "reported_t": total,
        "flag_sources": flags["sources"],
        "flag_city_near": flags["city_near"],
        "flag_city_far": flags["city_far"],
        "flag_hotspot": flags["hotspot"],
        "isolated": not any(flags.values()),
        "nearest_big_city": (far[0]["name"] + f" ({far[0]['distance_km']:.0f} km)") if far else "",
        "biggest_neighbour_t": max((rows[i]["release_t"] for i in neighbours), default=0.0),
        "map_noise_umol_m2": hot.get("noise"),
        "own_detectable": hot.get("own") is not None and hot["own"] >= floor,
        "own_enh_umol_m2": hot.get("own"),
        "other_enh_umol_m2": hot.get("other"),
        "hotspot_ratio": ratio,
    }


def rank(
    con: duckdb.DuckDBPyConnection,
    year: int,
    cfg: dict[str, Any] | None = None,
    tif: Path = NO2_MAP,
    cities: cities_src.Cities | None = None,
    log=print,
) -> list[dict]:
    """Isolation scores for every footprint of at least ``min_footprint_t``, largest first."""
    cfg = cfg or load_config()["candidates"]
    cities = cities or cities_src.load_cities()
    rows = eea.top_reporters(con, year, 100_000)
    groups = footprints(rows, cfg["footprint_km"])
    big = [g for g in groups if sum(rows[i]["release_t"] for i in g) >= cfg["min_footprint_t"]]
    log(
        f"{len(rows)} facilities with coordinates, {len(groups)} footprints, {len(big)} of at "
        f"least {cfg['min_footprint_t']:,.0f} t"
    )
    out = []
    for g in big:
        anchor = rows[max(g, key=lambda i: rows[i]["release_t"])]
        win = read_window(tif, anchor["lat"], anchor["lon"], cfg["hotspot"]["window_km"])
        out.append(score(g, rows, cities, win, cfg))
    out.sort(key=lambda r: -r["reported_t"])
    return out


def write_parquet(results: list[dict], path: Path = OUT_PARQUET) -> Path:
    """Write the scores as Parquet through DuckDB (no pandas in this project)."""
    import json
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        lines = Path(tmp) / "rows.jsonl"
        lines.write_text("\n".join(json.dumps(r, default=str) for r in results), encoding="utf-8")
        src = str(lines).replace("\\", "/")
        dst = str(path).replace("\\", "/")
        con = duckdb.connect()
        con.execute(
            f"copy (select * from read_json_auto('{src}', sample_size=-1)) "
            f"to '{dst}' (format parquet)"
        )
        con.close()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank candidate facilities by isolation")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()
    cities_src.download()
    con = duckdb.connect(str(eea.WAREHOUSE_DIR / "orbyt.duckdb"), read_only=True)
    results = rank(con, args.year)
    print(f"wrote {write_parquet(results)}")
    iso = [r for r in results if r["isolated"]]
    print(f"{len(iso)} of {len(results)} footprints are isolated")
    for r in results[: args.top]:
        keys = ("flag_sources", "flag_city_near", "flag_city_far", "flag_hotspot")
        flags = ",".join(k[5:] for k in keys if r[k])
        print(
            f"{r['reported_t']:8,.0f} t {r['country'][:3]} {ascii(r['city'])[:18]:18s} "
            f"{'ISOLATED' if r['isolated'] else flags}"
        )


if __name__ == "__main__":
    main()
