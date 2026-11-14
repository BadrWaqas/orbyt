"""M4.2: choose the US plants for the validation (PLAN.md 4.9, V1 and V2).

    uv run python -m orbyt.modules.pollution_hunter.validation_set

The plan starts from the US power plants in the Beirle catalogue. That download (M2.1) is waiting
on WDCC approval, so the starting point here is the monitors themselves: every US plant in the
EPA hourly file. The checks are the ones the European candidates face, unchanged, so the
validation tests the rule the product uses:

  size      footprint total of at least ``min_footprint_t`` in each of the two years (PLAN.md 1.5)
  quality   the monitored NOx is almost all measured, and the monitors have almost no gaps
  isolation the four checks of candidates.py: sources, city_near, city_far, hotspot

A footprint is a plant plus every monitored plant within 20 km, and the ground truth is their sum,
the same accounting as the European comparison. Nothing here looks at a satellite estimate, so the
choice cannot be tuned to the result.

What the monitors do not cover: only power plants have a continuous monitor here. A refinery,
cement kiln, steel mill or compressor station next to a plant is invisible to the sources check.
The hotspot check on the NO2 map is the only guard against those.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import duckdb

from orbyt.modules.pollution_hunter import candidates
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import campd
from orbyt.sources import cities as cities_src

ANNUAL = campd.WAREHOUSE_DIR / "campd_annual.parquet"
OUT_PARQUET = campd.WAREHOUSE_DIR / "us_validation_candidates.parquet"
PLANTS_JSON = Path(__file__).with_name("validation_plants.json")


def load_rows(annual: Path, years: tuple[int, int]) -> list[dict[str, Any]]:
    """One row per monitored plant with coordinates, in the shape candidates.score() expects.

    ``release_t`` is the NOx of the later year. The earlier year, the measured share and the share
    of operating hours with no value are kept for the size and quality checks.
    """
    first, last = years
    path = str(annual).replace("\\", "/")
    rows = (
        duckdb.connect()
        .execute(
            f"""
        select b.plant_id_eia, b.name, b.county, b.state, b.lat, b.lon,
               b.nox_t, a.nox_t, b.measured_share, a.measured_share,
               b.operating_nox_missing * 1.0 / nullif(b.unit_hours_operating, 0),
               a.operating_nox_missing * 1.0 / nullif(a.unit_hours_operating, 0)
        from read_parquet('{path}') b
        join read_parquet('{path}') a using (plant_id_eia)
        where b.year = {last} and a.year = {first} and b.nox_t > 0 and a.nox_t > 0
        """
        )
        .fetchall()
    )
    out = []
    for r in rows:
        out.append(
            {
                "register_id": str(r[0]),
                "name": r[1],
                "city": f"{r[2]}, {r[3]}",
                "country": "United States",
                "sector": "Power plant",
                "lat": r[4],
                "lon": r[5],
                "release_t": float(r[6]),
                "year": last,
                "nox_t_by_year": {last: float(r[6]), first: float(r[7])},
                "measured_share_by_year": {last: r[8], first: r[9]},
                "op_gap_by_year": {last: r[10] or 0.0, first: r[11] or 0.0},
            }
        )
    return out


def footprint_quality(group: list[int], rows: list[dict], years: tuple[int, int]) -> dict:
    """Totals per year, and the tonnes-weighted measured share and gap share of the footprint."""
    out: dict[str, Any] = {}
    for y in years:
        tot = sum(rows[i]["nox_t_by_year"][y] for i in group)
        out[f"nox_t_{y}"] = tot
        out[f"measured_share_{y}"] = (
            sum(
                rows[i]["nox_t_by_year"][y] * (rows[i]["measured_share_by_year"][y] or 0.0)
                for i in group
            )
            / tot
        )
        out[f"op_gap_{y}"] = max(rows[i]["op_gap_by_year"][y] for i in group)
    return out


def select(
    rows: list[dict],
    cities: cities_src.Cities,
    tif: Path,
    years: tuple[int, int],
    cfg: dict[str, Any],
    log=print,
) -> list[dict]:
    """Every footprint that passes the size check, scored, with the quality and isolation flags."""
    vcfg, ccfg = cfg["validation"], cfg["candidates"]
    groups = candidates.footprints(rows, ccfg["footprint_km"])
    log(f"{len(rows)} monitored plants with both years, {len(groups)} footprints")
    sized = []
    for g in groups:
        q = footprint_quality(g, rows, years)
        if all(q[f"nox_t_{y}"] >= vcfg["min_footprint_t"] for y in years):
            sized.append((g, q))
    log(f"{len(sized)} footprints of at least {vcfg['min_footprint_t']:,.0f} t in both years")
    out = []
    for g, q in sized:
        anchor = rows[max(g, key=lambda i: rows[i]["release_t"])]
        half_km = ccfg["hotspot"]["window_km"]
        win = candidates.read_window(tif, anchor["lat"], anchor["lon"], half_km)
        scored = candidates.score(g, rows, cities, win, ccfg)
        scored.update(q)
        scored["plant_ids"] = ",".join(sorted(rows[i]["register_id"] for i in g))
        scored["good_monitors"] = all(
            q[f"measured_share_{y}"] >= vcfg["min_measured_share"]
            and q[f"op_gap_{y}"] <= vcfg["max_operating_gap"]
            for y in years
        )
        out.append(scored)
    out.sort(key=lambda r: -r["reported_t"])
    return out


def tier_of(r: dict[str, Any], vcfg: dict[str, Any]) -> int:
    """1 passes every isolation check, 2 fails only checks in ``tier2_may_fail``, 0 is left out.

    Both tiers need good monitors. The tiers are fixed by the rules alone, so M4.3 can report the
    two groups separately and show whether the relaxed checks matter.
    """
    if not r["good_monitors"]:
        return 0
    failed = {
        k[5:] for k in ("flag_sources", "flag_city_near", "flag_city_far", "flag_hotspot") if r[k]
    }
    if not failed:
        return 1
    return 2 if failed <= set(vcfg["tier2_may_fail"]) else 0


def write_plants(results: list[dict], vcfg: dict[str, Any], path: Path) -> list[dict]:
    """The chosen footprints as JSON, largest first. M4.3 reads this file."""
    import json

    chosen = []
    for r in results:
        tier = tier_of(r, vcfg)
        if not tier:
            continue
        chosen.append(
            {
                "subject_id": f"ph-us-{r['subject_anchor']}",
                "tier": tier,
                "name": r["name"],
                "county_state": r["city"],
                "lat": round(r["lat"], 5),
                "lon": round(r["lon"], 5),
                "plant_ids_eia": [int(i) for i in r["plant_ids"].split(",")],
                "n_plants": r["n_facilities"],
                "nox_t_2023": round(r["nox_t_2023"]),
                "nox_t_2024": round(r["nox_t_2024"]),
                "measured_share": round(min(r["measured_share_2023"], r["measured_share_2024"]), 3),
                "flags_failed": [
                    k[5:]
                    for k in ("flag_sources", "flag_city_near", "flag_city_far", "flag_hotspot")
                    if r[k]
                ],
                "nearest_big_city": r["nearest_big_city"],
                "own_detectable": bool(r["own_detectable"]),
            }
        )
    chosen.sort(key=lambda c: (c["tier"], -c["nox_t_2024"]))
    path.write_text(json.dumps(chosen, indent=1) + "\n", encoding="utf-8")
    return chosen


def funnel(results: list[dict]) -> dict[str, int]:
    """How many footprints survive each check in turn, and each check on its own."""
    good = [r for r in results if r["good_monitors"]]
    steps = {"sized": len(results), "good_monitors": len(good)}
    left = good
    for flag in ("flag_sources", "flag_city_near", "flag_city_far", "flag_hotspot"):
        left = [r for r in left if not r[flag]]
        steps[f"after_{flag[5:]}"] = len(left)
    steps["alone_sources"] = sum(not r["flag_sources"] for r in good)
    steps["alone_city_near"] = sum(not r["flag_city_near"] for r in good)
    steps["alone_city_far"] = sum(not r["flag_city_far"] for r in good)
    steps["alone_hotspot"] = sum(not r["flag_hotspot"] for r in good)
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose the US validation plants")
    parser.add_argument("--annual", type=Path, default=ANNUAL)
    args = parser.parse_args()
    cfg = load_config()
    years = tuple(cfg["validation"]["years"])
    cities = cities_src.load_cities(cities_src.download())
    rows = load_rows(args.annual, years)
    results = select(rows, cities, candidates.NO2_MAP, years, cfg)
    candidates.write_parquet(results, OUT_PARQUET)
    print("funnel:", funnel(results))
    chosen = write_plants(results, cfg["validation"], PLANTS_JSON)
    counts = {t: sum(c["tier"] == t for c in chosen) for t in (1, 2)}
    print(f"wrote {OUT_PARQUET} and {PLANTS_JSON}: tier 1 {counts[1]}, tier 2 {counts[2]}")
    for c in chosen:
        print(
            f"T{c['tier']} {c['nox_t_2023']:6,d} {c['nox_t_2024']:6,d} t  {c['name'][:30]:30s} "
            f"{c['county_state'][:22]:22s} n={c['n_plants']} fails={','.join(c['flags_failed'])}"
        )


if __name__ == "__main__":
    main()
