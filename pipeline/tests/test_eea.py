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
    assert [r["register_id"] for r in eea.top_reporters(con, 2024, 10)] == [BELCHATOW]
    assert len(eea.top_reporters(con, 2022, 1)) == 1


def test_subject_id_is_stable_and_not_rank_based():
    a = eea.subject_id(BELCHATOW)
    assert a == eea.subject_id(BELCHATOW)
    assert a.startswith("ph-eu-") and len(a) == len("ph-eu-") + 8
    assert a != eea.subject_id(ITALY_CONFIDENTIAL)


def test_findings_have_reported_values_only(con):
    payload = eea.build_findings(eea.top_reporters(con, 2024, 5), 2024)
    assert payload["count"] == 1 and payload["period"] == "2024"
    f = payload["findings"][0]
    assert f["id"] == f"{eea.subject_id(BELCHATOW)}-2024"
    assert f["subject"]["country"] == "PL" and f["subject"]["register"] == "EEA"
    assert f["subject"]["lat"] == 51.26667 and f["subject"]["lon"] == 19.31667
    assert f["claimed"] == {
        "value": 18800.0,
        "unit": "t NOx/yr",
        "basis": None,
        "source": "EEA Industrial Reporting database v16",
    }
    assert f["observed"] is None and f["ratio"] is None
    assert f["verdict"] is None and f["grade"] is None
    assert f["period"] == {"label": "2024", "start": "2024-01-01", "end": "2024-12-31"}


def test_export_findings_writes_utf8_json(con, tmp_path):
    out = eea.export_findings(con, 2022, 10, tmp_path / "v1" / "findings.json")
    text = out.read_text(encoding="utf-8")
    assert "Bełchatów" in text
    data = json.loads(text)
    assert data["count"] == len(data["findings"]) == 2


def test_zip_check_rejects_missing_and_corrupt_files(tmp_path):
    assert not eea._zip_ok(tmp_path / "nope.zip")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert not eea._zip_ok(bad)
