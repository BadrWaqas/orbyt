"""EPA National Emissions Inventory 2023: point-source NOx the stack monitors do not see (M4.4).

    uv run python -m orbyt.sources.nei fetch

Why: the US ground truth of M4.3 is the sum of the CEMS power plants in a footprint, but the
satellite sees every source in it. Refineries, chemical works, kilns and compressor stations
report nothing to CEMS. The NEI lists them, so the validation can compare the satellite with the
whole footprint, which is the same accounting as the European register (PLAN.md 4.5).

What the file holds, checked against the real file (2023 NEI facility summary, July 2026):
- One row per facility and pollutant. ``pollutant code`` NOX is nitrogen oxides as NO2, the same
  convention as CEMS and the satellite estimate. ``total emissions`` is in short tons (``TON``).
- Power plants are in it too. In 30 of the 33 validation footprints the NEI power-plant total
  matches the CEMS total of 2023 within 5%. The NEI is lower at Sabine (11%) and R S Nelson
  (18%), and higher at Midland, where it lists the Midland Cogeneration Venture at 6,181 t
  against 3,240 t in CEMS (docs/decisions.md, M4.4).
- One inventory year. 2023 is used for both 2023 and 2024, which assumes industry changes little
  from one year to the next.

The data is EPA's (US government work). Credit EPA (DATA_LICENSES.md).
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np

from orbyt.core.geo import haversine_km

NEI_YEAR = 2023
URL = (
    "https://gaftp.epa.gov/air/nei/2023/data_summaries/"
    "eis_report_38234_2023NEI_facility_summary_21jul2026.zip"
)
SOURCE = "EPA 2023 National Emissions Inventory, facility summary (21 July 2026)"
SHORT_TON_T = 0.90718474
# NAICS 2211xx is electric power generation. Those plants are the ones CEMS monitors.
POWER_NAICS_PREFIX = "2211"

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "nei2023"


def csv_path(raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / "emis_sum_fac_38234.csv"


def fetch(raw_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Download the facility summary (39 MB zip) and unpack its CSV. Skipped if present."""
    out = csv_path(raw_dir)
    if out.exists() and not force:
        return out
    raw_dir.mkdir(parents=True, exist_ok=True)
    zpath = raw_dir / "facility_summary.zip"
    with urllib.request.urlopen(URL, timeout=600) as resp, zpath.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    with zipfile.ZipFile(zpath) as z:
        z.extract(out.name, raw_dir)
    return out


@dataclass(frozen=True)
class Facilities:
    """NOx point sources: name, NAICS, position and tonnes per year (NOx as NO2)."""

    name: list[str]
    naics: list[str]
    lat: np.ndarray
    lon: np.ndarray
    nox_t: np.ndarray

    @property
    def power(self) -> np.ndarray:
        return np.array([n.startswith(POWER_NAICS_PREFIX) for n in self.naics], dtype=bool)


def load_facilities(path: Path | None = None) -> Facilities:
    """Every NEI facility with a NOx total and coordinates."""
    path = path or csv_path()
    rows = (
        duckdb.connect()
        .execute(
            f"""
            select "site name", cast("primary naics code" as varchar), "site latitude",
                   "site longitude", "emissions uom", sum("total emissions")
            from read_csv_auto('{path.as_posix()}', sample_size=-1)
            where "pollutant code" = 'NOX' and "site latitude" is not null
            group by all
            """
        )
        .fetchall()
    )
    units = {r[4] for r in rows}
    if units - {"TON"}:
        raise ValueError(f"unexpected NOx units in the NEI file: {units}")
    return Facilities(
        name=[r[0] or "" for r in rows],
        naics=[r[1] or "" for r in rows],
        lat=np.array([r[2] for r in rows], dtype=float),
        lon=np.array([r[3] for r in rows], dtype=float),
        nox_t=np.array([r[5] for r in rows], dtype=float) * SHORT_TON_T,
    )


def footprint(
    fac: Facilities, lat: float, lon: float, radius_km: float, cems_t: float, top: int = 3
) -> dict:
    """NOx inside the footprint that the CEMS total misses.

    ``other_t``: every facility that is not a power plant. ``power_gap_t``: NEI power plants
    above the CEMS total of the same year (a unit CEMS does not cover), never below zero.
    ``unmonitored_t`` is their sum. ``largest`` names the biggest non-power sources.
    """
    d = haversine_km(lat, lon, fac.lat, fac.lon)
    inside = d <= radius_km
    power = fac.power
    other = inside & ~power
    other_t = float(fac.nox_t[other].sum())
    power_t = float(fac.nox_t[inside & power].sum())
    gap = max(0.0, power_t - cems_t)
    idx = np.where(other)[0]
    idx = idx[np.argsort(-fac.nox_t[idx])][:top]
    return {
        "other_t": other_t,
        "power_nei_t": power_t,
        "power_gap_t": gap,
        "unmonitored_t": other_t + gap,
        "largest": [
            {"name": fac.name[i], "nox_t": float(fac.nox_t[i]), "km": float(d[i])} for i in idx
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="EPA NEI 2023 facility NOx")
    parser.add_argument("command", choices=["fetch"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    out = fetch(force=args.force)
    fac = load_facilities(out)
    print(f"{out}: {len(fac.name):,} NOx facilities, {fac.nox_t.sum() / 1e6:.2f} Mt ({SOURCE})")


if __name__ == "__main__":
    main()
