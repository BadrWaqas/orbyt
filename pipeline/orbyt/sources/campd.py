"""EPA CAMPD hourly stack monitor data (CEMS) for US power plants, the ground truth of M4.

M4.1: US plants with hourly NOx mass measured at the stack, 2023 and 2024.

    uv run python -m orbyt.sources.campd fetch
    uv run python -m orbyt.sources.campd annual

Where the data comes from, and why it is not the CAMPD API:
- The CAMPD API and its bulk files need an api.data.gov key, which this project does not have.
- The Public Utility Data Liberation project (PUDL, Catalyst Cooperative) republishes the same
  EPA hourly file as Parquet in a public bucket, with the EIA plant id and coordinates joined on.
  DuckDB reads only the rows and columns asked for over HTTP, so nothing is downloaded in full.
- The release is pinned in ``PUDL_RELEASE``. The data is EPA's. Credit EPA CAMD, and PUDL for
  the republication (DATA_LICENSES.md).

What the hourly table holds, checked against the real file (release v2026.11.0):
- One row per emissions unit and hour. ``nox_mass_lbs`` is pounds of NOx expressed as NO2, which
  is the same convention as the EEA register and the satellite estimate. It is empty for hours a
  unit did not report, and ``operating_time_hours`` is 0 for hours it was off.
- ``operating_datetime_utc`` is the start of the hour in UTC.
- ``plant_id_eia`` joins to the EIA plant table for coordinates. A few units have no EIA id and
  are dropped, because they cannot be placed on a map.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

PUDL_RELEASE = "v2026.11.0"
BASE_URL = f"https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/{PUDL_RELEASE}/"
HOURLY_URL = BASE_URL + "core_epacems__hourly_emissions.parquet"
PLANTS_URL = BASE_URL + "core_eia__entity_plants.parquet"
SOURCE = f"EPA CAMPD hourly emissions, via PUDL {PUDL_RELEASE}"

LB_TO_KG = 0.45359237
YEARS = (2023, 2024)

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "campd"
WAREHOUSE_DIR = REPO_ROOT / "data" / "warehouse"


def hourly_path(years: tuple[int, ...] = YEARS, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / f"hourly_nox_{'_'.join(str(y) for y in years)}.parquet"


def connect() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB that can read the public bucket over HTTP."""
    con = duckdb.connect()
    con.execute("install httpfs")
    con.execute("load httpfs")
    return con


def fetch_hourly(
    years: tuple[int, ...] = YEARS,
    raw_dir: Path = RAW_DIR,
    con: duckdb.DuckDBPyConnection | None = None,
    force: bool = False,
) -> Path:
    """Copy the hourly NOx rows of the given years for every US plant into one local Parquet.

    Columns kept: plant, unit, hour, operating time, gross load, NOx mass and its measurement
    code. Sorted by plant and hour so a single plant reads fast. Skipped if the file exists.
    """
    out = hourly_path(years, raw_dir)
    if out.exists() and not force:
        return out
    raw_dir.mkdir(parents=True, exist_ok=True)
    con = con or connect()
    tmp = out.with_suffix(".part")
    target = str(tmp).replace("\\", "/")
    year_list = ", ".join(str(int(y)) for y in years)
    con.execute(
        f"""
        copy (
            select plant_id_eia, plant_id_epa, emissions_unit_id_epa as unit_id,
                   operating_datetime_utc as hour_utc, year, operating_time_hours,
                   gross_load_mw, nox_mass_lbs, nox_mass_measurement_code
            from read_parquet('{HOURLY_URL}')
            where year in ({year_list}) and plant_id_eia is not null
            order by plant_id_eia, unit_id, operating_datetime_utc
        ) to '{target}' (format parquet, compression zstd)
        """
    )
    tmp.replace(out)
    return out


