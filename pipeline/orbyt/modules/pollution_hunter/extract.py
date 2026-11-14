"""Pollution Hunter extraction (M3.2): usable overpasses and NO2 patches for one subject.

For one facility this lists the Sentinel-5P overpasses worth downloading, using a filter that runs
on the Earth Engine server (PLAN.md 4.3 step 2), then downloads one NO2 patch per day and caches
it as a compressed NPZ file under ``data/interim/<subject id>/``.

    uv run python -m orbyt.modules.pollution_hunter.extract --subject-id ph-eu-xxxxxxxx

A cached day holds ``field`` (float32 [lat, lon], NaN = no data), ``lats`` and ``lons`` (ascending
cell centres) and ``meta`` (JSON: image id, image start and end in ms, solar and sensor zenith
and solar azimuth at the source, valid fraction within the check radius).

One image covers about an hour of satellite track, so its start time is not the moment the
satellite passed over the source. era5.py works out the pass time from the sun's geometry at the
source instead, and checks that it falls between the image's start and end.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import ee
import numpy as np

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.modules.pollution_hunter.core_math import EARTH_R_KM
from orbyt.sources import eea, gee

INTERIM_DIR = gee.REPO_ROOT / "data" / "interim"
WAREHOUSE_DB = gee.REPO_ROOT / "data" / "warehouse" / "orbyt.duckdb"

SOLAR_ZENITH = "solar_zenith_angle"
SENSOR_ZENITH = "sensor_zenith_angle"
SOLAR_AZIMUTH = "solar_azimuth_angle"

Fetcher = Callable[[str, np.ndarray, np.ndarray, float], np.ndarray]


@dataclass(frozen=True)
class Subject:
    """One facility to measure."""

    subject_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Overpass:
    """One usable Sentinel-5P image over the source, with the numbers the filter used."""

    image_id: str
    start_ms: int
    end_ms: int | None
    sza: float  # solar zenith angle at the source, degrees
    vza: float  # sensor zenith angle at the source, degrees
    saa: float  # solar azimuth at the source, degrees from north, negative when west of it
    valid_frac: float  # share of pixels with data within the check radius

    @property
    def day(self) -> date:
        """UTC date of the image start. An hour of track never straddles a day over Europe."""
        return datetime.fromtimestamp(self.start_ms / 1000, UTC).date()


def overpass_from_properties(props: dict[str, Any]) -> Overpass | None:
    """Build an Overpass from server feature properties, or None if a number is missing."""
    keys = ("start", "sza", "vza", "saa", "valid")
    if any(props.get(k) is None for k in keys):
        return None
    end = props.get("end")
    return Overpass(
        image_id=props["id"],
        start_ms=int(props["start"]),
        end_ms=None if end is None else int(end),
        sza=float(props["sza"]),
        vza=float(props["vza"]),
        saa=float(props["saa"]),
        valid_frac=float(props["valid"]),
    )


def one_per_day(overpasses: list[Overpass]) -> list[Overpass]:
    """Keep one image per UTC day, the one viewed closest to straight down (smallest sensor
    zenith). Two images on one day only happen where adjacent orbits overlap at the edge."""
    by_day: dict[date, list[Overpass]] = defaultdict(list)
    for op in overpasses:
        by_day[op.day].append(op)
    return [min(ops, key=lambda o: (o.vza, o.start_ms)) for _, ops in sorted(by_day.items())]


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end) into pieces that never cross a month boundary."""
    pieces = []
    cur = start
    while cur < end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        pieces.append((cur, min(nxt, end)))
        cur = nxt
    return pieces


