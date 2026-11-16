"""Single-day plume test and the flipbook (PLAN.md 4.4, M3.6).

Each day is rotated so the wind points along +x, the background plane is subtracted (the same
plane as the estimate, see core_math.background_plane) and a box downwind of the source is
compared with the mirrored box upwind. The same enhancement images, for the days that are clear
enough, are drawn into one sprite sheet for the panel.

Units: enhancement in mol/m2 inside the maths and micromol/m2 in files and on screen.
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from orbyt.modules.pollution_hunter import extract
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.core_math import (
    background_plane,
    fan_half_width,
    rotate_scene,
)
from orbyt.modules.pollution_hunter.observe import grid, select_days
from orbyt.sources import era5

# Plume ramp from PLAN.md 9.2, low to high. Drawn on black, so the opacity column is not used.
RAMP = (
    (0.00, (0x4F, 0x1C, 0x00)),
    (0.15, (0x7D, 0x35, 0x01)),
    (0.35, (0xAF, 0x55, 0x04)),
    (0.55, (0xD9, 0x7A, 0x05)),
    (0.75, (0xF5, 0xA4, 0x20)),
    (0.90, (0xFC, 0xD5, 0x83)),
    (1.00, (0xFD, 0xF6, 0xD8)),
)
NO_DATA_RGB = (0x16, 0x1D, 0x26)  # --raised in PLAN.md 9.2
TEXT_RGB = (0xF2, 0xF4, 0xF7)  # --text
TEXT_2_RGB = (0xAA, 0xB2, 0xBD)  # --text-2
DETECTED_RGB = (0xFF, 0xB0, 0x2E)  # module glow step, PLAN.md 9.2


@dataclass(frozen=True)
class DayTest:
    """Result of the plume test on one day."""

    day: str
    speed_ms: float
    from_deg: float
    testable: bool
    detected: bool
    z: float | None
    down_umol_m2: float | None
    up_umol_m2: float | None
    noise_umol_m2: float | None
    valid_down: float
    valid_up: float


def day_plane(
    field: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    lat0: float,
    lon0: float,
    u_ms: float,
    v_ms: float,
    x_km: np.ndarray,
    yr_km: np.ndarray,
    cfg: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray] | None:
    """One day on a wind-aligned km grid and its background plane, both in mol/m2.

    None if the upwind box is too cloudy or the plane cannot be fitted.
    """
    x_up = np.arange(cfg["upwind_box_km"][0], cfg["upwind_box_km"][1] + 1, 2.0)
    up = rotate_scene(field, lats, lons, lat0, lon0, u_ms, v_ms, x_up, yr_km)
    if np.isfinite(up).mean() < 0.3:
        return None
    scene = rotate_scene(field, lats, lons, lat0, lon0, u_ms, v_ms, x_km, yr_km)
    plane = background_plane(scene, up, x_km, x_up, np.asarray(yr_km), cfg["flank_km"])
    return None if plane is None else (scene, plane)


def aligned_enhancement(
    field: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    lat0: float,
    lon0: float,
    u_ms: float,
    v_ms: float,
    x_km: np.ndarray,
    yr_km: np.ndarray,
    cfg: dict[str, Any],
) -> np.ndarray | None:
    """One day on a wind-aligned km grid, background removed, in mol/m2. None if unusable."""
    got = day_plane(field, lats, lons, lat0, lon0, u_ms, v_ms, x_km, yr_km, cfg)
    return None if got is None else got[0] - got[1]


def _box_masks(
    x_km: np.ndarray, yr_km: np.ndarray, speed_ms: float, dcfg: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Cells of the downwind box and the mirrored upwind box, both inside the fan."""
    length = min(dcfg["box_hours"] * speed_ms * 3.6, dcfg["box_max_km"])
    half = fan_half_width(np.abs(x_km) / (3.6 * speed_ms), speed_ms)
    in_fan = np.abs(yr_km)[:, None] <= half[None, :]
    down = in_fan & ((x_km > 0) & (x_km <= length))[None, :]
    up = in_fan & ((x_km < 0) & (x_km >= -length))[None, :]
    return down, up


def test_day(
    enh: np.ndarray,
    x_km: np.ndarray,
    yr_km: np.ndarray,
    speed_ms: float,
    flank_km: float,
    dcfg: dict[str, Any],
) -> dict[str, Any]:
    """The z test of PLAN.md 4.4 on one wind-aligned enhancement image (mol/m2)."""
    down_m, up_m = _box_masks(x_km, yr_km, speed_ms, dcfg)
    valid_down = float(np.isfinite(enh[down_m]).mean()) if down_m.any() else 0.0
    valid_up = float(np.isfinite(enh[up_m]).mean()) if up_m.any() else 0.0
    out: dict[str, Any] = {
        "testable": False,
        "detected": False,
        "z": None,
        "down": None,
        "up": None,
        "noise": None,
        "valid_down": valid_down,
        "valid_up": valid_up,
    }
    need = dcfg["min_valid_frac"]
    if valid_down < need or valid_up < need:
        return out
    flank = np.abs(yr_km) >= flank_km
    cells = enh[flank, :][:, np.abs(x_km) <= dcfg["box_max_km"]]
    cells = cells[np.isfinite(cells)]
    if cells.size < 20:
        return out
    centre = np.median(cells)
    sigma_cell = 1.4826 * np.median(np.abs(cells - centre))
    dx, dy = abs(x_km[1] - x_km[0]), abs(yr_km[1] - yr_km[0])
    n_ind = max(1.0, down_m.sum() * dx * dy / dcfg["pixel_area_km2"])
    noise = sigma_cell / np.sqrt(n_ind)
    down, up = float(np.nanmean(enh[down_m])), float(np.nanmean(enh[up_m]))
    out.update(testable=True, down=down, up=up, noise=float(noise))
    if noise > 0:
        z = (down - up) / noise
        out.update(z=float(z), detected=bool(z >= dcfg["z_min"]))
    return out


