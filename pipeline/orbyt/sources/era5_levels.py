"""ERA5 wind at about 500 m above ground, the level the estimates use since M4.4.

    uv run python -m orbyt.sources.era5_levels --subject-id ph-us-xxxxxxxx
    uv run python -m orbyt.sources.era5_levels --us-region --years 2023 2024
    uv run python -m orbyt.sources.era5_levels --eu-region

The published catalogue uses wind at about 500 m above ground (PLAN.md 4.3 step 3). Earth
Engine only carries the 100 m wind, so this reads the ERA5 pressure-level data from the
Copernicus Climate Data Store
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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime
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


REPO_ROOT = Path(__file__).resolve().parents[3]
REGION_DIR = REPO_ROOT / "data" / "raw" / "era5_pl"


def region_path(name: str, year: int, quarter: int, raw_dir: Path = REGION_DIR) -> Path:
    return raw_dir / f"{name}_{year}-Q{quarter}.nc"


def region_box(points: list[tuple[float, float]], margin_deg: float = 0.5) -> list[float]:
    """CDS area [north, west, south, east] on the 0.25 degree grid, holding every point's cell."""
    cells = [_cell(lat, lon) for lat, lon in points]
    lats, lons = [c[0] for c in cells], [c[1] for c in cells]
    return [
        max(lats) + margin_deg,
        min(lons) - margin_deg,
        min(lats) - margin_deg,
        max(lons) + margin_deg,
    ]


