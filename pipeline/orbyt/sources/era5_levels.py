"""ERA5 wind at about 500 m above ground, for the wind-level test (PLAN.md 4.3 step 3, V4).

    uv run python -m orbyt.sources.era5_levels --subject-id ph-us-xxxxxxxx

The published catalogue uses wind at about 500 m above ground. Earth Engine only carries the
100 m wind, so this reads the ERA5 pressure-level data from the Copernicus Climate Data Store
(needs ``~/.cdsapirc``). The wind is taken at the pressure surface ``offset_hpa`` below the
surface pressure (PLAN.md: surface pressure minus about 55 hPa), linearly interpolated in
pressure between the stored levels. Surface pressure comes from the same Earth Engine ERA5 hour
as the 100 m wind.

Same days, same ERA5 hours and same cell as ``wind.json``, so the two levels differ only in
height. The result is ``wind-500m.json`` in the format of ``wind.json``.

Levels below the ground are extrapolated by ERA5. The target level is about 55 hPa above the
surface, and the stored levels are 25 hPa apart, so at most one bracketing level can be below
ground. This is noted rather than corrected.
"""

from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import era5

LEVEL = "500m"


def interp_to_pressure(
    levels_hpa: np.ndarray, values: np.ndarray, p_target_hpa: float
) -> float | None:
    """Linear interpolation in pressure of one profile. None when the profile has a gap.

    ``levels_hpa`` need not be sorted. A target outside the stored levels takes the nearest one.
    """
    levels = np.asarray(levels_hpa, dtype=float)
    vals = np.asarray(values, dtype=float)
    if np.isnan(vals).any() or not math.isfinite(p_target_hpa):
        return None
    order = np.argsort(levels)
    return float(np.interp(p_target_hpa, levels[order], vals[order]))


def target_pressure_hpa(surface_pressure_pa: float, offset_hpa: float) -> float:
    return surface_pressure_pa / 100.0 - offset_hpa


def _cell(lat: float, lon: float) -> tuple[float, float]:
    """Centre of the 0.25 degree ERA5 cell nearest the point."""
    return round(lat * 4) / 4, round(lon * 4) / 4


def fetch_month(
    lat: float,
    lon: float,
    year: int,
    month: int,
    days: list[int],
    hours: list[int],
    target: Path,
    cfg: dict,
) -> Path:
    """Download u and v on the pressure levels for the cell around the point, for given days.

    One request per month with only the days and hours that are needed: the CDS refuses a
    whole year of 14 levels as too large ("cost limits exceeded").
    """
    if target.exists():
        return target
    import cdsapi

    clat, clon = _cell(lat, lon)
    request = {
        "product_type": ["reanalysis"],
        "variable": ["u_component_of_wind", "v_component_of_wind"],
        "pressure_level": [str(p) for p in cfg["levels_hpa"]],
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{d:02d}" for d in sorted(set(days))],
        "time": [f"{h:02d}:00" for h in sorted(set(hours))],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [clat + 0.25, clon - 0.25, clat - 0.25, clon + 0.25],
    }
    tmp = target.with_suffix(".part")
    cdsapi.Client(quiet=True).retrieve(cfg["dataset"], request, str(tmp))
    tmp.replace(target)
    return target


def read_profiles(path: Path, lat: float, lon: float) -> tuple[dict[int, np.ndarray], np.ndarray]:
    """{hour start in ms: array (2, n_levels) of u and v}, and the levels in hPa."""
    import xarray as xr

    ds = xr.open_dataset(path, engine="h5netcdf")
    try:
        clat, clon = _cell(lat, lon)
        sel = ds.sel(latitude=clat, longitude=clon, method="nearest")
        tdim = "valid_time" if "valid_time" in sel.dims else "time"
        ldim = "pressure_level" if "pressure_level" in sel.dims else "level"
        sel = sel.transpose(tdim, ldim)
        times = sel[tdim].values.astype("datetime64[s]").astype("int64") * 1000
        u, v = sel["u"].values, sel["v"].values
        levels = sel[ldim].values.astype(float)
    finally:
        ds.close()
    return {int(t): np.stack([u[i], v[i]]) for i, t in enumerate(times)}, levels


