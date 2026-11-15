"""Tests for the European subject list (M5.1): per-year footprints and the run order."""

from __future__ import annotations

import duckdb

from orbyt.modules.pollution_hunter import candidates, eu_set
from orbyt.sources import eea


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        "create table facilities (facility_id varchar, name varchar, city varchar, "
        "country varchar, sector varchar, lon double, lat double)"
    )
    con.execute(
        "create table reported (facility_id varchar, country varchar, year int, release_t double)"
    )
    # A at 50.0 N, B 11 km north of it, C 300 km away.
    for fid, lat in (("A", 50.0), ("B", 50.1), ("C", 52.7)):
        con.execute(
            "insert into facilities values (?, ?, 'town', 'Land', 'Energy', 10.0, ?)",
            [fid, f"Plant {fid}", lat],
        )
    for fid, year, t in (
        ("A", 2023, 5000.0),
        ("A", 2024, 4000.0),
        ("B", 2023, 1500.0),
        ("C", 2023, 9000.0),
        ("C", 2024, 8000.0),
    ):
        con.execute("insert into reported values (?, 'Land', ?, ?)", [fid, year, t])
    return con


def test_year_rows_has_no_fallback_to_other_years():
    rows = eu_set.year_rows(_con(), 2024)
    assert sorted(r["register_id"] for r in rows) == ["A", "C"]


def test_footprint_in_year_sums_only_that_years_members():
    con = _con()
    fp23 = eu_set.footprint_in_year(eu_set.year_rows(con, 2023), "A", 20.0)
    fp24 = eu_set.footprint_in_year(eu_set.year_rows(con, 2024), "A", 20.0)
    assert fp23["footprint_t"] == 6500.0
    assert [m["register_id"] for m in fp23["members"]] == ["A", "B"]
    assert fp24["footprint_t"] == 4000.0
    assert [m["register_id"] for m in fp24["members"]] == ["A"]


def test_footprint_in_year_is_none_when_the_anchor_did_not_report():
    rows = eu_set.year_rows(_con(), 2024)
    assert eu_set.footprint_in_year(rows, "B", 20.0) is None


def test_select_orders_reliable_first_and_keeps_each_footprint_once(monkeypatch):
    con = _con()

    def fake_rank(_con, year, _cfg, log=print, **_kw):
        rows = eu_set.year_rows(con, year)
        out = []
        for g in candidates.footprints(rows, 20.0):
            anchor = rows[max(g, key=lambda i: rows[i]["release_t"])]
            out.append(
                {
                    "subject_anchor": anchor["register_id"],
                    "name": anchor["name"],
                    "city": anchor["city"],
                    "country": anchor["country"],
                    "sector": anchor["sector"],
                    "lat": anchor["lat"],
                    "lon": anchor["lon"],
                    "n_facilities": len(g),
                    "reported_t": sum(rows[i]["release_t"] for i in g),
                    "isolated": True,
                    "own_detectable": True,
                    "own_enh_umol_m2": 5.0,
                    "map_noise_umol_m2": 1.0,
                }
            )
        return out

    monkeypatch.setattr(candidates, "rank", fake_rank)
    cfg = {
        "candidates": {"footprint_km": 20, "reliable_min_t": 6000},
        "europe": {"register_years": [2023, 2024]},
    }
    subjects = eu_set.select(con, cfg)
    assert [s["register_id"] for s in subjects] == ["C", "A"]
    assert [s["reliable"] for s in subjects] == [True, False]
    # A is chosen from 2024 (4,000 t), and its 2023 footprint, which holds B, is not a second one.
    assert subjects[1]["selected_from_year"] == 2024
    assert subjects[1]["years"]["2023"]["footprint_t"] == 6500.0
    assert subjects[1]["latest_register_year"] == 2024
    assert subjects[1]["latest_footprint_t"] == 4000.0


def test_failed_checks_reads_the_flags():
    scored = {"flag_sources": True, "flag_city_near": False, "flag_hotspot": True}
    assert eu_set.failed_checks(scored) == {"sources", "hotspot"}
    assert eu_set.failed_checks({}) == set()


def test_neighbours_of_lists_the_big_sources_20_to_60_km_out():
    # Anchor at 50.0 N. 0.3 deg is 33 km, 1.0 deg is 111 km, 0.05 deg is 5.6 km (in footprint).
    rows = [
        {"register_id": "A", "name": "A", "lat": 50.0, "lon": 10.0, "release_t": 3000.0},
        {"register_id": "B", "name": "B", "lat": 50.05, "lon": 10.0, "release_t": 500.0},
        {"register_id": "N", "name": "N", "lat": 50.3, "lon": 10.0, "release_t": 2000.0},
        {"register_id": "S", "name": "S", "lat": 50.3, "lon": 10.0, "release_t": 100.0},
        {"register_id": "F", "name": "F", "lat": 51.0, "lon": 10.0, "release_t": 5000.0},
    ]
    ccfg = {"footprint_km": 20, "source_frac": 0.25, "source_min_km": 20, "source_max_km": 60}
    near = eu_set.neighbours_of(rows, "A", ccfg)
    assert [n["register_id"] for n in near] == ["N"]
    assert 30 < near[0]["distance_km"] < 36


def test_select_keeps_a_cluster_only_when_the_flag_is_allowed(monkeypatch):
    con = _con()

    def fake_rank(_con, year, _cfg, log=print, **_kw):
        rows = eu_set.year_rows(con, year)
        out = []
        for g in candidates.footprints(rows, 20.0):
            anchor = rows[max(g, key=lambda i: rows[i]["release_t"])]
            only_sources = anchor["register_id"] == "A"
            out.append(
                {
                    "subject_anchor": anchor["register_id"],
                    "name": anchor["name"],
                    "city": anchor["city"],
                    "country": anchor["country"],
                    "sector": anchor["sector"],
                    "lat": anchor["lat"],
                    "lon": anchor["lon"],
                    "n_facilities": len(g),
                    "reported_t": sum(rows[i]["release_t"] for i in g),
                    "isolated": not only_sources,
                    "flag_sources": only_sources,
                    "own_detectable": True,
                    "own_enh_umol_m2": 5.0,
                    "map_noise_umol_m2": 1.0,
                }
            )
        return out

    monkeypatch.setattr(candidates, "rank", fake_rank)
    monkeypatch.setattr(eea, "top_reporters", lambda *_a, **_k: [])
    base = {
        "candidates": {
            "footprint_km": 20,
            "reliable_min_t": 6000,
            "source_frac": 0.25,
            "source_min_km": 20,
            "source_max_km": 60,
        },
        "europe": {"register_years": [2023, 2024]},
    }
    strict = eu_set.select(con, base)
    assert [(s["register_id"], s["selection"]) for s in strict] == [("C", "isolated")]
    loose = eu_set.select(con, {**base, "europe": {**base["europe"], "cluster_flags": ["sources"]}})
    by_id = {s["register_id"]: s for s in loose}
    assert by_id["A"]["selection"] == "cluster"
    assert by_id["A"]["failed_checks"] == ["sources"]
    assert by_id["C"]["selection"] == "isolated"
