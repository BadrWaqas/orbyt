"""M4.5: choose 20 empty sites for the null test (PLAN.md 4.9, V3).

    uv run python -m orbyt.modules.pollution_hunter.null_sites

V3: run the pipeline at places with no source within 60 km. No site may pass the gates. A site
that does is a false positive, and the gates are not safe to publish with.

A site is a small town (so it is on land and inhabited, like real surroundings) with no register
source of ``source_min_t`` or more within ``source_radius_km``: no EEA facility in Europe, no
monitored US power plant. Sites are drawn at random with a fixed seed, in four cells of five:

                         Europe    United States
    far from cities       5            5      no city of 200,000 within 100 km
    in a city's shadow    5            5      a city of 500,000 or more 30 to 100 km away,
                                              none of 200,000 within 30 km

The second row is the case the provisional ``city_far`` rule (500,000 within 100 km) is for. If
those sites are rejected by the gates anyway, the rule is not needed. If one passes, it is.

Nothing here looks at a satellite image, so the draw cannot favour easy sites. What the draw
cannot see: unreported industry, shipping, airports and motorways. That is the point of a null
test in real surroundings, and any site that passes gets a manual look before it is called a
false positive.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from orbyt.core.geo import haversine_km
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import campd, eea
from orbyt.sources import cities as cities_src

OUT_JSON = Path(__file__).with_name("null_sites.json")
US_NAME = "United States of America"
EUROPE_NAMES = set(eea.COUNTRY_ISO2)
REGIONS = {
    "europe": {"lat": (36.0, 56.0), "lon": (-10.0, 30.0)},
    "us": {"lat": (28.0, 48.0), "lon": (-125.0, -67.0)},
}


def load_sources(
    db_path: Path = eea.WAREHOUSE_DIR / "orbyt.duckdb",
    annual: Path = campd.WAREHOUSE_DIR / "campd_annual.parquet",
    year: int = 2024,
    min_year: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Latitude, longitude and NOx tonnes of every register source: EEA facilities and US plants.

    EEA facilities are taken at their latest reported year, whatever it is: a plant that last
    reported in 2019 (the United Kingdom) is still a source. US plants are taken at ``year``.
    """
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        eu = con.execute(
            """
            select f.lat, f.lon, r.t from facilities f
            join (select facility_id, max(year) as y, arg_max(release_t, year) as t
                  from reported group by facility_id) r using (facility_id)
            where f.lat is not null and f.lon is not null and r.y >= ?
            """,
            [min_year],
        ).fetchall()
    finally:
        con.close()
    us = (
        duckdb.connect()
        .execute(
            f"select lat, lon, nox_t from read_parquet('{annual.as_posix()}') where year = ?",
            [year],
        )
        .fetchall()
    )
    rows = np.array([*eu, *us], dtype=float)
    return rows[:, 0], rows[:, 1], rows[:, 2]


def region_of(country: str, lat: float, lon: float) -> str | None:
    """'europe' or 'us' when the place is in one of the boxes, else None."""
    name = "us" if country == US_NAME else "europe" if country in EUROPE_NAMES else None
    if name is None:
        return None
    box = REGIONS[name]
    if box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]:
        return name
    return None


def stratum_of(
    cities: cities_src.Cities, lat: float, lon: float, cfg: dict[str, Any]
) -> tuple[str | None, str]:
    """('far' | 'shadow' | None, nearest city of 500,000 or more as text)."""
    dist = haversine_km(lat, lon, cities.lat, cities.lon)
    pop = cities.population
    big = np.where(pop >= cfg["shadow_pop"])[0]
    nearest = ""
    if len(big):
        k = big[np.argmin(dist[big])]
        nearest = f"{cities.name[k]} ({dist[k]:.0f} km)"
    near_200k = ((pop >= cfg["far_pop"]) & (dist <= cfg["city_near_km"])).any()
    if near_200k:
        return None, nearest
    in_100 = ((pop >= cfg["far_pop"]) & (dist <= cfg["far_km"])).any()
    shadow = (pop >= cfg["shadow_pop"]) & (dist >= cfg["city_near_km"]) & (dist <= cfg["far_km"])
    if shadow.any():
        return "shadow", nearest
    return (None, nearest) if in_100 else ("far", nearest)


def choose(
    cities: cities_src.Cities,
    src: tuple[np.ndarray, np.ndarray, np.ndarray],
    cfg: dict[str, Any],
    log=print,
) -> list[dict[str, Any]]:
    """Draw the sites. Every cell gets ``per_cell`` sites, or fewer if the pool runs out."""
    rng = np.random.default_rng(cfg["seed"])
    s_lat, s_lon, s_t = src
    keep = s_t >= cfg["source_min_t"]
    s_lat, s_lon = s_lat[keep], s_lon[keep]
    cells = {(r, s): [] for r in REGIONS for s in ("far", "shadow")}
    order = rng.permutation(len(cities))
    for i in order:
        if cities.population[i] > cfg["max_town_pop"]:
            continue
        lat, lon = float(cities.lat[i]), float(cities.lon[i])
        region = region_of(str(cities.country[i]), lat, lon)
        if region is None:
            continue
        if len(cells[(region, "far")]) >= cfg["per_cell"] and (
            len(cells[(region, "shadow")]) >= cfg["per_cell"]
        ):
            continue
        d_src = haversine_km(lat, lon, s_lat, s_lon)
        if (d_src <= cfg["source_radius_km"]).any():
            continue
        stratum, nearest = stratum_of(cities, lat, lon, cfg)
        if stratum is None or len(cells[(region, stratum)]) >= cfg["per_cell"]:
            continue
        chosen = [site for cell in cells.values() for site in cell]
        if any(haversine_km(lat, lon, c["lat"], c["lon"]) < cfg["min_spacing_km"] for c in chosen):
            continue
        cells[(region, stratum)].append(
            {
                "name": f"{cities.name[i]}, {cities.country[i]}",
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "region": region,
                "stratum": stratum,
                "town_pop": int(cities.population[i]),
                "nearest_big_city": nearest,
                "nearest_source_km": round(float(d_src.min()), 1),
            }
        )
    out = []
    for (region, stratum), sites in cells.items():
        if len(sites) < cfg["per_cell"]:
            log(f"only {len(sites)} of {cfg['per_cell']} sites for {region}, {stratum}")
        out.extend(sites)
    for n, site in enumerate(out, start=1):
        site["subject_id"] = f"ph-null-{n:02d}"
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose the empty sites for the null test")
    parser.add_argument("--out", type=Path, default=OUT_JSON)
    args = parser.parse_args()
    cfg = load_config()["null_test"]
    cities = cities_src.load_cities(cities_src.download())
    sites = choose(cities, load_sources(), cfg)
    args.out.write_text(json.dumps(sites, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(sites)} sites")
    for s in sites:
        print(
            f"{s['subject_id']} {s['region']:6s} {s['stratum']:6s} {ascii(s['name'])[:34]:34s} "
            f"{s['lat']:7.3f} {s['lon']:8.3f}  big city: {s['nearest_big_city'] or '-':26s} "
            f"nearest source {s['nearest_source_km']:.0f} km"
        )


if __name__ == "__main__":
    main()