def winds_500m(subject_id: str, out_dir: Path | None = None, log=print) -> Path:
    """Write ``wind-500m.json`` for a subject that already has ``wind.json``."""
    from orbyt.modules.pollution_hunter import extract
    from orbyt.sources import gee

    out_dir = out_dir or extract.INTERIM_DIR
    wcfg = load_config()["wind"]
    cfg = wcfg["pressure_levels"]
    subject = extract.load_subject(subject_id)
    base = era5.read_winds(era5.wind_path(out_dir, subject_id))
    if not base:
        raise SystemExit(f"no 100 m wind for {subject_id}, run era5 first")

    def hour_ms(w: era5.DayWind) -> int:
        stamp = datetime.fromisoformat(w.era5_hour_utc.replace("Z", "+00:00"))
        return int(stamp.timestamp() * 1000)

    gee.init()
    sp = extract._retry(
        lambda: era5.sample_bands(
            subject.lat,
            subject.lon,
            [hour_ms(w) for w in base],
            ["surface_pressure", wcfg["u_band"]],
            cfg=wcfg,
        )
    )
    by_month: dict[tuple[int, int], list[datetime]] = {}
    for w in base:
        stamp = datetime.fromisoformat(w.era5_hour_utc.replace("Z", "+00:00"))
        by_month.setdefault((stamp.year, stamp.month), []).append(stamp)
    jobs = sorted(by_month.items())

    def get_month(job: tuple[tuple[int, int], list[datetime]]) -> Path:
        (year, month), stamps = job
        path = out_dir / subject_id / f"era5_pl_{year}-{month:02d}.nc"
        log(f"{year}-{month:02d}: {len(stamps)} hours from the CDS")
        return fetch_month(
            subject.lat,
            subject.lon,
            year,
            month,
            [s.day for s in stamps],
            [s.hour for s in stamps],
            path,
            cfg,
        )

    # The CDS queue, not the size of a request, sets the time, so months go in parallel.
    with ThreadPoolExecutor(max_workers=cfg["max_parallel"]) as pool:
        paths = list(pool.map(get_month, jobs))
    profiles: dict[int, np.ndarray] = {}
    levels = np.array([])
    for path in paths:
        prof, levels = read_profiles(path, subject.lat, subject.lon)
        profiles.update(prof)
    rows, extrapolated = [], 0
    for w in base:
        key = hour_ms(w)
        prof, s = profiles.get(key), sp.get(key)
        if prof is None or s is None:
            rows.append(replace(w, u_ms=None, v_ms=None, speed_ms=None, from_deg=None))
            continue
        p = target_pressure_hpa(s[0], cfg["offset_hpa"])
        extrapolated += p > levels.max() or p < levels.min()
        u = interp_to_pressure(levels, prof[0], p)
        v = interp_to_pressure(levels, prof[1], p)
        if u is None or v is None:
            rows.append(replace(w, u_ms=None, v_ms=None, speed_ms=None, from_deg=None))
            continue
        speed, from_deg = era5.wind_speed_and_from(u, v)
        rows.append(replace(w, u_ms=u, v_ms=v, speed_ms=speed, from_deg=from_deg))

    source = {
        "level": LEVEL,
        "collection": cfg["dataset"],
        "bands": ["u_component_of_wind", "v_component_of_wind"],
        "note": f"pressure surface {cfg['offset_hpa']} hPa below ERA5 surface pressure",
        "levels_hpa": [float(p) for p in levels],
    }
    path = era5.write_winds(
        era5.wind_path(out_dir, subject_id, LEVEL), subject_id, rows, wcfg, source
    )
    speeds = np.array([r.speed_ms for r in rows if r.speed_ms is not None])
    log(
        f"{len(rows)} days, {sum(r.speed_ms is None for r in rows)} without wind, "
        f"{extrapolated} outside the stored levels"
    )
    if len(speeds):
        log(f"wind speed m/s at ~500 m: median {np.median(speeds):.1f}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="ERA5 wind at about 500 m, per day")
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    print(f"wrote {winds_500m(args.subject_id, args.out_dir)}")


if __name__ == "__main__":
    main()
