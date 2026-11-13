"""Panel evidence for one subject (M3.7): what the VerdictPanel draws next to the estimate.

Writes into the web data contract (PLAN.md 2.5 and Appendix B):

* ``img/ph/<subject>/stack-<year>.webp``: the wind-aligned plume image, all days averaged.
* ``img/ph/<subject>/flipbook-<year>.webp``: one north-up frame per clear day, as a sprite sheet.
* ``finding/<id>.json``: the stacked curve with its fit, the day list and the image geometry.
* ``findings.json``: the estimate with its interval for that subject.

Only a subject whose estimate passes every gate is published (PLAN.md 4.3 step 9). Run it after
observe, and again after an EEA export, which rewrites the reported side of both JSON files.

    uv run python -m orbyt.modules.pollution_hunter.evidence --subject-id ph-eu-...

Units: enhancement in mol/m2 inside the maths, micromol/m2 in images and files.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np

from orbyt.modules.pollution_hunter import detect, extract
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.core_math import fan_half_width, rotate_scene
from orbyt.modules.pollution_hunter.layers import RAMP
from orbyt.modules.pollution_hunter.observe import daily_fluxes, grid, select_days
from orbyt.sources import era5

WEB_PUBLIC = extract.gee.REPO_ROOT / "web" / "public"
FINDINGS = WEB_PUBLIC / "data" / "v1" / "pollution-hunter" / "findings.json"
IMG_URL = "/img/ph"

# Mirrors of the design tokens in PLAN.md 9.2: the night ocean under the glow, and the raised
# surface for cells the satellite could not see.
BASE_RGB = (0x04, 0x07, 0x0B)  # --earth-ocean
NO_DATA_RGB = (0x16, 0x1D, 0x26)  # --raised
UMOL = 1e6
SOURCES = ("Copernicus Sentinel-5P", "ERA5")


def _hex(colour: str) -> tuple[int, int, int]:
    h = colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def colourise_glow(enh_umol_m2: np.ndarray, full_scale_umol_m2: float) -> np.ndarray:
    """RGB uint8 image: the plume ramp with its opacity (PLAN.md 9.2) laid over the base colour.

    Linear from 0 to ``full_scale_umol_m2``. Zero and below show the base, NaN the no-data colour.
    """
    pos = np.clip(np.nan_to_num(enh_umol_m2, nan=0.0) / full_scale_umol_m2, 0.0, 1.0)
    stops = [p for p, _, _ in RAMP]
    alpha = np.interp(pos, stops, [a for _, _, a in RAMP])[..., None]
    ramp = np.stack(
        [np.interp(pos, stops, [_hex(c)[k] for _, c, _ in RAMP]) for k in range(3)], axis=-1
    )
    rgb = np.rint(ramp * alpha + np.array(BASE_RGB) * (1.0 - alpha)).astype(np.uint8)
    rgb[~np.isfinite(enh_umol_m2)] = NO_DATA_RGB
    return rgb


def nice_full_scale(peak: float, steps: list[float]) -> float:
    """The smallest listed step that holds ``peak``, or the largest one."""
    for s in steps:
        if peak <= s:
            return float(s)
    return float(steps[-1])


def stack_enhancement(flux: np.ndarray, speeds: list[float], min_days_frac: float) -> np.ndarray:
    """Mean enhancement over days in mol/m2 on the travel-time grid, [len(yr), len(t)].

    ``flux`` is [n_days, len(yr), len(t)] in mol per m per s. Dividing each day by its wind speed
    gives back the column above that day's background. Cells seen on too few days are NaN.
    """
    enh = flux / np.asarray(speeds, dtype=float)[:, None, None]
    with warnings.catch_warnings():  # all-NaN cells are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        cover = np.isfinite(enh).mean(axis=0)
        return np.where(cover >= min_days_frac, np.nanmean(enh, axis=0), np.nan)


def plane_coefficients(
    plane: np.ndarray, x_km: np.ndarray, yr_km: np.ndarray
) -> tuple[float, float, float]:
    """(c0, cx, cy) of ``plane = c0 + cx * x + cy * y`` from its values on the grid."""
    cx = (plane[0, -1] - plane[0, 0]) / (x_km[-1] - x_km[0])
    cy = (plane[-1, 0] - plane[0, 0]) / (yr_km[-1] - yr_km[0])
    return float(plane[0, 0] - cx * x_km[0] - cy * yr_km[0]), float(cx), float(cy)


def north_up_enhancement(
    field: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    lat0: float,
    lon0: float,
    u_ms: float,
    v_ms: float,
    coef: tuple[float, float, float],
    east_km: np.ndarray,
    north_km: np.ndarray,
) -> np.ndarray:
    """One day as a map around the source, north up, background plane removed, in mol/m2.

    ``coef`` is the plane in wind-aligned km (x downwind, y across), as the estimate fits it.
    Returns [len(north_km), len(east_km)] with row 0 the southern edge.
    """
    raw = rotate_scene(field, lats, lons, lat0, lon0, 1.0, 0.0, east_km, north_km)
    theta = math.atan2(v_ms, u_ms)
    c, s = math.cos(theta), math.sin(theta)
    east, north = np.meshgrid(east_km, north_km)
    x, y = c * east + s * north, -s * east + c * north
    return raw - (coef[0] + coef[1] * x + coef[2] * y)


def _save_webp(rgb: np.ndarray, path: Path, size: tuple[int, int] | None, quality: int) -> None:
    from PIL import Image

    im = Image.fromarray(rgb)
    if size is not None:
        im = im.resize(size, Image.BICUBIC)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=quality, method=6)


def render_stack(
    path: Path,
    enh_mol_m2: np.ndarray,
    t_hours: np.ndarray,
    yr_km: np.ndarray,
    mean_speed_ms: float,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Write the wind-aligned plume image and return its geometry for the panel.

    The picture is drawn true to scale at the mean wind: one hour of travel is as wide as the
    distance the mean wind covers in it. Crosswind +y is up.
    """
    enh = enh_mol_m2 * UMOL
    peak = float(np.nanpercentile(enh, cfg["full_scale_percentile"]))
    full = nice_full_scale(peak, cfg["full_scale_steps_umol_m2"])
    span_km = (t_hours[-1] - t_hours[0]) * mean_speed_ms * 3.6
    width = int(cfg["width_px"])
    height = round(width * (yr_km[-1] - yr_km[0]) / span_km)
    _save_webp(colourise_glow(enh[::-1], full), path, (width, height), cfg["webp_quality"])
    return {
        "width": width,
        "height": height,
        "t_h": [float(t_hours[0]), float(t_hours[-1])],
        "crosswind_km": [float(yr_km[0]), float(yr_km[-1])],
        "full_scale_umol_m2": full,
        "mean_wind_ms": round(mean_speed_ms, 2),
        "fan_half_width_km": [round(float(v), 1) for v in fan_half_width(t_hours, mean_speed_ms)],
    }


