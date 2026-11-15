"""Download the mean NO2 grids that the map layers are cut from (M6.2 and the finer annual layer).

Each period has two grids, both in mol/m2 and both read with bilinear resampling:

    global   the whole world at 0.1 degree
    region   Europe on a finer grid: 0.02 degree for the annual mean, 0.04 for a month

They are saved as GeoTIFF under ``data/raw/no2_grids``. A grid that is already there is skipped,
so a run that stopped can be started again. The Earth Engine cost of the first few grids is
measured and written to ``eecu_log.jsonl`` next to them (PLAN.md 3.3: measure before scaling).

    uv run python -m orbyt.modules.pollution_hunter.grids annual
    uv run python -m orbyt.modules.pollution_hunter.grids monthly --to 2026-10
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.extract import EecuMeter, _profiled
from orbyt.sources import gee

GRID_DIR = gee.RAW_DIR / "no2_grids"
EECU_LOG = "eecu_log.jsonl"
# A window of a year's mean on the fine grid takes up to a minute or two. A call that has not
# answered by then has lost its connection: it is dropped and the grid is tried again.
CALL_DEADLINE_S = 240
GRID_ATTEMPTS = 4
RETRY_WAIT_S = 15

Bounds = tuple[float, float, float, float]


def month_range(first: str, last: str) -> list[str]:
    """Every month from ``first`` to ``last``, both included, as ``YYYY-MM``."""
    y, m = (int(part) for part in first.split("-"))
    end = tuple(int(part) for part in last.split("-"))
    months = []
    while (y, m) <= end:
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def month_dates(month: str) -> tuple[str, str]:
    """First day of ``month`` and first day of the month after it, as ISO dates."""
    y, m = (int(part) for part in month.split("-"))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


def latest_complete_month(latest_image: str) -> str:
    """The last month that has images up to its final day, given the newest image's ISO date."""
    newest = date.fromisoformat(latest_image)
    first_of_next = (newest.replace(day=1) + timedelta(days=32)).replace(day=1)
    if newest + timedelta(days=1) == first_of_next:
        return f"{newest.year:04d}-{newest.month:02d}"
    before = newest.replace(day=1) - timedelta(days=1)
    return f"{before.year:04d}-{before.month:02d}"


def step_tag(step: float) -> str:
    return f"{step:g}".replace(".", "p") + "deg"


def grid_path(period: str, scope: str, step: float, grid_dir: Path = GRID_DIR) -> Path:
    """Where a grid lives. ``period`` is a year or a month, ``scope`` is global or region."""
    return grid_dir / f"no2_mean_{period}_{scope}_{step_tag(step)}.tif"


@dataclass(frozen=True)
class GridJob:
    period: str  # "2024" or "2024-06"
    scope: str  # "global" or "region"
    start: str
    end: str
    bounds: Bounds
    step: float

    def path(self, grid_dir: Path = GRID_DIR) -> Path:
        return grid_path(self.period, self.scope, self.step, grid_dir)


def annual_jobs(cfg: dict, year: int) -> list[GridJob]:
    """The annual layer's own grid: Europe, fine. Its global grid is the one from M1.2."""
    region = tuple(cfg["region_bounds_deg"])
    return [
        GridJob(
            str(year),
            "region",
            f"{year}-01-01",
            f"{year + 1}-01-01",
            region,
            cfg["region_step_annual_deg"],
        )
    ]


def monthly_jobs(cfg: dict, months: list[str]) -> list[GridJob]:
    region = tuple(cfg["region_bounds_deg"])
    jobs = []
    for month in months:
        start, end = month_dates(month)
        jobs.append(GridJob(month, "global", start, end, gee.WORLD, cfg["global_step_deg"]))
        jobs.append(GridJob(month, "region", start, end, region, cfg["region_step_monthly_deg"]))
    return jobs


