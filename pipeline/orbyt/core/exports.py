"""Flat downloads of the published findings: findings.csv and findings.parquet (PLAN.md 2.5).

One row per finding, the same numbers as findings.json. ``FIELDS`` is the column list and the
description of each column, so the /data page and the files cannot drift apart.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

# (column, plain-language description)
FIELDS: list[tuple[str, str]] = [
    ("finding_id", "Id of the finding, also the name of its detail file"),
    ("subject_id", "Id of the facility or cluster"),
    ("kind", "facility, or cluster when the reported total sums several facilities"),
    ("name", "Name as the register gives it"),
    ("operator", "Operator, where the register gives one"),
    ("sector", "Sector, as the register gives it"),
    ("country", "Two-letter country code"),
    ("city", "City or town, where known"),
    ("lat", "Latitude of the site, degrees"),
    ("lon", "Longitude of the site, degrees"),
    ("register", "Where the reported figure comes from"),
    ("register_id", "Id in that register"),
    ("period", "Calendar year the finding covers"),
    ("reported_t", "Reported NOx in tonnes a year, as NO2 mass"),
    (
        "reported_basis",
        "How the reported value was obtained: measured, calculated, estimated, stated",
    ),
    ("estimate_t", "Satellite-based estimate of NOx in tonnes a year, as NO2 mass"),
    ("estimate_lo", "Lower end of the 95% interval"),
    ("estimate_hi", "Upper end of the 95% interval"),
    ("interval_basis", "sampling when the interval covers sampling noise only"),
    ("n_days", "Clear, windy days used"),
    ("lifetime_h", "Fitted NO2 lifetime in the plume, hours"),
    ("ratio", "Estimate divided by reported. Empty for sources with no verdict"),
    ("ratio_lo", "Lower end of the ratio's 95% interval, with the systematic uncertainty"),
    ("ratio_hi", "Upper end of the ratio's 95% interval, with the systematic uncertainty"),
    ("verdict", "higher, consistent, lower or inconclusive. Empty when not compared"),
    ("grade", "A, B or C. Empty when there is no verdict"),
    ("us_test_site", "True for the US power plants used to test the method"),
    (
        "below_reliable_detection",
        "True when the footprint is under the size the method measures reliably",
    ),
    ("cluster_facilities", "Number of facilities in the reported total, for clusters"),
]
COLUMNS = [name for name, _ in FIELDS]


def flatten(f: dict[str, Any]) -> dict[str, Any]:
    """One row of the download from one finding of findings.json."""
    s = f["subject"]
    claimed = f.get("claimed") or {}
    obs = f.get("observed") or {}
    ratio = f.get("ratio") or {}
    detection = f.get("detection") or {}
    cluster = f.get("cluster") or {}
    return {
        "finding_id": f["id"],
        "subject_id": s["id"],
        "kind": s["kind"],
        "name": s["name"],
        "operator": s.get("operator"),
        "sector": s["sector"],
        "country": s["country"],
        "city": s.get("city"),
        "lat": s["lat"],
        "lon": s["lon"],
        "register": s["register"],
        "register_id": s["register_id"],
        "period": f["period"]["label"],
        "reported_t": claimed.get("value"),
        "reported_basis": claimed.get("basis"),
        "estimate_t": obs.get("value"),
        "estimate_lo": obs.get("lo"),
        "estimate_hi": obs.get("hi"),
        "interval_basis": obs.get("interval_basis"),
        "n_days": obs.get("n_days"),
        "lifetime_h": obs.get("lifetime_h"),
        "ratio": ratio.get("value"),
        "ratio_lo": ratio.get("lo"),
        "ratio_hi": ratio.get("hi"),
        "verdict": f.get("verdict"),
        "grade": f.get("grade"),
        "us_test_site": bool(f.get("validation_site")),
        "below_reliable_detection": (not detection["reliable"]) if detection else None,
        "cluster_facilities": cluster.get("n_facilities"),
    }


def write_exports(module_dir: Path) -> dict[str, int]:
    """Write findings.csv, findings.parquet and fields.json beside findings.json."""
    import duckdb

    payload = json.loads((module_dir / "findings.json").read_text(encoding="utf-8"))
    rows = [flatten(f) for f in payload["findings"]]
    csv_path = module_dir / "findings.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    parquet_path = module_dir / "findings.parquet"
    con = duckdb.connect()
    # Read the CSV back with explicit text for the codes, so "NO" and ids are never guessed.
    con.execute(
        "COPY (SELECT * FROM read_csv(?, header = true, all_varchar = false, "
        "types = {'country': 'VARCHAR', 'register_id': 'VARCHAR', 'period': 'VARCHAR'})) "
        "TO ? (FORMAT PARQUET)",
        [csv_path.as_posix(), parquet_path.as_posix()],
    )
    con.close()
    fields = [{"name": n, "description": d} for n, d in FIELDS]
    (module_dir / "fields.json").write_text(
        json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return {"rows": len(rows)}
