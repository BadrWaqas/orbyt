"""Pollution Hunter observation (M3.4): one facility's emission from cached patches and wind.

    uv run python -m orbyt.modules.pollution_hunter.observe --subject-id ph-eu-xxxxxxxx

Reads the cached NO2 patches and ``wind.json`` written by extract.py and era5.py, keeps the days
with wind of at least ``wind.min_speed_ms``, and runs the unchanged math from core_math.py. It
writes ``estimate.json`` and ``diagnostic.png`` next to the patches.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np

from orbyt.modules.pollution_hunter import extract
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.core_math import (
    daily_flux_density,
    emg,
    estimate_emission,
    failed_gates,
    fan_half_width,
    stack_profile,
)
from orbyt.sources import era5

REPO_FINDINGS = (
    extract.gee.REPO_ROOT / "web" / "public" / "data" / "v1" / "pollution-hunter" / "findings.json"
)


def grid(spec: dict[str, float]) -> np.ndarray:
    """Evenly spaced axis from start to stop, both included."""
    n = round((spec["stop"] - spec["start"]) / spec["step"])
    return spec["start"] + spec["step"] * np.arange(n + 1)


def reported_tonnes(subject_id: str, path: Path = REPO_FINDINGS) -> float | None:
    """The register value for the subject from findings.json, or None if it is not there."""
    if not path.exists():
        return None
    for f in json.loads(path.read_text(encoding="utf-8"))["findings"]:
        if f["subject"]["id"] == subject_id:
            return float(f["claimed"]["value"])
    return None


def select_days(
    winds: list[era5.DayWind], min_speed_ms: float
) -> tuple[list[era5.DayWind], dict[str, int]]:
    """Days with a wind of at least ``min_speed_ms``, and counts of what was dropped."""
    kept = [w for w in winds if w.speed_ms is not None and w.speed_ms >= min_speed_ms]
    dropped = {
        "no_wind": sum(w.speed_ms is None for w in winds),
        "calm": sum(w.speed_ms is not None and w.speed_ms < min_speed_ms for w in winds),
    }
    return kept, dropped


def daily_fluxes(
    subject: extract.Subject,
    days: list[era5.DayWind],
    patch_dir: Path,
    t_hours: np.ndarray,
    yr_km: np.ndarray,
    cfg: dict,
) -> np.ndarray:
    """[n_days, len(yr), len(t)] flux density in mol per m per s, one slice per day."""
    out = []
    for d in days:
        files = sorted(patch_dir.glob(f"{d.day.replace('-', '')}_*.npz"))
        field, lats, lons, _ = extract.load_patch(files[0])
        out.append(
            daily_flux_density(
                field,
                lats,
                lons,
                subject.lat,
                subject.lon,
                d.u_ms,
                d.v_ms,
                t_hours,
                yr_km,
                upwind_km=tuple(cfg["upwind_box_km"]),
                flank_km=cfg["flank_km"],
            )
        )
    return np.array(out)


SECTORS = (("N", 315.0, 45.0), ("E", 45.0, 135.0), ("S", 135.0, 225.0), ("W", 225.0, 315.0))


def sector_of(from_deg: float) -> str:
    """Which quarter of the compass the wind comes from."""
    for name, lo, hi in SECTORS:
        inside = (from_deg >= lo or from_deg < hi) if lo > hi else (lo <= from_deg < hi)
        if inside:
            return name
    raise AssertionError("unreachable")


def sector_profiles(
    flux: np.ndarray,
    days: list[era5.DayWind],
    yr_km: np.ndarray,
    half_width_km: np.ndarray,
    min_days: int,
) -> list[dict]:
    """The stacked curve for each wind quarter with enough days, same fan as the estimate.

    A source seen from four sides should give four similar curves. A quarter that stands out
    points at another source or uneven background in that direction.
    """
    names = np.array([sector_of(d.from_deg) for d in days])
    out = []
    for name, _, _ in SECTORS:
        idx = np.where(names == name)[0]
        row: dict[str, Any] = {"wind_from": name, "n_days": len(idx), "flux_mol_s": None}
        if len(idx) >= min_days:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                row["flux_mol_s"] = stack_profile(flux[idx], yr_km, half_width_km)
        out.append(row)
    return out


def run_estimate(
    flux: np.ndarray, t_hours: np.ndarray, yr_km: np.ndarray, speeds: list[float], cfg: dict
) -> tuple[dict | None, list[str]]:
    """The emission estimate and the names of the gates it fails."""
    # An all-NaN scene is a day the satellite could not see the plume, not an error.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        est = estimate_emission(
            flux,
            t_hours,
            yr_km,
            speeds,
            n_boot=cfg["n_boot"],
            seed=cfg["seed"],
            nox_to_no2=cfg["nox_to_no2"],
            amf_correction=cfg["amf_correction"],
        )
    return est, failed_gates(est, min_days=cfg["min_days"])


def profile_of(flux: np.ndarray, t_hours: np.ndarray, yr_km: np.ndarray, speeds: list[float]):
    """The stacked profile and the fan used, as the estimate saw them."""
    hw = fan_half_width(t_hours, float(np.mean(speeds)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return stack_profile(flux, yr_km, hw), hw


def _clean(x: Any) -> Any:
    """Make numpy values JSON safe, with NaN as null."""
    if isinstance(x, np.ndarray):
        return [_clean(v) for v in x.tolist()]
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def build_document(
    subject: extract.Subject,
    days: list[era5.DayWind],
    all_days: int,
    dropped: dict[str, int],
    est: dict | None,
    gates: list[str],
    t_hours: np.ndarray,
    profile: np.ndarray,
    reported_t: float | None,
    cfg: dict,
    sectors: list[dict] | None = None,
) -> dict:
    fit = None
    if est is not None:
        curve = emg(t_hours, est["q"], est["tau"], est["sigma"], est["t0"], est["b"])
        fit = {k: est[k] for k in ("q", "tau", "sigma", "t0", "b", "r2")}
        fit["curve_mol_s"] = curve
    return _clean(
        {
            "subject_id": subject.subject_id,
            "name": subject.name,
            "method": load_config()["method_version"],
            "constants": {
                k: cfg[k]
                for k in (
                    "nox_to_no2",
                    "amf_correction",
                    "n_boot",
                    "seed",
                    "upwind_box_km",
                    "flank_km",
                )
            },
            "min_speed_ms": load_config()["wind"]["min_speed_ms"],
            "days": {"cached": all_days, "used": len(days), "dropped": dropped},
            "observed": None
            if est is None
            else {
                "nox_t_yr": est["nox_t_yr"],
                "lo": est["ci95"][0],
                "hi": est["ci95"][1],
                "unit": "t NOx/yr as NO2",
                "n_boot_ok": est["n_boot_ok"],
                "lifetime_h": est["tau"],
            },
            "reported_t_yr": reported_t,
            "ratio": None if est is None or not reported_t else est["nox_t_yr"] / reported_t,
            "gates_failed": gates,
            "profile": {"t_h": t_hours, "flux_mol_s": profile, "fit": fit},
            "sectors": sectors or [],
            "day_list": [
                {"date": d.day, "wind_ms": d.speed_ms, "wind_from_deg": d.from_deg} for d in days
            ],
        }
    )


def estimate_name(
    year: int | None, stem: str = "estimate", suffix: str = ".json", level: str = "100m"
) -> str:
    """``estimate.json`` for all cached days, ``estimate-2024.json`` for one calendar year.

    A wind level other than the default 100 m adds its name: ``estimate-2024-500m.json``.
    """
    tag = "" if level == "100m" else f"-{level}"
    return f"{stem}{'' if year is None else f'-{year}'}{tag}{suffix}"


def observe_subject(
    subject_id: str,
    out_dir: Path | None = None,
    log=print,
    year: int | None = None,
    level: str = "100m",
) -> Path:
    """Estimate one subject. ``year`` keeps only the cached days of that UTC calendar year."""
    out_dir = out_dir or extract.INTERIM_DIR
    cfg = load_config()["observe"]
    subject = extract.load_subject(subject_id)
    patch_dir = out_dir / subject_id
    winds = era5.read_winds(era5.wind_path(out_dir, subject_id, level))
    if year is not None:
        winds = [w for w in winds if w.day.startswith(f"{year}-")]
        if not winds:
            raise SystemExit(f"no cached days of {year} for {subject_id}")
    days, dropped = select_days(winds, load_config()["wind"]["min_speed_ms"])
    t_hours, yr_km = grid(cfg["travel_hours"]), grid(cfg["crosswind_km"])
    flux = daily_fluxes(subject, days, patch_dir, t_hours, yr_km, cfg)
    speeds = [d.speed_ms for d in days]
    est, gates = run_estimate(flux, t_hours, yr_km, speeds, cfg)
    profile, hw = profile_of(flux, t_hours, yr_km, speeds)
    doc = build_document(
        subject,
        days,
        len(winds),
        dropped,
        est,
        gates,
        t_hours,
        profile,
        reported_tonnes(subject_id),
        cfg,
        sector_profiles(flux, days, yr_km, hw, cfg["sector_min_days"]),
    )
    doc["wind_level"] = level
    path = patch_dir / estimate_name(year, level=level)
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    from orbyt.modules.pollution_hunter.diagnostic import draw_diagnostic

    draw_diagnostic(
        patch_dir / estimate_name(year, "diagnostic", ".png", level), doc, flux, t_hours, yr_km, hw
    )
    log(json.dumps({k: doc[k] for k in ("observed", "reported_t_yr", "ratio", "gates_failed")}))
    log(f"days used {len(days)} of {len(winds)} ({dropped})")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate one facility's NOx emission")
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--window", type=int, help="calendar year; default is every cached day")
    parser.add_argument("--level", default="100m", choices=["100m", "500m"], help="wind level")
    args = parser.parse_args()
    path = observe_subject(args.subject_id, args.out_dir, year=args.window, level=args.level)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