def fetch_period(
    lat: float,
    lon: float,
    year: int,
    months: list[int],
    days: list[int],
    hours: list[int],
    target: Path,
    cfg: dict,
    area: list[float] | None = None,
    levels_hpa: list[int] | None = None,
) -> Path:
    """Download u and v on the pressure levels for the cell around the point.

    The request is the product of the given months, days and hours, so a quarter holds a few
    thousand fields. The CDS refuses a whole year of 14 levels as too large ("cost limits
    exceeded"), and a request spends minutes in the queue, so the period is a quarter.
    ``area`` replaces the one cell with a box ([north, west, south, east]). The CDS charges by
    the number of fields, not the area, so one box for many plants costs about as much queue
    time as one plant (M4.4: about 1.5 h per request).
    """
    if target.exists():
        return target
    import cdsapi

    clat, clon = _cell(lat, lon)
    request = {
        "product_type": ["reanalysis"],
        "variable": ["u_component_of_wind", "v_component_of_wind"],
        "pressure_level": [str(p) for p in (levels_hpa or cfg["levels_hpa"])],
        "year": [str(year)],
        "month": [f"{m:02d}" for m in sorted(set(months))],
        "day": [f"{d:02d}" for d in sorted(set(days))],
        "time": [f"{h:02d}:00" for h in sorted(set(hours))],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": area or [clat + 0.25, clon - 0.25, clat - 0.25, clon + 0.25],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    for attempt in range(cfg["reject_retries"]):
        try:
            cdsapi.Client(quiet=True).retrieve(cfg["dataset"], request, str(tmp))
            break
        except Exception as exc:  # the CDS rejects when too many requests are queued
            if "queued requests" not in str(exc) or attempt == cfg["reject_retries"] - 1:
                raise
            time.sleep(cfg["reject_wait_s"])
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


def region_covers(path: Path, lat: float, lon: float, stamps: list[datetime]) -> bool:
    """True when a regional file holds the point's cell and every hour asked for."""
    import xarray as xr

    clat, clon = _cell(lat, lon)
    ds = xr.open_dataset(path, engine="h5netcdf")
    try:
        lats, lons = ds["latitude"].values, ds["longitude"].values
        if not (np.isclose(lats, clat).any() and np.isclose(lons, clon).any()):
            return False
        tdim = "valid_time" if "valid_time" in ds.dims else "time"
        have = set(ds[tdim].values.astype("datetime64[s]").astype("int64").tolist())
    finally:
        ds.close()
    need = {int(s.timestamp()) for s in stamps}
    return need <= have


def fetch_region(
    name: str,
    points: list[tuple[float, float]],
    hours: list[int],
    year: int,
    quarter: int,
    cfg: dict,
    raw_dir: Path = REGION_DIR,
    months: list[int] | None = None,
    levels_hpa: list[int] | None = None,
) -> Path:
    """One CDS request for a quarter, every day, the given hours, over a box around the points.

    ``months`` limits the request to some months of the quarter (a quarter not yet over), and
    ``levels_hpa`` replaces the configured levels.
    """
    months = months or [3 * (quarter - 1) + m for m in (1, 2, 3)]
    lat, lon = points[0]
    return fetch_period(
        lat,
        lon,
        year,
        months,
        list(range(1, 32)),
        hours,
        region_path(name, year, quarter, raw_dir),
        cfg,
        area=region_box(points),
        levels_hpa=levels_hpa,
    )


def region_holds_cell(path: Path, lat: float, lon: float) -> bool:
    """True when a regional file holds the point's cell, whatever hours it has."""
    import xarray as xr

    clat, clon = _cell(lat, lon)
    ds = xr.open_dataset(path, engine="h5netcdf")
    try:
        return bool(
            np.isclose(ds["latitude"].values, clat).any()
            and np.isclose(ds["longitude"].values, clon).any()
        )
    finally:
        ds.close()


def winds_500m(
    subject_id: str, out_dir: Path | None = None, log=print, region_only: bool = False
) -> Path:
    """Write ``wind-500m.json`` for a subject that already has ``wind.json``.

    ``region_only`` reads the regional files only: a quarter with no file holding the cell, or an
    hour a file does not hold, gives that day no wind (dropped as ``no_wind``), and nothing is
    asked of the CDS for the one subject.
    """
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
    by_quarter: dict[tuple[int, int], list[datetime]] = {}
    for w in base:
        stamp = datetime.fromisoformat(w.era5_hour_utc.replace("Z", "+00:00"))
        by_quarter.setdefault((stamp.year, (stamp.month - 1) // 3 + 1), []).append(stamp)
    jobs = sorted(by_quarter.items())

    def get_quarter(job: tuple[tuple[int, int], list[datetime]]) -> Path | None:
        (year, quarter), stamps = job
        regions = sorted(REGION_DIR.glob(f"*_{year}-Q{quarter}.nc"))
        for region in regions:
            if region_covers(region, subject.lat, subject.lon, stamps):
                log(f"{year} Q{quarter}: from {region.name}")
                return region
        if region_only:
            for region in regions:
                if region_holds_cell(region, subject.lat, subject.lon):
                    log(f"{year} Q{quarter}: from {region.name}, some hours missing")
                    return region
            log(f"{year} Q{quarter}: no regional file, {len(stamps)} days without wind")
            return None
        path = out_dir / subject_id / f"era5_pl_{year}-Q{quarter}.nc"
        log(f"{year} Q{quarter}: {len(stamps)} hours from the CDS")
        return fetch_period(
            subject.lat,
            subject.lon,
            year,
            [s.month for s in stamps],
            [s.day for s in stamps],
            [s.hour for s in stamps],
            path,
            cfg,
        )

    # The CDS queue, not the size of a request, sets the time, so quarters go in parallel.
    with ThreadPoolExecutor(max_workers=cfg["max_parallel"]) as pool:
        paths = list(pool.map(get_quarter, jobs))
    profiles: dict[int, np.ndarray] = {}
    levels = np.array([])
    for path in paths:
        if path is None:
            continue
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


def fetch_us_region(years: list[int], log=print) -> list[Path]:
    """Every quarter of the given years over a box around the US validation plants.

    The hours are the ERA5 hours that the plants' 100 m winds use (18 to 21 UTC in M4.3).
    One request per quarter instead of one per plant and quarter: 8 requests for 2023 and 2024
    instead of 264, with the same data.
    """
    import json

    from orbyt.modules.pollution_hunter import extract, validation_set

    plants = json.loads(validation_set.PLANTS_JSON.read_text(encoding="utf-8"))
    points = [(p["lat"], p["lon"]) for p in plants]
    hours: set[int] = set()
    for p in plants:
        for w in era5.read_winds(era5.wind_path(extract.INTERIM_DIR, p["subject_id"])):
            hours.add(int(w.era5_hour_utc[11:13]))
    cfg = load_config()["wind"]["pressure_levels"]
    log(f"box {region_box(points)}, hours {sorted(hours)}")
    out = []
    for year in years:
        for quarter in (1, 2, 3, 4):
            t0 = time.time()
            out.append(fetch_region("us", points, sorted(hours), year, quarter, cfg))
            log(f"{year} Q{quarter}: {out[-1].name} ({(time.time() - t0) / 60:.0f} min)")
    return out


def eu_quarters(
    first_day: date, last_month: date, first_years: list[int]
) -> list[tuple[int, int, list[int]]]:
    """(year, quarter, months) from ``first_day``'s month to ``last_month``, both included.

    Quarters of ``first_years`` (the register years) come first, so the calendar-year estimates
    can be made before the rolling windows have all their wind.
    """
    out: dict[tuple[int, int], list[int]] = {}
    k = first_day.year * 12 + first_day.month - 1
    end = last_month.year * 12 + last_month.month - 1
    while k <= end:
        y, m = divmod(k, 12)
        out.setdefault((y, m // 3 + 1), []).append(m + 1)
        k += 1
    keys = sorted(out, key=lambda q: (q[0] not in first_years, q))
    return [(y, q, out[(y, q)]) for y, q in keys]


def fetch_eu_region(log=print) -> list[Path]:
    """Every quarter of the European period over one box around the European subjects.

    The hours are the ERA5 hours that the subjects' 100 m winds use. The period runs from
    ``europe.first_day`` to the last complete month of their data, the end of the last rolling
    window. Days after it get no 500 m wind, and no estimate uses them.
    """
    import json

    from orbyt.modules.pollution_hunter import eu_set, extract

    subs = json.loads(eu_set.SUBJECTS_JSON.read_text(encoding="utf-8"))
    points, hours, last_day = [], set(), date.min
    for s in subs:
        points.append((s["lat"], s["lon"]))
        for w in era5.read_winds(era5.wind_path(extract.INTERIM_DIR, s["subject_id"])):
            hours.add(int(w.era5_hour_utc[11:13]))
            last_day = max(last_day, date.fromisoformat(w.day))
    ecfg = load_config()["europe"]
    first_day = date.fromisoformat(ecfg["first_day"])
    k = last_day.year * 12 + last_day.month - 2  # the month before the last day's month
    last_month = date(k // 12, k % 12 + 1, 1)
    cfg = load_config()["wind"]["pressure_levels"]
    quarters = eu_quarters(first_day, last_month, ecfg["register_years"])
    box = region_box(points)
    log(f"box {box}, hours {sorted(hours)}, {len(quarters)} quarters to {last_month}")
    out = []
    for year, quarter, months in quarters:
        t0 = time.time()
        out.append(
            fetch_region(
                "eu",
                points,
                sorted(hours),
                year,
                quarter,
                cfg,
                months=months,
                levels_hpa=cfg["eu_levels_hpa"],
            )
        )
        log(f"{year} Q{quarter}: {out[-1].name} ({(time.time() - t0) / 60:.0f} min)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="ERA5 wind at about 500 m, per day")
    parser.add_argument("--subject-id")
    parser.add_argument("--us-region", action="store_true", help="fetch the US box by quarter")
    parser.add_argument("--eu-region", action="store_true", help="fetch the Europe box by quarter")
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024])
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.eu_region:
        fetch_eu_region()
    elif args.us_region:
        fetch_us_region(args.years)
    elif args.subject_id:
        print(f"wrote {winds_500m(args.subject_id, args.out_dir)}")
    else:
        parser.error("give --subject-id, --us-region or --eu-region")


if __name__ == "__main__":
    main()
