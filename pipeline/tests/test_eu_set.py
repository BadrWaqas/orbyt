"""Tests for the European subject list (M5.1): per-year footprints and the run order."""

from __future__ import annotations

import duckdb

from orbyt.modules.pollution_hunter import candidates, eu_set


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
