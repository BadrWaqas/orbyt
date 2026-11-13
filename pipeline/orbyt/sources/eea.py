"""EEA Industrial Reporting database (v16) loader: reported NOx to air for European facilities.

M1.5: download the user friendly CSV bundle, load the facility air release table into DuckDB,
build ``facilities``, ``reported`` and ``coverage``, and export the 300 largest 2024 reporters as
``findings.json`` with reported values only (nothing from satellites yet).
M1.6: next to it, one ``finding/<id>.json`` per finding with every year that facility reported.

    uv run python -m orbyt.sources.eea

What the v16 CSVs hold, checked against the real files:
- ``F1_4_Air_Releases_Facilities.csv`` has one row per facility, year and pollutant. Releases are
  in kilograms. NOx is "Nitrogen oxides (NOX)", expressed as NO2.
- There is no measured, calculated or estimated column in the CSV bundle. The method code is not
  published there, so ``claimed.basis`` is "unknown" until another source supplies it.
- Some countries have not reported 2024 yet. See the ``coverage`` table. Their facilities are
  kept at the country's latest year, and each finding's ``period`` says which year that is.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

import duckdb

SOURCE = "EEA Industrial Reporting database v16"
SHARE_TOKEN = "sptXqwkQr5g7Bp5"  # public EEA download share, used as the WebDAV user name
ZIP_URL = (
    "https://sdi.eea.europa.eu/datashare/public.php/webdav/"
    "eea_t_ied-eprtr_p_2007-2024_v16_r00/User%20friendly%20.csv%20files.zip"
)
FACILITY_CSV = "F1_4_Air_Releases_Facilities.csv"
NOX = "Nitrogen oxides (NOX)"

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "eea_v16"
WAREHOUSE_DIR = REPO_ROOT / "data" / "warehouse"
DEFAULT_FINDINGS = (
    REPO_ROOT / "web" / "public" / "data" / "v1" / "pollution-hunter" / "findings.json"
)

COUNTRY_ISO2 = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY",
    "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE", "Finland": "FI", "France": "FR",
    "Germany": "DE", "Greece": "GR", "Hungary": "HU", "Iceland": "IS", "Ireland": "IE",
    "Italy": "IT", "Latvia": "LV", "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT",
    "Netherlands": "NL", "Norway": "NO", "Poland": "PL", "Portugal": "PT", "Romania": "RO",
    "Serbia": "RS", "Slovakia": "SK", "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
    "Switzerland": "CH", "United Kingdom": "GB",
}  # fmt: skip


def _zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return FACILITY_CSV in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def download(raw_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Fetch the CSV bundle (about 148 MB) and extract the facility air release table."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "csv_files.zip"
    if force or not _zip_ok(zip_path):
        auth = base64.b64encode(f"{SHARE_TOKEN}:".encode()).decode()
        req = urllib.request.Request(ZIP_URL, headers={"Authorization": f"Basic {auth}"})
        tmp = zip_path.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
        tmp.replace(zip_path)
        if not _zip_ok(zip_path):
            raise RuntimeError(f"{zip_path} is not a valid bundle")
    csv_path = raw_dir / FACILITY_CSV
    if force or not csv_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extract(FACILITY_CSV, raw_dir)
    return csv_path


def load(csv_path: Path, con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Build the ``facilities``, ``reported`` and ``coverage`` tables from the facility CSV."""
    path = str(csv_path).replace("\\", "/").replace("'", "''")
    con.execute(
        f"""
        create or replace temp table raw_nox as
        select * from read_csv('{path}', all_varchar=true, sample_size=-1)
        where Pollutant = '{NOX}' and TargetRelease = 'AIR'
        """
    )
    con.execute(
        """
        create or replace table reported as
        select FacilityInspireId as facility_id,
               countryName as country,
               cast(reportingYear as integer) as year,
               cast(Releases as double) as release_kg,
               cast(Releases as double) / 1000.0 as release_t
        from raw_nox
        where try_cast(Releases as double) is not null
        """
    )
    con.execute(
        """
        create or replace table facilities as
        select FacilityInspireId as facility_id,
               arg_max(trim(facilityName), cast(reportingYear as integer)) as name,
               arg_max(trim(city), cast(reportingYear as integer)) as city,
               arg_max(countryName, cast(reportingYear as integer)) as country,
               arg_max(EPRTR_SectorCode, cast(reportingYear as integer)) as sector_code,
               arg_max(EPRTR_SectorName, cast(reportingYear as integer)) as sector,
               arg_max(EPRTRAnnexIMainActivity, cast(reportingYear as integer)) as activity,
               arg_max(try_cast(Longitude as double), cast(reportingYear as integer))
                   filter (where try_cast(Longitude as double) is not null
                           and try_cast(Latitude as double) is not null) as lon,
               arg_max(try_cast(Latitude as double), cast(reportingYear as integer))
                   filter (where try_cast(Longitude as double) is not null
                           and try_cast(Latitude as double) is not null) as lat
        from raw_nox
        group by FacilityInspireId
        """
    )
    con.execute(
        """
        create or replace table coverage as
        with m as (
            select country, min(year) as first_year, max(year) as last_year
            from reported group by country
        )
        select m.country, m.first_year, m.last_year,
               (select count(*) from reported r
                where r.country = m.country and r.year = m.last_year) as n_facilities_last_year
        from m order by m.country
        """
    )
    return con