def patch_grid(
    lat0: float, lon0: float, half_km: float, step: float
) -> tuple[np.ndarray, np.ndarray]:
    """Ascending cell-centre latitudes and longitudes, centred on the source.

    The source sits in the middle cell. Longitude cells cover the same distance as latitude
    cells at the source's latitude, so the patch is roughly square on the ground.
    """
    lat_half = math.degrees(half_km / EARTH_R_KM)
    lon_half = math.degrees(half_km / (EARTH_R_KM * math.cos(math.radians(lat0))))
    n_lat, n_lon = round(lat_half / step), round(lon_half / step)
    return (
        lat0 + step * np.arange(-n_lat, n_lat + 1),
        lon0 + step * np.arange(-n_lon, n_lon + 1),
    )


def pixel_request(expression: Any, lats: np.ndarray, lons: np.ndarray, step: float) -> dict:
    """The ``computePixels`` request for a lat/lon grid. Rows come back north first."""
    return {
        "expression": expression,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": len(lons), "height": len(lats)},
            "affineTransform": {
                "scaleX": step,
                "shearX": 0,
                "translateX": float(lons[0] - step / 2),
                "shearY": 0,
                "scaleY": -step,
                "translateY": float(lats[-1] + step / 2),
            },
            "crsCode": "EPSG:4326",
        },
    }


def fetch_patch(image_id: str, lats: np.ndarray, lons: np.ndarray, step: float) -> np.ndarray:
    """One overpass as float32 [lat ascending, lon ascending], NaN where there is no data."""
    image = ee.Image(f"{gee.COLLECTION}/{image_id}")
    request = pixel_request(image.select(gee.BAND).unmask(gee.NODATA), lats, lons, step)
    arr = ee.data.computePixels(request)[gee.BAND].astype("float32")
    if arr.shape != (len(lats), len(lons)):
        raise ValueError(f"{image_id}: expected {(len(lats), len(lons))}, got {arr.shape}")
    arr[arr == gee.NODATA] = np.nan
    return np.ascontiguousarray(arr[::-1, :])


def patch_path(out_dir: Path, subject_id: str, op: Overpass) -> Path:
    return out_dir / subject_id / f"{op.day:%Y%m%d}_{op.image_id}.npz"


def save_patch(
    path: Path, field: np.ndarray, lats: np.ndarray, lons: np.ndarray, op: Overpass
) -> None:
    """Write one day to disk. Goes through a temp file so a crash never leaves half a patch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as fh:
        np.savez_compressed(
            fh,
            field=field.astype("float32"),
            lats=lats,
            lons=lons,
            meta=np.array(json.dumps(asdict(op))),
        )
    tmp.replace(path)


def load_patch(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """The inverse of save_patch: field, lats, lons, meta."""
    with np.load(path) as z:
        return z["field"], z["lats"], z["lons"], json.loads(str(z["meta"]))


# --- Earth Engine cost -----------------------------------------------------------------------


def parse_eecu_seconds(profile_text: str) -> float:
    """Total EECU-seconds in an Earth Engine profile table.

    The first column of each row is the cost of that step in EECU-seconds, or a dash when it is
    below the table's resolution.
    """
    total = 0.0
    for line in profile_text.splitlines():
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s", line)
        if m:
            total += float(m.group(1))
    return total


@dataclass(frozen=True)
class EecuCost:
    """What a set of Earth Engine calls cost, as far as their profiles could be read."""

    measured_s: float  # EECU-seconds of the calls whose profile was found
    n_calls: int
    n_found: int  # calls whose profile was found. Some calls have none stored.

    @property
    def estimated_s(self) -> float:
        """Cost of all calls, taking the calls with no profile to cost the average of the rest."""
        return self.measured_s * self.n_calls / self.n_found if self.n_found else 0.0


class EecuMeter:
    """Collects Earth Engine profile ids from many threads and totals their cost."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self._lock = threading.Lock()

    def hook(self, profile_id: str) -> None:
        with self._lock:
            self.ids.append(profile_id)

    def cost(self, attempts: int = 3, wait_s: float = 3.0, workers: int = 8) -> EecuCost:
        """Read each call's profile on its own. A profile can appear a moment after its call,
        and some calls never get one, so a missing profile is counted rather than treated as an
        error. Any other failure is raised."""
        get_profiles = ee.apifunction.ApiFunction.lookup("Profile.getProfiles")

        def read(profile_id: str) -> float | None:
            for attempt in range(1, attempts + 1):
                try:
                    return parse_eecu_seconds(get_profiles.call(ids=[profile_id]).getInfo())
                except ee.EEException as exc:
                    missing = "not found" in str(exc)
                    if attempt == attempts:
                        if missing:
                            return None
                        raise
                    time.sleep(wait_s)
            raise AssertionError("unreachable")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            found = [s for s in pool.map(read, self.ids) if s is not None]
        return EecuCost(sum(found), len(self.ids), len(found))


