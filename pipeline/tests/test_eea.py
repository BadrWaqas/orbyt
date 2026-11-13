import json
from pathlib import Path

import duckdb
import pytest

from orbyt.sources import eea

# Real rows from the v16 facility air release table: Belchatow (PL), Pocerady (CZ), and one Italian
# facility whose name and coordinates are withheld as confidential. Includes SOX rows to be dropped.
FIXTURE = Path(__file__).parent / "fixtures" / "eea_f1_4_sample.csv"
BELCHATOW = "PL.MŚ/000000349.FACILITY"
ITALY_CONFIDENTIAL = "IT.CAED/210322001.FACILITY"


@pytest.fixture
def con():
    c = duckdb.connect()
    eea.load(FIXTURE, c)
    return c


def test_reported_keeps_only_nox_and_converts_kg_to_tonnes(con):
    rows = con.execute("select count(*) from reported").fetchone()[0]
    assert rows == 7  # 3 Belchatow + 1 Pocerady + 3 Italy, no SOX
    kg, t = con.execute(
        "select release_kg, release_t from reported where facility_id = ? and year = 2024",
        [BELCHATOW],
    ).fetchone()
    assert kg == 18_800_000 and t == 18_800.0


def test_facilities_use_latest_row_trim_names_and_keep_missing_coordinates_null(con):
    assert con.execute("select count(*) from facilities").fetchone()[0] == 3
    name, lon, lat, sector = con.execute(
        "select name, lon, lat, sector from facilities where facility_id = ?", [BELCHATOW]
    ).fetchone()
    assert name.endswith("Elektrownia Bełchatów")
    assert (lon, lat) == (pytest.approx(19.3166675567627), pytest.approx(51.2666664123535))
    assert sector == "Energy sector"
    lon, lat = con.execute(
        "select lon, lat from facilities where facility_id = ?", [ITALY_CONFIDENTIAL]
    ).fetchone()
    assert lon is None and lat is None


def test_coverage_shows_which_countries_have_not_reported_2024(con):
    cov = {r[0]: r[1:] for r in con.execute("select * from coverage").fetchall()}
    assert cov["Czechia"] == (2022, 2022, 1)
    assert cov["Poland"] == (2022, 2024, 1)
    assert cov["Italy"] == (2022, 2024, 1)


def test_top_reporters_orders_by_release_and_skips_rows_without_coordinates(con):
    top_2022 = eea.top_reporters(con, 2022, 10)
    assert [r["register_id"] for r in top_2022] == [
        BELCHATOW,
        "CZ.MZP.U424/CZ44746297.FACILITY",
    ]
    assert top_2022[0]["release_t"] == 26_600.0
    assert len(eea.top_reporters(con, 2022, 1)) == 1


def test_top_reporters_keeps_countries_without_2024_at_their_latest_year(con):
    top = eea.top_reporters(con, 2024, 10)
    assert [(r["register_id"], r["year"]) for r in top] == [
        (BELCHATOW, 2024),
        ("CZ.MZP.U424/CZ44746297.FACILITY", 2022),  # Czechia stops at 2022
    ]


def test_fallback_years_older_than_the_cutoff_are_dropped(con):
    top = eea.top_reporters(con, 2024, 10, min_year=2023)
    assert [(r["register_id"], r["year"]) for r in top] == [(BELCHATOW, 2024)]
    assert eea.MIN_FALLBACK_YEAR == 2022


def test_subject_id_is_stable_and_not_rank_based():
    a = eea.subject_id(BELCHATOW)
    assert a == eea.subject_id(BELCHATOW)
    assert a.startswith("ph-eu-") and len(a) == len("ph-eu-") + 8
    assert a != eea.subject_id(ITALY_CONFIDENTIAL)


def test_findings_have_reported_values_only(con):
    payload = eea.build_findings(eea.top_reporters(con, 2024, 5), 2024)
    assert payload["count"] == 2 and payload["period"] == "2024"
    f = payload["findings"][0]
    assert f["id"] == f"{eea.subject_id(BELCHATOW)}-2024"
    assert f["subject"]["country"] == "PL" and f["subject"]["register"] == "EEA"
    assert f["subject"]["lat"] == 51.26667 and f["subject"]["lon"] == 19.31667
    assert f["claimed"] == {
        "value": 18800.0,
        "unit": "t NOx/yr",
        "basis": "unknown",
        "source": "EEA Industrial Reporting database v16",
    }
    assert f["observed"] is None and f["ratio"] is None
    assert f["verdict"] is None and f["grade"] is None
    assert f["period"] == {"label": "2024", "start": "2024-01-01", "end": "2024-12-31"}


def test_findings_label_the_year_when_a_country_has_no_2024(con):
    payload = eea.build_findings(eea.top_reporters(con, 2024, 5), 2024)
    cz = payload["findings"][1]
    assert cz["subject"]["country"] == "CZ"
    assert cz["id"].endswith("-2022")
    assert cz["period"]["label"] == "2022"
    assert cz["period"]["start"] == "2022-01-01" and cz["period"]["end"] == "2022-12-31"
    assert cz["period"]["note"] == "Latest year reported by Czechia. No 2024 data."
    assert "note" not in payload["findings"][0]["period"]
    assert payload["latest_year_countries"] == {"CZ": 2022}


def test_export_findings_writes_utf8_json(con, tmp_path):
    out = eea.export_findings(con, 2022, 10, tmp_path / "v1" / "findings.json")
    text = out.read_text(encoding="utf-8")
    assert "Bełchatów" in text
    data = json.loads(text)
    assert data["count"] == len(data["findings"]) == 2


def test_reported_series_lists_every_reported_year_oldest_first(con):
    series = eea.reported_series(con, [BELCHATOW, "CZ.MZP.U424/CZ44746297.FACILITY"])
    assert series[BELCHATOW] == [
        {"year": 2022, "value": 26600.0, "basis": "unknown"},
        {"year": 2023, "value": 18800.0, "basis": "unknown"},
        {"year": 2024, "value": 18800.0, "basis": "unknown"},
    ]
    assert series["CZ.MZP.U424/CZ44746297.FACILITY"] == [
        {"year": 2022, "value": 4335.3, "basis": "unknown"}
    ]


def test_export_writes_one_detail_file_per_finding_and_removes_stale_ones(con, tmp_path):
    out = tmp_path / "v1" / "findings.json"
    stale = out.parent / "finding" / "ph-eu-00000000-2019.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    eea.export_findings(con, 2024, 10, out)
    ids = [f["id"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]]
    files = sorted(p.name for p in (out.parent / "finding").iterdir())
    assert files == sorted(f"{i}.json" for i in ids) and not stale.exists()
    detail = json.loads((out.parent / "finding" / f"{ids[0]}.json").read_text(encoding="utf-8"))
    assert detail["id"] == ids[0] == f"{eea.subject_id(BELCHATOW)}-2024"
    assert [p["year"] for p in detail["reported_series"]] == [2022, 2023, 2024]
    assert detail["sources"] == ["EEA Industrial Reporting database v16"]


def test_zip_check_rejects_missing_and_corrupt_files(tmp_path):
    assert not eea._zip_ok(tmp_path / "nope.zip")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert not eea._zip_ok(bad)