def run_days(
    subject: extract.Subject,
    days: list[era5.DayWind],
    patch_dir: Path,
    cfg: dict[str, Any],
    dcfg: dict[str, Any],
) -> tuple[list[DayTest], list[np.ndarray | None]]:
    """The test and the enhancement image (mol/m2, shape [ny, nx]) for every day."""
    x_km, yr_km = grid(dcfg["x_km"]), grid(cfg["crosswind_km"])
    tests: list[DayTest] = []
    images: list[np.ndarray | None] = []
    for d in days:
        files = sorted(patch_dir.glob(f"{d.day.replace('-', '')}_*.npz"))
        field, lats, lons, _ = extract.load_patch(files[0])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            enh = aligned_enhancement(
                field, lats, lons, subject.lat, subject.lon, d.u_ms, d.v_ms, x_km, yr_km, cfg
            )
            r = (
                test_day(enh, x_km, yr_km, d.speed_ms, cfg["flank_km"], dcfg)
                if enh is not None
                else None
            )
        images.append(enh)
        um = 1e6
        tests.append(
            DayTest(
                day=d.day,
                speed_ms=float(d.speed_ms),
                from_deg=float(d.from_deg),
                testable=bool(r and r["testable"]),
                detected=bool(r and r["detected"]),
                z=None if not r or r["z"] is None else round(r["z"], 2),
                down_umol_m2=None if not r or r["down"] is None else round(r["down"] * um, 2),
                up_umol_m2=None if not r or r["up"] is None else round(r["up"] * um, 2),
                noise_umol_m2=None if not r or r["noise"] is None else round(r["noise"] * um, 3),
                valid_down=round(r["valid_down"], 2) if r else 0.0,
                valid_up=round(r["valid_up"], 2) if r else 0.0,
            )
        )
    return tests, images


# --- Flipbook ---------------------------------------------------------------------------------


def colourise(enh_umol_m2: np.ndarray, full_scale_umol_m2: float) -> np.ndarray:
    """RGB uint8 image from enhancement, on the plume ramp. NaN gets the no-data colour."""
    pos = np.clip(np.nan_to_num(enh_umol_m2, nan=0.0) / full_scale_umol_m2, 0.0, 1.0)
    p = np.array([r[0] for r in RAMP])
    rgb = np.stack([np.interp(pos, p, [r[1][k] for r in RAMP]) for k in range(3)], axis=-1).astype(
        np.uint8
    )
    rgb[~np.isfinite(enh_umol_m2)] = NO_DATA_RGB
    return rgb


def clear_frame_indices(
    images: list[np.ndarray | None], x_km: np.ndarray, show_from_km: float, min_valid: float
) -> list[int]:
    """Days whose shown part of the image is mostly valid, in input order."""
    cols = x_km >= show_from_km
    keep = []
    for i, im in enumerate(images):
        if im is not None and np.isfinite(im[:, cols]).mean() >= min_valid:
            keep.append(i)
    return keep


def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow older than 10.1 has one fixed size
        return ImageFont.load_default()


def _compass(draw, cx: float, cy: float, from_deg: float, r: float) -> None:
    """Arrow showing where the wind blows to on the map, north up."""
    to = np.radians((from_deg + 180.0) % 360.0)
    dx, dy = np.sin(to), -np.cos(to)
    tip = (cx + dx * r, cy + dy * r)
    tail = (cx - dx * r, cy - dy * r)
    draw.line([tail, tip], fill=TEXT_RGB, width=2)
    for side in (-1, 1):
        ang = to + np.pi + side * 0.5
        draw.line(
            [tip, (tip[0] + np.sin(ang) * r * 0.6, tip[1] - np.cos(ang) * r * 0.6)],
            fill=TEXT_RGB,
            width=2,
        )