def _profiled(meter: EecuMeter | None):
    return ee.data.profiling(meter.hook) if meter else contextlib.nullcontext()


def _retry[T](fn: Callable[[], T], attempts: int = 4, wait_s: float = 5.0) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except ee.EEException:
            if attempt == attempts:
                raise
            time.sleep(wait_s * attempt)
    raise AssertionError("unreachable")


# --- Listing usable overpasses -------------------------------------------------------------


def _month_overpasses(
    lat: float, lon: float, start: date, end: date, cfg: dict[str, Any]
) -> list[Overpass]:
    """Usable images over the source in [start, end). The filter runs on the server."""
    scale = cfg["reduce_scale_m"]
    point = ee.Geometry.Point([lon, lat])
    disc = point.buffer(cfg["valid_radius_km"] * 1000)

    def annotate(img: ee.Image) -> ee.Image:
        angles = img.select([SOLAR_ZENITH, SENSOR_ZENITH, SOLAR_AZIMUTH]).reduceRegion(
            ee.Reducer.first(), point, scale
        )
        # The mask is 0 outside the image footprint, so its mean is the share of the disc with data.
        valid = img.select(gee.BAND).mask().reduceRegion(ee.Reducer.mean(), disc, scale)
        return img.set(
            {
                "sza": angles.get(SOLAR_ZENITH),
                "vza": angles.get(SENSOR_ZENITH),
                "saa": angles.get(SOLAR_AZIMUTH),
                "valid": valid.get(gee.BAND),
            }
        )

    usable = (
        ee.ImageCollection(gee.COLLECTION)
        .filterDate(start.isoformat(), end.isoformat())
        .filterBounds(point)
        .map(annotate)
        .filter(
            ee.Filter.And(
                ee.Filter.lte("sza", cfg["max_solar_zenith_deg"]),
                ee.Filter.lte("vza", cfg["max_sensor_zenith_deg"]),
                ee.Filter.gte("valid", cfg["min_valid_frac"]),
            )
        )
    )
    features = ee.FeatureCollection(
        usable.map(
            lambda i: ee.Feature(
                None,
                {
                    "id": i.id(),
                    "start": i.get("system:time_start"),
                    "end": i.get("system:time_end"),
                    "sza": i.get("sza"),
                    "vza": i.get("vza"),
                    "saa": i.get("saa"),
                    "valid": i.get("valid"),
                },
            )
        )
    )
    rows = features.getInfo()["features"]
    return [op for r in rows if (op := overpass_from_properties(r["properties"])) is not None]


def list_overpasses(
    lat: float,
    lon: float,
    start: date,
    end: date,
    meter: EecuMeter | None = None,
    cfg: dict[str, Any] | None = None,
    log: Callable[[str], None] = print,
) -> list[Overpass]:
    """Every usable image over the source in [start, end), one server call per month."""
    cfg = cfg or load_config()["extract"]
    found: dict[str, Overpass] = {}
    for a, b in month_ranges(start, end):
        with _profiled(meter):
            ops = _retry(lambda a=a, b=b: _month_overpasses(lat, lon, a, b, cfg))
        found.update({op.image_id: op for op in ops})
        log(f"{a:%Y-%m}: {len(ops)} usable images")
    return sorted(found.values(), key=lambda o: o.start_ms)