def render_flipbook(
    path: Path, frames_mol_m2: list[np.ndarray], cfg: dict[str, Any]
) -> dict[str, Any]:
    """Write the sprite sheet of north-up frames (row 0 of each array is south) and its grid."""
    from PIL import Image

    n = len(frames_mol_m2)
    ny, nx = frames_mol_m2[0].shape
    up = int(cfg["upscale"])
    fw, fh = nx * up, ny * up
    columns = max(1, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / columns)
    sheet = Image.new("RGB", (columns * fw, rows * fh), BASE_RGB)
    for k, frame in enumerate(frames_mol_m2):
        rgb = colourise_glow(frame[::-1] * UMOL, cfg["full_scale_umol_m2"])
        tile = Image.fromarray(rgb).resize((fw, fh), Image.BICUBIC)
        sheet.paste(tile, ((k % columns) * fw, (k // columns) * fh))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, "WEBP", quality=cfg["webp_quality"], method=6)
    return {
        "frame_w": fw,
        "frame_h": fh,
        "columns": columns,
        "rows": rows,
        "n_frames": n,
        "half_km": float(cfg["half_km"]),
        "full_scale_umol_m2": float(cfg["full_scale_umol_m2"]),
    }


def day_frames(
    subject: extract.Subject,
    days: list[era5.DayWind],
    patch_dir: Path,
    cfg: dict[str, Any],
    dcfg: dict[str, Any],
    fcfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    """The day list for the panel and the north-up frames of the clear days, in day order.

    The single-day plume test (detect.py) is left out of the published rows on purpose: its
    false alarm rate is not set until the null sites of M4, and on real scenes it flags days
    with nothing to see (docs/decisions.md, M3.6 and M3.7).
    """
    x_km, yr_km = grid(dcfg["x_km"]), grid(cfg["crosswind_km"])
    half, step = fcfg["half_km"], fcfg["step_km"]
    axis = np.arange(-half, half + step / 2, step)
    rows: list[dict[str, Any]] = []
    frames: list[np.ndarray] = []
    for d in days:
        files = sorted(patch_dir.glob(f"{d.day.replace('-', '')}_*.npz"))
        field, lats, lons, _ = extract.load_patch(files[0])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            got = detect.day_plane(
                field, lats, lons, subject.lat, subject.lon, d.u_ms, d.v_ms, x_km, yr_km, cfg
            )
        row: dict[str, Any] = {
            "date": d.day,
            "wind_ms": round(float(d.speed_ms), 1),
            "wind_dir_deg": round(float(d.from_deg)),  # the direction the wind blows from
            "frame": None,
        }
        if got is not None:
            _, plane = got
            north_up = north_up_enhancement(
                field,
                lats,
                lons,
                subject.lat,
                subject.lon,
                d.u_ms,
                d.v_ms,
                plane_coefficients(plane, x_km, yr_km),
                axis,
                axis,
            )
            if np.isfinite(north_up).mean() >= fcfg["min_valid_frac"]:
                row["frame"] = len(frames)
                frames.append(north_up)
        rows.append(row)
    return rows, frames


def _round_list(values: Any, digits: int) -> list[float | None]:
    return [None if v is None or not np.isfinite(v) else round(float(v), digits) for v in values]


def merge_into_contract(
    findings_path: Path,
    subject_id: str,
    year: str,
    observed: dict[str, Any],
    detail: dict[str, Any],
) -> Path:
    """Add the satellite side to findings.json and to the subject's detail file."""
    payload = json.loads(findings_path.read_text(encoding="utf-8"))
    matches = [f for f in payload["findings"] if f["subject"]["id"] == subject_id]
    if not matches:
        raise KeyError(f"{subject_id} is not in {findings_path.name}")
    finding = matches[0]
    if finding["period"]["label"] != year:
        raise ValueError(
            f"estimate is for {year}, the reported value is for {finding['period']['label']}"
        )
    finding["observed"] = observed
    findings_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    detail_path = findings_path.parent / "finding" / f"{finding['id']}.json"
    doc = json.loads(detail_path.read_text(encoding="utf-8"))
    doc.update(detail)
    doc["observed"] = observed
    doc["sources"] = list(dict.fromkeys([*doc.get("sources", []), *SOURCES]))
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n"
    detail_path.write_text(text, encoding="utf-8")
    return detail_path


def publish_subject(
    subject_id: str,
    interim_dir: Path | None = None,
    web_public: Path = WEB_PUBLIC,
    findings_path: Path = FINDINGS,
    log=print,
) -> Path:
    interim_dir = interim_dir or extract.INTERIM_DIR
    all_cfg = load_config()
    cfg, dcfg, ecfg = all_cfg["observe"], all_cfg["detect"], all_cfg["evidence"]
    patch_dir = interim_dir / subject_id
    est = json.loads((patch_dir / "estimate.json").read_text(encoding="utf-8"))
    if est["gates_failed"] or est["observed"] is None:
        raise SystemExit(
            f"{subject_id} fails {est['gates_failed'] or ['no_fit']}: inconclusive, not published"
        )
    if est["method"] != all_cfg["method_version"]:
        raise SystemExit(f"estimate.json is from {est['method']}, rerun observe first")

    subject = extract.load_subject(subject_id)
    winds = era5.read_winds(era5.wind_path(interim_dir, subject_id))
    days, _ = select_days(winds, all_cfg["wind"]["min_speed_ms"])
    years = {d.day[:4] for d in days}
    if len(years) != 1:
        raise SystemExit(f"days span {sorted(years)}, one calendar year expected")
    year = years.pop()
    speeds = [float(d.speed_ms) for d in days]
    t_hours, yr_km = grid(cfg["travel_hours"]), grid(cfg["crosswind_km"])

    img_dir = web_public / "img" / "ph" / subject_id
    flux = daily_fluxes(subject, days, patch_dir, t_hours, yr_km, cfg)
    stack = render_stack(
        img_dir / f"stack-{year}.webp",
        stack_enhancement(flux, speeds, ecfg["stack"]["min_days_frac"]),
        t_hours,
        yr_km,
        float(np.mean(speeds)),
        ecfg["stack"],
    )
    stack["n_days"] = len(days)
    day_rows, frames = day_frames(subject, days, patch_dir, cfg, dcfg, ecfg["flipbook"])
    sheet = render_flipbook(img_dir / f"flipbook-{year}.webp", frames, ecfg["flipbook"])

    obs, fit = est["observed"], est["profile"]["fit"]
    observed = {
        "value": round(obs["nox_t_yr"]),
        "lo": round(obs["lo"]),
        "hi": round(obs["hi"]),
        "unit": "t NOx/yr",
        "method": est["method"],
        "n_days": len(days),
        "lifetime_h": round(obs["lifetime_h"], 1),
        # The interval is the bootstrap over days. Systematic terms come with validation (4.7).
        "interval_basis": "sampling",
    }
    detail = {
        "profile": {
            "t_h": _round_list(est["profile"]["t_h"], 2),
            "flux_mol_s": _round_list(est["profile"]["flux_mol_s"], 3),
            "fit_mol_s": _round_list(fit["curve_mol_s"], 3),
            "fit": {k: round(fit[k], 3) for k in ("q", "tau", "sigma", "t0", "b", "r2")},
        },
        "days": day_rows,
        "evidence": {
            "stack_image": f"{IMG_URL}/{subject_id}/stack-{year}.webp",
            "flipbook": f"{IMG_URL}/{subject_id}/flipbook-{year}.webp",
            "stack": stack,
            "flipbook_sheet": sheet,
        },
    }
    path = merge_into_contract(findings_path, subject_id, year, observed, detail)
    log(
        f"published {subject_id} {year}: {observed['value']} t ({observed['lo']} to "
        f"{observed['hi']}), {len(days)} days, {len(frames)} frames"
    )
    return path


def main() -> None:
    p = argparse.ArgumentParser(description="Publish the panel evidence for one subject")
    p.add_argument("--subject-id", required=True)
    a = p.parse_args()
    publish_subject(a.subject_id)


if __name__ == "__main__":
    main()