def write_warehouse(con: duckdb.DuckDBPyConnection, out_dir: Path = WAREHOUSE_DIR) -> None:
    """Export the three tables as Parquet next to the DuckDB file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for table in ("facilities", "reported", "coverage"):
        target = str(out_dir / f"eea_{table}.parquet").replace("\\", "/")
        con.execute(f"copy {table} to '{target}' (format parquet)")


MIN_FALLBACK_YEAR = 2022  # older latest years (UK 2019, Norway 2017, Iceland 2007) are dropped


def top_reporters(
    con: duckdb.DuckDBPyConnection, year: int, n: int, min_year: int = MIN_FALLBACK_YEAR
) -> list[dict]:
    """The n largest NOx reporters that have usable coordinates.

    Each facility is taken at ``year``, or at its country's latest reported year when that
    country has not reported ``year`` yet. Rows older than ``min_year`` are left out before the
    cut to n, so the list is refilled with the next largest. The row carries the year used.
    """
    rows = con.execute(
        """
        select f.facility_id, f.name, f.city, f.country, f.sector, f.lon, f.lat,
               r.release_t, r.year
        from reported r
        join facilities f using (facility_id)
        join coverage c on c.country = r.country and r.year = least(c.last_year, ?)
        where f.lon between -180 and 180 and f.lat between -90 and 90
          and r.year >= ?
        order by r.release_t desc, f.facility_id
        limit ?
        """,
        [year, min_year, n],
    ).fetchall()
    keys = ("register_id", "name", "city", "country", "sector", "lon", "lat", "release_t", "year")
    return [dict(zip(keys, row, strict=True)) for row in rows]


def subject_id(register_id: str) -> str:
    """Stable id derived from the register's own identifier, not from rank."""
    return "ph-eu-" + hashlib.sha1(register_id.encode("utf-8")).hexdigest()[:8]


