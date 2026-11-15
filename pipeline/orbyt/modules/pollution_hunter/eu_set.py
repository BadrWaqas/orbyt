"""The European subjects of milestone M5 (PLAN.md 1.7 and 6, M5.1).

    uv run python -m orbyt.modules.pollution_hunter.eu_set

A subject is a footprint (a facility plus every register facility within 20 km, chained) whose
reported NOx is at least ``candidates.min_footprint_t`` in one of ``europe.register_years`` and
that passes all four isolation checks of candidates.py in that year. The list is fixed from the
register, the city list and the 2024 NO2 map alone, before any European estimate exists, and is
written to ``eu_subjects.json`` next to this file.

Run order for the estimates: footprints at or above ``candidates.reliable_min_t`` first, then the
rest, each largest first. The ones below are kept (the 2,000 t floor stays) and labelled "below
reliable detection" (M4.4). Each year's footprint is rebuilt from that year's register rows, so a
facility that did not report in a year is not in that year's total, and a year in which the
subject's own anchor facility did not report is not paired.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

from orbyt.core.geo import haversine_km
from orbyt.modules.pollution_hunter import candidates
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import cities as cities_src
from orbyt.sources import eea

SUBJECTS_JSON = Path(__file__).parent / "eu_subjects.json"
KEYS = ("register_id", "name", "city", "country", "sector", "lon", "lat", "release_t")


def year_rows(con: duckdb.DuckDBPyConnection, year: int) -> list[dict]:
    """Every register row of exactly ``year`` that has coordinates. No fallback to other years."""
    rows = con.execute(
        """
        select f.facility_id, f.name, f.city, f.country, f.sector, f.lon, f.lat, r.release_t
        from reported r join facilities f using (facility_id)
        where r.year = ? and f.lon between -180 and 180 and f.lat between -90 and 90
        order by r.release_t desc, f.facility_id
        """,
        [year],
    ).fetchall()
    return [dict(zip(KEYS, row, strict=True)) for row in rows]


def footprint_in_year(rows: list[dict], anchor_id: str, radius_km: float) -> dict | None:
    """The footprint that holds the anchor facility in this year's rows, or None if it has none.

    Same chaining as the candidate scoring (candidates.footprints), so the reported total is the
    one the isolation checks used. Members are listed largest first.
    """
    for group in candidates.footprints(rows, radius_km):
        if any(rows[i]["register_id"] == anchor_id for i in group):
            members = sorted(group, key=lambda i: -rows[i]["release_t"])
            return {
                "footprint_t": round(sum(rows[i]["release_t"] for i in members), 1),
                "members": [
                    {
                        "register_id": rows[i]["register_id"],
                        "name": rows[i]["name"],
                        "reported_t": round(rows[i]["release_t"], 1),
                    }
                    for i in members
                ],
            }
    return None


def select(
    con: duckdb.DuckDBPyConnection, cfg: dict[str, Any] | None = None, log=print, **kw
) -> list[dict]:
    """Isolated footprints of the minimum size in any register year, newest year first.

    A footprint found in an earlier year is not added again when it lies within the footprint
    radius of one already chosen from a later year. ``kw`` goes to ``candidates.rank``.
    """
    cfg = cfg or load_config()
    ccfg, years = cfg["candidates"], sorted(cfg["europe"]["register_years"])
    chosen: list[dict] = []
    for year in reversed(years):
        scored = candidates.rank(con, year, ccfg, log=log, **kw)
        for r in scored:
            if not r["isolated"]:
                continue
            if any(
                haversine_km(r["lat"], r["lon"], c["lat"], c["lon"]) <= ccfg["footprint_km"]
                for c in chosen
            ):
                continue
            chosen.append({**r, "selected_from_year": year})
    rows_by_year = {y: year_rows(con, y) for y in years}
    out = []
    for c in chosen:
        per_year = {
            str(y): footprint_in_year(rows_by_year[y], c["subject_anchor"], ccfg["footprint_km"])
            for y in years
        }
        latest = max((y for y in years if per_year[str(y)]), default=None)
        total = per_year[str(latest)]["footprint_t"] if latest else c["reported_t"]
        out.append(
            {
                "subject_id": eea.subject_id(c["subject_anchor"]),
                "register_id": c["subject_anchor"],
                "name": c["name"],
                "city": c["city"],
                "country": c["country"],
                "sector": c["sector"],
                "lat": round(c["lat"], 5),
                "lon": round(c["lon"], 5),
                "n_facilities": c["n_facilities"],
                "selected_from_year": c["selected_from_year"],
                "latest_register_year": latest,
                "latest_footprint_t": total,
                "reliable": total >= ccfg["reliable_min_t"],
                "own_detectable": bool(c["own_detectable"]),
                "own_enh_umol_m2": c["own_enh_umol_m2"],
                "map_noise_umol_m2": c["map_noise_umol_m2"],
                "years": per_year,
            }
        )
    # Reliable footprints first, then the rest, each largest first.
    out.sort(key=lambda s: (not s["reliable"], -s["latest_footprint_t"]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose the European subjects for M5")
    parser.add_argument("--out", type=Path, default=SUBJECTS_JSON)
    args = parser.parse_args()
    cities_src.download()
    con = duckdb.connect(str(eea.WAREHOUSE_DIR / "orbyt.duckdb"), read_only=True)
    subjects = select(con)
    args.out.write_text(json.dumps(subjects, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_rel = sum(s["reliable"] for s in subjects)
    print(f"{len(subjects)} isolated footprints, {n_rel} at or above the reliable size. {args.out}")
    for s in subjects:
        yrs = ", ".join(
            f"{y}: {v['footprint_t']:,.0f} t" if v else f"{y}: none" for y, v in s["years"].items()
        )
        tag = "reliable" if s["reliable"] else "below reliable detection"
        print(f"  {s['subject_id']} {s['country']:12s} {ascii(s['city'])[:20]:20s} {yrs}  {tag}")


if __name__ == "__main__":
    main()