def compass_name(from_deg: float) -> str:
    names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return names[int(((from_deg % 360.0) + 22.5) // 45.0) % 8]


def draw_flipbook(
    path: Path,
    images: list[np.ndarray],
    tests: list[DayTest],
    x_km: np.ndarray,
    yr_km: np.ndarray,
    fcfg: dict[str, Any],
) -> dict[str, Any]:
    """Write the sprite sheet PNG and return the manifest for the player."""
    from PIL import Image, ImageDraw

    show = x_km >= fcfg["show_from_km"]
    scale, label_h, cols = fcfg["scale_px"], fcfg["label_px"], fcfg["columns"]
    fw, fh = int(show.sum()) * scale, len(yr_km) * scale + label_h
    rows = max(1, -(-len(images) // cols))
    sheet = Image.new("RGB", (cols * fw, rows * fh), (0, 0, 0))
    small, tiny = _font(12), _font(10)
    frames = []
    for k, (im, t) in enumerate(zip(images, tests, strict=True)):
        col, row = k % cols, k // cols
        pic = colourise(im[:, show][::-1] * 1e6, fcfg["full_scale_umol_m2"])  # +y up
        tile = Image.fromarray(pic).resize((fw, fh - label_h), Image.NEAREST)
        frame = Image.new("RGB", (fw, fh), (0, 0, 0))
        frame.paste(tile, (0, 0))
        d = ImageDraw.Draw(frame)
        sx = int((0.0 - fcfg["show_from_km"]) / abs(x_km[1] - x_km[0]) * scale + scale / 2)
        sy = int((fh - label_h) / 2)
        d.line([(sx - 6, sy), (sx + 6, sy)], fill=TEXT_RGB, width=1)
        d.line([(sx, sy - 6), (sx, sy + 6)], fill=TEXT_RGB, width=1)
        d.text((4, fh - label_h + 3), t.day, fill=TEXT_RGB, font=small)
        z = "z n/a" if t.z is None else f"z {t.z:.1f}"
        verdict = "plume" if t.detected else ("no plume" if t.testable else "not tested")
        d.text(
            (4, fh - label_h + 19),
            f"{t.speed_ms:.1f} m/s {compass_name(t.from_deg)}  {z}",
            fill=TEXT_2_RGB,
            font=tiny,
        )
        d.text(
            (4, fh - label_h + 31),
            verdict,
            fill=DETECTED_RGB if t.detected else TEXT_2_RGB,
            font=tiny,
        )
        _compass(d, fw - 18, fh - label_h / 2, t.from_deg, 9)
        if t.detected:
            d.rectangle([0, 0, fw - 1, fh - 1], outline=DETECTED_RGB, width=2)
        sheet.paste(frame, (col * fw, row * fh))
        frames.append(
            {
                "index": k,
                "day": t.day,
                "col": col,
                "row": row,
                "speed_ms": round(t.speed_ms, 2),
                "wind_from_deg": round(t.from_deg, 1),
                "z": t.z,
                "detected": t.detected,
                "tested": t.testable,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)
    return {
        "image": path.name,
        "frame_w": fw,
        "frame_h": fh,
        "columns": cols,
        "rows": rows,
        "scale_px": scale,
        "x_km_from": fcfg["show_from_km"],
        "x_km_to": float(x_km[-1]),
        "crosswind_km_half": float(yr_km[-1]),
        "full_scale_umol_m2": fcfg["full_scale_umol_m2"],
        "frames": frames,
    }


# --- CLI --------------------------------------------------------------------------------------


def detect_subject(subject_id: str, out_dir: Path | None = None, log=print) -> Path:
    out_dir = out_dir or extract.INTERIM_DIR
    all_cfg = load_config()
    cfg, dcfg = all_cfg["observe"], all_cfg["detect"]
    subject = extract.load_subject(subject_id)
    patch_dir = out_dir / subject_id
    winds = era5.read_winds(era5.wind_path(out_dir, subject_id, all_cfg["wind"]["level"]))
    days, dropped = select_days(winds, all_cfg["wind"]["min_speed_ms"])
    tests, images = run_days(subject, days, patch_dir, cfg, dcfg)
    x_km, yr_km = grid(dcfg["x_km"]), grid(cfg["crosswind_km"])
    fcfg = dcfg["flipbook"]
    keep = clear_frame_indices(images, x_km, fcfg["show_from_km"], fcfg["min_valid_frac"])
    manifest = draw_flipbook(
        patch_dir / "flipbook.png",
        [images[i] for i in keep],  # type: ignore[misc]
        [tests[i] for i in keep],
        x_km,
        yr_km,
        fcfg,
    )
    (patch_dir / "flipbook.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    testable = [t for t in tests if t.testable]
    doc = {
        "subject_id": subject_id,
        "method": "ph-detect-1.0",
        "z_min": dcfg["z_min"],
        "days_used": len(days),
        "days_dropped": dropped,
        "days_testable": len(testable),
        "days_detected": sum(t.detected for t in testable),
        "frames_in_flipbook": len(keep),
        "days": [t.__dict__ for t in tests],
    }
    path = patch_dir / "detect.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    log(
        f"plume detected on {doc['days_detected']} of {doc['days_testable']} testable days "
        f"({doc['days_used']} used), {len(keep)} frames in the flipbook"
    )
    return path


def main() -> None:
    p = argparse.ArgumentParser(description="Single-day plume test and flipbook for one subject")
    p.add_argument("--subject-id", required=True)
    p.add_argument("--out-dir", type=Path, default=None)
    a = p.parse_args()
    detect_subject(a.subject_id, a.out_dir)


if __name__ == "__main__":
    main()