def build_findings(rows: list[dict], year: int) -> dict:
    """findings.json payload (PLAN.md Appendix B) with the reported side only.

    ``year`` is the target year. A row from a country that has not reported it carries its own
    year in ``period`` and a note saying so, and the country is listed in ``latest_year_countries``.
    """
    findings = []
    latest_year_countries: dict[str, int] = {}
    for r in rows:
        y = r["year"]
        iso = COUNTRY_ISO2.get(r["country"], r["country"])
        period = {"label": str(y), "start": f"{y}-01-01", "end": f"{y}-12-31"}
        if y != year:
            period["note"] = f"Latest year reported by {r['country']}. No {year} data."
            latest_year_countries[iso] = y
        findings.append(
            {
                "id": f"{subject_id(r['register_id'])}-{y}",
                "module": "pollution-hunter",
                "subject": {
                    "id": subject_id(r["register_id"]),
                    "kind": "facility",
                    "name": r["name"],
                    "operator": None,
                    "sector": r["sector"],
                    "country": iso,
                    "city": r["city"],
                    "lat": round(r["lat"], 5),
                    "lon": round(r["lon"], 5),
                    "register": "EEA",
                    "register_id": r["register_id"],
                },
                "period": period,
                "claimed": {
                    "value": round(r["release_t"], 1),
                    "unit": "t NOx/yr",
                    "basis": "unknown",
                    "source": SOURCE,
                },
                "observed": None,
                "ratio": None,
                "verdict": None,
                "grade": None,
            }
        )
    return {
        "module": "pollution-hunter",
        "period": str(year),
        "source": SOURCE,
        "count": len(findings),
        "latest_year_countries": dict(sorted(latest_year_countries.items())),
        "findings": findings,
    }


def reported_series(
    con: duckdb.DuckDBPyConnection, register_ids: list[str]
) -> dict[str, list[dict]]:
    """Every reported year for the given facilities, oldest first. Years not reported are absent."""
    rows = con.execute(
        """
        select facility_id, year, release_t
        from reported
        where facility_id in (select unnest(?))
        order by facility_id, year
        """,
        [register_ids],
    ).fetchall()
    series: dict[str, list[dict]] = {rid: [] for rid in register_ids}
    for register_id, year, release_t in rows:
        series[register_id].append(
            {"year": year, "value": round(release_t, 1), "basis": "unknown"}
        )
    return series


def export_details(con: duckdb.DuckDBPyConnection, payload: dict, out_dir: Path) -> int:
    """One ``<finding id>.json`` per finding with its reported series (PLAN.md Appendix B).

    The panel fetches these one at a time, so findings.json stays small. Detail files left over
    from an earlier export that are no longer in ``payload`` are removed.
    """
    findings = payload["findings"]
    series = reported_series(con, [f["subject"]["register_id"] for f in findings])
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {f"{f['id']}.json" for f in findings}
    for stale in out_dir.glob("*.json"):
        if stale.name not in wanted:
            stale.unlink()
    for f in findings:
        detail = {
            "id": f["id"],
            "reported_series": series[f["subject"]["register_id"]],
            "sources": [SOURCE],
        }
        text = json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n"
        (out_dir / f"{f['id']}.json").write_text(text, encoding="utf-8")
    return len(findings)


def export_findings(
    con: duckdb.DuckDBPyConnection, year: int = 2024, n: int = 300, out: Path = DEFAULT_FINDINGS
) -> Path:
    """Write findings.json and, next to it, the ``finding/`` folder of detail files."""
    payload = build_findings(top_reporters(con, year, n), year)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    export_details(con, payload, out.parent / "finding")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Load EEA v16 reported NOx and export findings")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--top", type=int, default=300)
    parser.add_argument("--out", type=Path, default=DEFAULT_FINDINGS)
    args = parser.parse_args()
    csv_path = download()
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_DIR / "orbyt.duckdb"))
    load(csv_path, con)
    write_warehouse(con)
    out = export_findings(con, args.year, args.top, args.out)
    n_fac = con.execute("select count(*) from facilities").fetchone()[0]
    n_year = con.execute("select count(*) from reported where year = ?", [args.year]).fetchone()[0]
    print(f"{n_fac} facilities, {n_year} reported in {args.year}. Wrote {out}")
    missing = con.execute(
        "select country, last_year from coverage where last_year < ? order by country", [args.year]
    ).fetchall()
    print(
        f"Latest year used where {args.year} is missing:",
        ", ".join(f"{c} ({y})" for c, y in missing),
    )


if __name__ == "__main__":
    main()