# --- One subject, end to end ---------------------------------------------------------------


@dataclass
class ExtractResult:
    subject_id: str
    start: date
    end: date
    n_overpasses: int  # usable images found by the server-side filter
    n_days: int  # after keeping one image per day
    n_downloaded: int
    n_cached: int
    listing_cost: EecuCost | None  # None when the listing was not measured
    patch_cost: EecuCost | None  # None when no patch was downloaded in this call
    paths: list[Path]


MODULE_DIR = Path(__file__).parent
# Subjects that are not EEA facilities live in a JSON list next to this file, keyed by id prefix:
# the US validation plants (M4.2) and the empty sites of the null test (M4.5).
SUBJECT_FILES = {
    "ph-us-": MODULE_DIR / "validation_plants.json",
    "ph-null-": MODULE_DIR / "null_sites.json",
}


def load_subject(subject_id: str, db_path: Path = WAREHOUSE_DB) -> Subject:
    """Find a subject by its id: ``ph-eu-...`` in the EEA warehouse, the others in their file."""
    for prefix, path in SUBJECT_FILES.items():
        if subject_id.startswith(prefix):
            for row in json.loads(path.read_text(encoding="utf-8")):
                if row["subject_id"] == subject_id:
                    return Subject(subject_id, row["name"], float(row["lat"]), float(row["lon"]))
            raise KeyError(f"{subject_id} is not in {path.name}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "select facility_id, name, lat, lon from facilities "
            "where lat is not null and lon is not null"
        ).fetchall()
    finally:
        con.close()
    for facility_id, name, lat, lon in rows:
        if eea.subject_id(facility_id) == subject_id:
            return Subject(subject_id, name, float(lat), float(lon))
    raise KeyError(f"no facility with id {subject_id}")


def extract_subject(
    subject: Subject,
    start: date,
    end: date,
    *,
    out_dir: Path = INTERIM_DIR,
    workers: int = 4,
    limit: int | None = None,
    measure_eecu: bool = True,
    lister: Callable[..., list[Overpass]] = list_overpasses,
    fetcher: Fetcher = fetch_patch,
    cfg: dict[str, Any] | None = None,
    log: Callable[[str], None] = print,
) -> ExtractResult:
    """List usable overpasses for [start, end), download one patch per day, cache as NPZ.

    ``limit`` stops after that many days, for a quick trial. ``measure_eecu`` totals the Earth
    Engine cost of the listing and of the downloads that actually ran in this call.
    """
    cfg = cfg or load_config()["extract"]
    step = cfg["grid_step_deg"]
    lats, lons = patch_grid(subject.lat, subject.lon, cfg["half_extent_km"], step)
    patch_meter = EecuMeter() if measure_eecu else None

    # The listing is cached with its own cost, so a later run still knows what it took.
    listing = out_dir / subject.subject_id / f"overpasses_{start}_{end}.json"
    listing_cost: EecuCost | None = None
    if listing.exists():
        raw = json.loads(listing.read_text(encoding="utf-8"))
        ops = [Overpass(**r) for r in raw["overpasses"]]
        if raw.get("listing_cost"):
            listing_cost = EecuCost(**raw["listing_cost"])
        log(f"listing read from {listing.name}: {len(ops)} usable images")
    else:
        list_meter = EecuMeter() if measure_eecu else None
        ops = lister(subject.lat, subject.lon, start, end, list_meter, cfg=cfg, log=log)
        if list_meter is not None and list_meter.ids:
            listing_cost = list_meter.cost()
        listing.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "filters": cfg,
            "listing_cost": asdict(listing_cost) if listing_cost else None,
            "overpasses": [asdict(o) for o in ops],
        }
        listing.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    days = one_per_day(ops)
    if limit is not None:
        days = days[:limit]

    def work(op: Overpass) -> tuple[Path, bool]:
        path = patch_path(out_dir, subject.subject_id, op)
        if path.exists():
            return path, False
        with _profiled(patch_meter):
            field = _retry(lambda: fetcher(op.image_id, lats, lons, step))
        save_patch(path, field, lats, lons, op)
        return path, True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = list(pool.map(work, days))
    paths = [p for p, _ in done]
    n_new = sum(fresh for _, fresh in done)
    log(f"{len(days)} days: {n_new} downloaded, {len(days) - n_new} already cached")

    patch_cost = patch_meter.cost() if patch_meter and patch_meter.ids else None
    return ExtractResult(
        subject_id=subject.subject_id,
        start=start,
        end=end,
        n_overpasses=len(ops),
        n_days=len(one_per_day(ops)),
        n_downloaded=n_new,
        n_cached=len(days) - n_new,
        listing_cost=listing_cost,
        patch_cost=patch_cost,
        paths=paths,
    )


