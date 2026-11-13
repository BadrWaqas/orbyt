"""ERA5 100 m wind at the moment the satellite passed over a source (M3.3).

For each cached day of a subject this works out when the satellite saw the source, takes the
ERA5 hour nearest to that moment, and reads the 100 m wind from the cell that holds the source.

    uv run python -m orbyt.sources.era5 --subject-id ph-eu-xxxxxxxx

The pass time comes from the sun. The image start and end are the edges of about an hour of
track, and the satellite crosses a source at a different minute on every day. At the source the
solar zenith angle fixes how far the sun is from local noon, and the sign of the solar azimuth
says which side (negative is west of south, so afternoon). That is turned into UTC with the
source longitude and the equation of time. The result must fall inside the image window. If it
does not, the plan's fixed 13:30 local solar time is used and the day says so.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import ee
import numpy as np

from orbyt.modules.pollution_hunter.config import load_config

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


@dataclass(frozen=True)
class DayWind:
    """The wind used for one day, and how the pass time behind it was found."""

    day: str  # UTC date of the image start, YYYY-MM-DD
    image_id: str
    pass_utc: str  # moment the satellite saw the source, ISO 8601
    pass_source: str  # "solar-geometry" or "fixed-solar-time"
    era5_hour_utc: str  # ERA5 hour used, ISO 8601
    u_ms: float | None  # eastward wind, m/s
    v_ms: float | None  # northward wind, m/s
    speed_ms: float | None
    from_deg: float | None  # compass direction the wind blows from, 0 = north, clockwise


def declination_and_eot(day_of_year: float) -> tuple[float, float]:
    """Solar declination (radians) and equation of time (minutes) for a day of the year.

    Fourier series of the NOAA solar calculator (Spencer 1971). Good to about a minute.
    """
    g = 2 * math.pi / 365.0 * (day_of_year - 1)
    decl = (
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.00148 * math.sin(3 * g)
    )
    eot = 229.18 * (
        0.000075
        + 0.001868 * math.cos(g)
        - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g)
        - 0.040849 * math.sin(2 * g)
    )
    return decl, eot


def pass_time_from_sun(
    day: date, lat_deg: float, lon_deg: float, sza_deg: float, saa_deg: float
) -> datetime | None:
    """UTC moment at which the sun at the source had this zenith angle and side.

    Returns None when the angles cannot be met at this latitude and date.
    """
    decl, eot_min = declination_and_eot(day.timetuple().tm_yday + 0.5)
    lat = math.radians(lat_deg)
    denom = math.cos(lat) * math.cos(decl)
    if denom <= 0:
        return None
    cos_h = (math.cos(math.radians(sza_deg)) - math.sin(lat) * math.sin(decl)) / denom
    if not -1.0 <= cos_h <= 1.0:
        return None
    hour_angle_deg = math.degrees(math.acos(cos_h))
    if saa_deg < 0:  # west of south: afternoon
        solar_hours = 12.0 + hour_angle_deg / 15.0
    else:
        solar_hours = 12.0 - hour_angle_deg / 15.0
    utc_hours = solar_hours - lon_deg / 15.0 - eot_min / 60.0
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return midnight + timedelta(hours=utc_hours)


def fixed_pass_time(day: date, lon_deg: float, solar_hour: float) -> datetime:
    """PLAN.md 4.3 step 3: UTC time of a fixed local solar hour, with no equation of time."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return midnight + timedelta(hours=solar_hour - lon_deg / 15.0)


def choose_pass_time(
    day: date,
    lat_deg: float,
    lon_deg: float,
    meta: dict[str, Any],
    *,
    fallback_solar_hour: float,
    tolerance_min: float,
) -> tuple[datetime, str]:
    """The pass time for one cached day, and where it came from.

    The sun based time is kept only if it sits inside the image window, widened by
    ``tolerance_min`` for the minute-level error of the sun formulas.
    """
    start = datetime.fromtimestamp(meta["start_ms"] / 1000, UTC)
    end_ms = meta.get("end_ms")
    end = datetime.fromtimestamp(end_ms / 1000, UTC) if end_ms else start + timedelta(hours=1)
    guess = pass_time_from_sun(day, lat_deg, lon_deg, meta["sza"], meta["saa"])
    slack = timedelta(minutes=tolerance_min)
    if guess is not None and start - slack <= guess <= end + slack:
        return guess, "solar-geometry"
    return fixed_pass_time(day, lon_deg, fallback_solar_hour), "fixed-solar-time"


def nearest_hour(moment: datetime) -> datetime:
    """The whole UTC hour closest to ``moment``."""
    floor = moment.replace(minute=0, second=0, microsecond=0)
    return floor + timedelta(hours=1) if moment.minute >= 30 else floor