def load_plants(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    """Build the ``plants`` table (EIA id, name, state, coordinates) in the given connection."""
    con = con or connect()
    con.execute(
        f"""
        create or replace table plants as
        select plant_id_eia, plant_name_eia as name, state, county, latitude as lat,
               longitude as lon
        from read_parquet('{PLANTS_URL}')
        where latitude is not null and longitude is not null
        """
    )
    return con


def annual_nox(con: duckdb.DuckDBPyConnection, hourly: Path) -> duckdb.DuckDBPyConnection:
    """Build ``annual``: one row per plant and year with the monitored NOx total.

    ``nox_t`` is metric tonnes of NOx as NO2, summed over the hours that have a value.
    A missing NOx value almost always means the unit was off (checked: 24.95 M operating unit
    hours have a value and 0.05 M do not, against 43.9 M idle hours with none). So the gap that
    matters is ``operating_nox_missing``, the operating unit hours with no value. It is kept so a
    plant with a gappy year can be dropped from the comparison.
    ``measured_share`` is the share of the tonnes whose measurement code is Measured, or
    Measured and Substitute. The rest is Calculated (from fuel use), LME or Substitute, which are
    weaker ground truth. A unit hour that was never reported has no row and is not counted.
    """
    path = str(hourly).replace("\\", "/")
    con.execute(
        f"""
        create or replace table annual as
        select plant_id_eia, year,
               sum(nox_mass_lbs) * {LB_TO_KG} / 1000.0 as nox_t,
               sum(case when nox_mass_measurement_code in ('Measured', 'Measured and Substitute')
                        then nox_mass_lbs else 0 end) / nullif(sum(nox_mass_lbs), 0)
                   as measured_share,
               count(distinct unit_id) as n_units,
               count(*) as unit_hours,
               sum(case when operating_time_hours > 0 then 1 else 0 end) as unit_hours_operating,
               sum(case when operating_time_hours > 0 and nox_mass_lbs is null then 1 else 0 end)
                   as operating_nox_missing
        from read_parquet('{path}')
        group by plant_id_eia, year
        """
    )
    return con


def plant_hourly(con: duckdb.DuckDBPyConnection, hourly: Path, plant_id_eia: int) -> list[dict]:
    """The plant's hourly NOx, summed over its units, oldest first.

    ``nox_kg`` is NOx as NO2 for the hour. ``units_missing`` is how many units were operating
    but have no NOx value in that hour, so the caller can decide whether the hour is trustworthy.
    """
    path = str(hourly).replace("\\", "/")
    rows = con.execute(
        f"""
        select hour_utc,
               coalesce(sum(nox_mass_lbs), 0) * {LB_TO_KG} as nox_kg,
               sum(case when operating_time_hours > 0 and nox_mass_lbs is null then 1 else 0 end)
                   as units_missing,
               count(*) as units,
               coalesce(sum(gross_load_mw), 0) as gross_load_mw
        from read_parquet('{path}')
        where plant_id_eia = ?
        group by hour_utc
        order by hour_utc
        """,
        [plant_id_eia],
    ).fetchall()
    keys = ("hour_utc", "nox_kg", "units_missing", "units", "gross_load_mw")
    return [dict(zip(keys, r, strict=True)) for r in rows]


def write_annual(out_dir: Path = WAREHOUSE_DIR, years: tuple[int, ...] = YEARS) -> Path:
    """Annual NOx per plant and year, joined to EIA coordinates, as ``campd_annual.parquet``."""
    con = load_plants()
    annual_nox(con, hourly_path(years))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "campd_annual.parquet"
    target = str(out).replace("\\", "/")
    con.execute(
        f"""
        copy (
            select a.*, p.name, p.state, p.county, p.lat, p.lon
            from annual a join plants p using (plant_id_eia)
            order by a.nox_t desc
        ) to '{target}' (format parquet)
        """
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="EPA CAMPD hourly stack monitor data")
    parser.add_argument("command", choices=["fetch", "annual"])
    parser.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    years = tuple(args.years)
    if args.command == "fetch":
        out = fetch_hourly(years, force=args.force)
        n = (
            duckdb.connect()
            .execute(
                f"select count(*), count(distinct plant_id_eia) "
                f"from read_parquet('{out.as_posix()}')"
            )
            .fetchone()
        )
        print(f"{out}: {n[0]:,} unit hours, {n[1]} plants ({SOURCE})")
    else:
        out = write_annual(years=years)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