def write_cost_summary(
    subject: Subject, result: ExtractResult, out_dir: Path = INTERIM_DIR
) -> Path | None:
    """Record what the run cost in ``extract_summary.json`` next to the patches.

    Only written when the listing cost and this call's download cost are both known, so a rerun
    that served every patch from the cache never overwrites a real measurement with zeros.
    """
    listing, patches = result.listing_cost, result.patch_cost
    if listing is None or patches is None:
        return None
    total_s = listing.estimated_s + patches.estimated_s
    quota_h = load_config()["quota"]["community_eecu_hours"]
    summary = {
        "subject_id": subject.subject_id,
        "name": subject.name,
        "lat": subject.lat,
        "lon": subject.lon,
        "window": [result.start.isoformat(), result.end.isoformat()],
        "filters": load_config()["extract"],
        "usable_images_listed": result.n_overpasses,
        "days_after_one_per_day": result.n_days,
        "patches_downloaded": result.n_downloaded,
        "eecu_seconds": {
            "listing": round(listing.estimated_s, 1),
            "patches": round(patches.estimated_s, 1),
            "total": round(total_s, 1),
        },
        # Earth Engine stores no profile for some calls. The totals above scale the calls that
        # have one up to all calls, so these counts show how much of the total was read directly.
        "profiles_found": {
            "listing": f"{listing.n_found} of {listing.n_calls}",
            "patches": f"{patches.n_found} of {patches.n_calls}",
        },
        "eecu_hours_total": round(total_s / 3600, 4),
        "share_of_community_quota": round(total_s / 3600 / quota_h, 5),
    }
    path = out_dir / subject.subject_id / "extract_summary.json"
    path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NO2 patches for one facility")
    parser.add_argument("--subject-id", required=True, help="published id, for example ph-eu-...")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--to", dest="end", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, help="stop after this many days (trial run)")
    parser.add_argument("--out-dir", type=Path, default=INTERIM_DIR)
    args = parser.parse_args()

    gee.init()
    subject = load_subject(args.subject_id)
    print(f"{subject.subject_id}: {ascii(subject.name)} at {subject.lat:.5f}, {subject.lon:.5f}")
    result = extract_subject(
        subject, args.start, args.end, out_dir=args.out_dir, workers=args.workers, limit=args.limit
    )
    print(
        f"{result.n_overpasses} usable images, {result.n_days} days, "
        f"{result.n_downloaded} downloaded, {result.n_cached} cached"
    )
    listing, patches = result.listing_cost, result.patch_cost
    if listing is not None and patches is not None:
        total = listing.estimated_s + patches.estimated_s
        print(
            f"EECU-seconds: listing {listing.estimated_s:.1f} "
            f"({listing.n_found} of {listing.n_calls} profiles read), patches "
            f"{patches.estimated_s:.1f} ({patches.n_found} of {patches.n_calls}), "
            f"total {total:.1f} ({total / 3600:.4f} EECU-hours)"
        )
        summary = write_cost_summary(subject, result, args.out_dir)
        print(f"cost recorded in {summary}")


if __name__ == "__main__":
    main()