def wind_speed_and_from(u_ms: float, v_ms: float) -> tuple[float, float]:
    """Speed in m/s and the compass bearing the wind comes from (0 = north, 90 = east)."""
    speed = math.hypot(u_ms, v_ms)
    from_deg = (math.degrees(math.atan2(-u_ms, -v_ms)) + 360.0) % 360.0
    return speed, from_deg


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def era5_winds(
    lat: float, lon: float, hours_ms: list[int], *, cfg: dict[str, Any] | None = None
) -> dict[int, tuple[float, float] | None]:
    """100 m (u, v) in m/s from the ERA5 cell holding the point, for each hour start in ms.

    One server call per batch of hours. An hour ERA5 does not have maps to None.
    """
    cfg = cfg or load_config()["wind"]
    bands = [cfg["u_band"], cfg["v_band"]]
    point = ee.Geometry.Point([lon, lat])
    collection = ee.ImageCollection(cfg["collection"])
    out: dict[int, tuple[float, float] | None] = {}
    wanted = sorted(set(hours_ms))
    for i in range(0, len(wanted), cfg["batch_hours"]):
        batch = wanted[i : i + cfg["batch_hours"]]

        def sample(t: Any) -> ee.Feature:
            img = collection.filter(ee.Filter.eq("system:time_start", t)).first()
            props = ee.Dictionary(
                ee.Algorithms.If(
                    img,
                    ee.Image(img)
                    .select(bands)
                    .reduceRegion(ee.Reducer.first(), point, cfg["scale_m"]),
                    ee.Dictionary({}),
                )
            )
            return ee.Feature(None, props.set("t", t))

        info = ee.FeatureCollection(ee.List(batch).map(sample)).getInfo()
        for feat in info["features"]:
            p = feat["properties"]
            u, v = p.get(bands[0]), p.get(bands[1])
            out[int(p["t"])] = (float(u), float(v)) if u is not None and v is not None else None
    return out


def build_day_winds(
    lat: float,
    lon: float,
    metas: list[dict[str, Any]],
    winds: dict[int, tuple[float, float] | None],
    *,
    cfg: dict[str, Any],
) -> list[DayWind]:
    """Join cached day metadata to the fetched winds."""
    rows = []
    for meta in metas:
        day, pass_time, source, hour = _day_plan(lat, lon, meta, cfg)
        uv = winds.get(int(hour.timestamp() * 1000))
        if uv is None:
            u = v = speed = from_deg = None
        else:
            u, v = uv
            speed, from_deg = wind_speed_and_from(u, v)
        rows.append(
            DayWind(
                day.isoformat(),
                meta["image_id"],
                _iso(pass_time),
                source,
                _iso(hour),
                u,
                v,
                speed,
                from_deg,
            )
        )
    return rows


def _day_plan(
    lat: float, lon: float, meta: dict[str, Any], cfg: dict[str, Any]
) -> tuple[date, datetime, str, datetime]:
    day = datetime.fromtimestamp(meta["start_ms"] / 1000, UTC).date()
    pass_time, source = choose_pass_time(
        day,
        lat,
        lon,
        meta,
        fallback_solar_hour=cfg["fallback_solar_hour"],
        tolerance_min=cfg["window_tolerance_min"],
    )
    return day, pass_time, source, nearest_hour(pass_time)


def wind_path(out_dir: Path, subject_id: str) -> Path:
    return out_dir / subject_id / "wind.json"


def write_winds(path: Path, subject_id: str, rows: list[DayWind], cfg: dict[str, Any]) -> Path:
    doc = {
        "subject_id": subject_id,
        "collection": cfg["collection"],
        "bands": [cfg["u_band"], cfg["v_band"]],
        "units": "m/s",
        "days": [asdict(r) for r in rows],
    }
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read_winds(path: Path) -> list[DayWind]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [DayWind(**d) for d in doc["days"]]


def winds_for_subject(subject_id: str, out_dir: Path | None = None, log=print) -> Path:
    """Fetch and cache the wind for every cached day of a subject. Returns the wind.json path."""
    from orbyt.modules.pollution_hunter import extract

    out_dir = out_dir or extract.INTERIM_DIR
    cfg = load_config()["wind"]
    subject = extract.load_subject(subject_id)
    files = sorted((out_dir / subject_id).glob("*.npz"))
    if not files:
        raise SystemExit(f"no cached patches for {subject_id}, run extract first")
    metas = [extract.load_patch(f)[3] for f in files]
    from orbyt.sources import gee

    gee.init()
    hours = [int(_day_plan(subject.lat, subject.lon, m, cfg)[3].timestamp() * 1000) for m in metas]
    winds = extract._retry(lambda: era5_winds(subject.lat, subject.lon, hours, cfg=cfg))
    rows = build_day_winds(subject.lat, subject.lon, metas, winds, cfg=cfg)
    path = write_winds(wind_path(out_dir, subject_id), subject_id, rows, cfg)
    missing = sum(r.speed_ms is None for r in rows)
    sun = sum(r.pass_source == "solar-geometry" for r in rows)
    speeds = np.array([r.speed_ms for r in rows if r.speed_ms is not None])
    log(f"{len(rows)} days, {sun} with a sun based pass time, {missing} without wind")
    if len(speeds):
        log(
            f"wind speed m/s: median {np.median(speeds):.1f}, min {speeds.min():.1f}, "
            f"max {speeds.max():.1f}"
        )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="ERA5 100 m wind at the pass time, per day")
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    print(f"wrote {winds_for_subject(args.subject_id, args.out_dir)}")


if __name__ == "__main__":
    main()