def run(jobs: list[GridJob], measure_grids: int, chunk: int, grid_dir: Path = GRID_DIR) -> None:
    """Download every job that has no file yet. Logs the cost of the first ``measure_grids``."""
    todo = [job for job in jobs if not job.path(grid_dir).exists()]
    print(f"{len(jobs) - len(todo)} of {len(jobs)} grids already there, {len(todo)} to download")
    if not todo:
        return
    gee.init()
    gee.set_deadline(CALL_DEADLINE_S)
    grid_dir.mkdir(parents=True, exist_ok=True)
    measured_s = 0.0
    measured_px = 0
    for i, job in enumerate(todo, 1):
        started = time.monotonic()
        if gee.image_count(job.start, job.end) == 0:
            print(f"[{i}/{len(todo)}] {job.period} {job.scope}: no images, skipped")
            continue
        meter = EecuMeter() if i <= measure_grids else None
        cache = grid_dir / "chunks" / f"{job.period}_{job.scope}"
        for attempt in range(1, GRID_ATTEMPTS + 1):
            try:
                arr = gee.download_image(
                    gee.mean_no2(job.start, job.end, bilinear=True),
                    job.bounds,
                    job.step,
                    chunk=chunk,
                    cache_dir=cache,
                    cache_key=f"{gee.COLLECTION}|{gee.BAND}|mean|{job.start}|{job.end}|{job.step}",
                    around=lambda meter=meter: _profiled(meter),
                )
                break
            except Exception as exc:
                # A dropped connection or a call past its deadline. The windows that did arrive
                # are cached, so another pass only fetches the rest.
                print(f"{job.period} {job.scope}: attempt {attempt} failed, {exc!r}", flush=True)
                if attempt == GRID_ATTEMPTS:
                    raise
                time.sleep(RETRY_WAIT_S)
        gee.save_geotiff(arr, job.path(grid_dir), job.bounds, job.step)
        shutil.rmtree(cache, ignore_errors=True)  # the GeoTIFF is the copy that is kept
        line = f"[{i}/{len(todo)}] {job.period} {job.scope}: {time.monotonic() - started:.0f} s"
        if meter is not None:
            cost = meter.cost()
            measured_s += cost.estimated_s
            measured_px += arr.size
            left_px = sum(
                gee.grid_shape(j.bounds, j.step)[0] * gee.grid_shape(j.bounds, j.step)[1]
                for j in todo[i:]
            )
            record = {
                "period": job.period,
                "scope": job.scope,
                "step_deg": job.step,
                "pixels": int(arr.size),
                "eecu_seconds": round(cost.estimated_s, 1),
                "calls": cost.n_calls,
                "calls_with_profile": cost.n_found,
            }
            with (grid_dir / EECU_LOG).open("a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")
            per_px = measured_s / measured_px
            line += (
                f", {cost.estimated_s:.0f} EECU-s. "
                f"Rest of this run at that rate: {per_px * left_px / 3600:.2f} EECU-hours"
            )
        print(line, flush=True)


def main() -> None:
    cfg = load_config()["layers"]
    parser = argparse.ArgumentParser(description="Download the NO2 mean grids for the map layers")
    sub = parser.add_subparsers(dest="kind", required=True)
    annual = sub.add_parser("annual")
    annual.add_argument("--year", type=int, default=cfg["annual_year"])
    monthly = sub.add_parser("monthly")
    monthly.add_argument("--from", dest="first", default=cfg["first_month"])
    monthly.add_argument("--to", dest="last", default=None, help="default: last complete month")
    for p in (annual, monthly):
        p.add_argument("--chunk", type=int, default=600, help="window size in cells")
        p.add_argument("--measure", type=int, default=cfg["measure_grids"])
    args = parser.parse_args()
    if args.kind == "annual":
        jobs = annual_jobs(cfg, args.year)
    else:
        last = args.last
        if last is None:
            gee.init()
            last = latest_complete_month(gee.latest_image_date())
        jobs = monthly_jobs(cfg, month_range(args.first, last))
    run(jobs, args.measure, args.chunk)


if __name__ == "__main__":
    main()
