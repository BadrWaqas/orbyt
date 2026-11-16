"""Rolling 12-month windows of the satellite estimate (M5.2, PLAN.md 6 and 2.4).

A window is [start, end) of whole months. The estimate for a window keeps the cached days that
fall inside it and runs the same math as observe.py (same grids, background, fan, fit, gates,
bootstrap), so a window that is a calendar year gives the number ``estimate-<year>.json`` has.
The daily flux of each cached day is computed once and sliced per window.

Windows start at ``europe.first_day`` (July 2022, one processor generation) and step by one
month. The first window ends 12 months after it. The last one ends at the start of the first
month that is not complete in the data. Only a window that is a calendar year can be paired with
a register value, because the register reports calendar years.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from orbyt.modules.pollution_hunter import extract, observe
from orbyt.modules.pollution_hunter.config import load_config, wind_level
from orbyt.sources import era5

MONTHS = 12


def add_months(d: date, n: int) -> date:
    """The first of the month ``n`` months after ``d``'s month. ``d`` must be a first."""
    k = d.year * 12 + (d.month - 1) + n
    return date(k // 12, k % 12 + 1, 1)


def first_incomplete_month(data_end: date) -> date:
    """First day of the first month not fully covered by data that runs to ``data_end``."""
    nxt = date(data_end.year + (data_end.month == 12), data_end.month % 12 + 1, 1)
    last_day_of_month = (nxt - data_end).days == 1
    return nxt if last_day_of_month else date(data_end.year, data_end.month, 1)


def rolling_windows(
    first_day: date, data_end: date, months: int = MONTHS
) -> list[tuple[date, date]]:
    """Windows [start, end) of ``months`` whole months, stepped by one month.

    The first starts at ``first_day`` (a first of the month). A window is kept when it ends on or
    before the first incomplete month of the data.
    """
    cut = first_incomplete_month(data_end)
    out = []
    start = first_day
    while add_months(start, months) <= cut:
        out.append((start, add_months(start, months)))
        start = add_months(start, 1)
    return out


def is_calendar_year(start: date, end: date) -> int | None:
    """The year when the window is exactly January to December of one year."""
    if start.month == 1 and start.day == 1 and end == date(start.year + 1, 1, 1):
        return start.year
    return None


def window_label(start: date, end: date) -> str:
    last = add_months(end, -1)
    return f"{start:%b %Y} to {last:%b %Y}"


def estimate_windows(
    subject_id: str,
    windows: list[tuple[date, date]],
    out_dir: Path | None = None,
    level: str | None = None,
    log=print,
) -> dict[str, Any]:
    """The estimate of every window for one subject, from cached patches and wind."""
    level = level or wind_level()
    out_dir = out_dir or extract.INTERIM_DIR
    cfg = load_config()
    ocfg = cfg["observe"]
    subject = extract.load_subject(subject_id)
    winds = era5.read_winds(era5.wind_path(out_dir, subject_id, level))
    kept, dropped = observe.select_days(winds, cfg["wind"]["min_speed_ms"])
    t_hours, yr_km = observe.grid(ocfg["travel_hours"]), observe.grid(ocfg["crosswind_km"])
    flux = observe.daily_fluxes(subject, kept, out_dir / subject_id, t_hours, yr_km, ocfg)
    log(f"{subject_id}: flux of {len(kept)} usable days of {len(winds)} cached ({dropped})")
    rows = []
    for start, end in windows:
        a, b = start.isoformat(), end.isoformat()
        cached = sum(a <= w.day < b for w in winds)
        idx = [i for i, d in enumerate(kept) if a <= d.day < b]
        est, gates = (None, ["no_fit"])
        if idx:
            speeds = [float(kept[i].speed_ms) for i in idx]
            try:
                est, gates = observe.run_estimate(flux[idx], t_hours, yr_km, speeds, ocfg)
            except (ValueError, RuntimeError, FloatingPointError):
                est, gates = None, ["no_fit"]
        rows.append(
            {
                "start": a,
                "end": b,
                "label": window_label(start, end),
                "calendar_year": is_calendar_year(start, end),
                "n_days_cached": cached,
                "n_days": len(idx),
                "nox_t_yr": None if est is None else est["nox_t_yr"],
                "lo": None if est is None else est["ci95"][0],
                "hi": None if est is None else est["ci95"][1],
                "lifetime_h": None if est is None else est["tau"],
                "t0_h": None if est is None else est["t0"],
                "r2": None if est is None else est["r2"],
                "gates_failed": gates,
            }
        )
    return {
        "subject_id": subject_id,
        "method": cfg["method_version"],
        "wind_level": level,
        "months": MONTHS,
        "constants": {
            k: ocfg[k] for k in ("nox_to_no2", "amf_correction", "n_boot", "seed", "min_days")
        },
        "windows": rows,
    }


def rolling_name(level: str | None = None) -> str:
    level = level or wind_level()
    return "rolling.json" if level == "100m" else f"rolling-{level}.json"


def write_rolling(doc: dict[str, Any], out_dir: Path | None = None) -> Path:
    out_dir = out_dir or extract.INTERIM_DIR
    path = out_dir / doc["subject_id"] / rolling_name(doc["wind_level"])
    path.write_text(json.dumps(observe._clean(doc), indent=1) + "\n", encoding="utf-8")
    return path


def read_rolling(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def passing(row: dict[str, Any]) -> bool:
    """A window with an estimate that passes every gate."""
    return row["nox_t_yr"] is not None and not row["gates_failed"]


def summarise(doc: dict[str, Any]) -> dict[str, int]:
    rows = doc["windows"]
    return {
        "windows": len(rows),
        "with_estimate": sum(r["nox_t_yr"] is not None for r in rows),
        "pass_all_gates": sum(passing(r) for r in rows),
        "median_days": int(np.median([r["n_days"] for r in rows])) if rows else 0,
    }
