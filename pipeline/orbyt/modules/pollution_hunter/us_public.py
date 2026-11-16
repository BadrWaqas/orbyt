"""The US validation plants on the public map (PLAN.md 1.7 fallback, decided 15 Nov 2026).

    uv run python -m orbyt.modules.pollution_hunter.us_public

PLAN.md 1.7: with fewer than 20 measurable European subjects, bring the US plants onto the public
map as well as the validation page. This writes one finding per tier 1 footprint
(``validation.publish_tiers``) into ``findings.json``, with:

- ``claimed``: the calendar-year total of the stack monitors (CEMS), basis measured.
- ``observed``: filled by evidence.py for the year shown, only when that year's estimate passed
  every gate. The year shown is the latest year whose estimate passed, else the latest year.
- ``detection``: the footprint total (monitors plus NEI unmonitored NOx) and whether it is at
  least ``candidates.reliable_min_t``.
- in the detail file, ``validation``: every year's comparison from M4.3 and M4.4
  (docs/validation/validation_table.csv), so the panel shows the check for this plant.

Run validate.py first. Re-running replaces the US findings and leaves the European ones alone.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from orbyt.modules.pollution_hunter import evidence, validate, validation_set
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import nei
from orbyt.sources.eea import detection_label

REGISTER = "EPA CAMPD"
CLAIMED_SOURCE = "EPA CAMPD hourly stack monitors (CEMS)"
SOURCES = [
    "EPA CAMPD hourly emissions, via PUDL",
    nei.SOURCE,
    "Copernicus Sentinel-5P",
    "ERA5",
]


def _num(x: str) -> float | None:
    return None if x in ("", None) else float(x)


def read_table(path: Path, level: str | None = None) -> dict[str, dict[int, dict]]:
    """{subject id: {year: row}} from validation_table.csv, for one wind level.

    ``level`` defaults to the level the estimates use (``wind.level``).
    """
    level = level or load_config()["wind"]["level"]
    out: dict[str, dict[int, dict]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["level"] == level:
                out.setdefault(row["subject_id"], {})[int(row["year"])] = row
    return out


def validation_entry(row: dict) -> dict[str, Any]:
    """One year of the comparison, as the panel shows it."""
    est, v1, v2, v2f = (
        _num(row[k]) for k in ("est_t_yr", "v1_ref_t_yr", "v2_ref_t_yr", "v2_fp_ref_t_yr")
    )
    gates = [g for g in (row["gates_failed"] or "").split(",") if g]
    passed = est is not None and not gates
    return {
        "year": int(row["year"]),
        "estimate_t": None if est is None else round(est),
        "lo": None if _num(row["lo"]) is None else round(_num(row["lo"])),
        "hi": None if _num(row["hi"]) is None else round(_num(row["hi"])),
        "passed": passed,
        "gates_failed": gates,
        "days": None if row["days_used"] in ("", None) else int(row["days_used"]),
        "monitors_at_pass_t": None if v1 is None else round(v1),
        "monitors_t": None if v2 is None else round(v2),
        "footprint_t": None if v2f is None else round(v2f),
        "ratio_at_pass": None if not (passed and v1) else round(est / v1, 2),
        "ratio_footprint": None if not (passed and v2f) else round(est / v2f, 2),
    }


def shown_year(rows: dict[int, dict]) -> int:
    """The latest year whose estimate passed every gate, else the latest year."""
    passing = [y for y, r in rows.items() if r["est_t_yr"] and not r["gates_failed"]]
    return max(passing) if passing else max(rows)


def build(
    plants: list[dict], table: dict[str, dict[int, dict]], tiers: list[int], cfg: dict
) -> list[tuple[dict, dict, bool]]:
    """(finding, detail, publish evidence) per published plant."""
    out = []
    for p in plants:
        sid = p["subject_id"]
        if p["tier"] not in tiers or sid not in table:
            continue
        rows = table[sid]
        year = shown_year(rows)
        row = rows[year]
        monitors = float(row["v2_ref_t_yr"])
        footprint = _num(row["v2_fp_ref_t_yr"]) or monitors
        finding = {
            "id": f"{sid}-{year}",
            "module": "pollution-hunter",
            "subject": {
                "id": sid,
                "kind": "facility" if p["n_plants"] == 1 else "cluster",
                "name": p["name"],
                "display_name": None,
                "operator": None,
                "sector": "Power generation",
                "country": "US",
                "city": p["county_state"],
                "lat": round(p["lat"], 5),
                "lon": round(p["lon"], 5),
                "register": REGISTER,
                "register_id": "EIA plant " + ", ".join(str(i) for i in p["plant_ids_eia"]),
            },
            "period": {"label": str(year), "start": f"{year}-01-01", "end": f"{year}-12-31"},
            "claimed": {
                "value": round(monitors, 1),
                "unit": "t NOx/yr",
                "basis": "measured",
                "source": CLAIMED_SOURCE,
            },
            "observed": None,
            "ratio": None,
            "verdict": None,
            "grade": None,
            "detection": detection_label(
                footprint, cfg["candidates"]["footprint_km"], cfg["candidates"]["reliable_min_t"]
            ),
            "validation_site": True,
        }
        detail = {
            "id": finding["id"],
            "reported_series": [
                {"year": y, "value": round(float(r["v2_ref_t_yr"]), 1), "basis": "measured"}
                for y, r in sorted(rows.items())
            ],
            "sources": SOURCES,
            "validation": {
                "tier": p["tier"],
                "unmonitored_t": round(float(row["nei_unmonitored_t_yr"] or 0)),
                "unmonitored_largest": row["nei_largest"],
                "u_sys": cfg["verdict"]["u_sys"],
                "years": [validation_entry(r) for _, r in sorted(rows.items())],
            },
        }
        out.append((finding, detail, bool(row["est_t_yr"]) and not row["gates_failed"]))
    return out


def merge(findings_path: Path, built: list[tuple[dict, dict, bool]]) -> None:
    """Replace the US findings in findings.json and write their detail files."""
    payload = json.loads(findings_path.read_text(encoding="utf-8"))
    keep = [f for f in payload["findings"] if f["subject"].get("register") != REGISTER]
    payload["findings"] = keep + [f for f, _, _ in built]
    payload["count"] = len(payload["findings"])
    detail_dir = findings_path.parent / "finding"
    for stale in detail_dir.glob("ph-us-*.json"):
        stale.unlink()
    for _, detail, _ in built:
        text = json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n"
        (detail_dir / f"{detail['id']}.json").write_text(text, encoding="utf-8")
    findings_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Put the US validation plants on the map")
    parser.add_argument("--table", type=Path, default=validate.OUT_DIR / "validation_table.csv")
    parser.add_argument("--no-evidence", action="store_true", help="skip the plume images")
    args = parser.parse_args()
    cfg = load_config()
    plants = json.loads(validation_set.PLANTS_JSON.read_text(encoding="utf-8"))
    built = build(plants, read_table(args.table), cfg["validation"]["publish_tiers"], cfg)
    merge(evidence.FINDINGS, built)
    print(f"wrote {len(built)} US findings")
    if args.no_evidence:
        return
    for finding, _, ok in built:
        if ok:
            evidence.publish_subject(finding["subject"]["id"], year=int(finding["period"]["label"]))


if __name__ == "__main__":
    main()
