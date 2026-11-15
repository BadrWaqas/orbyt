"""Tests for the CSV and Parquet downloads (M6.8)."""

from __future__ import annotations

import json

import duckdb
from test_contracts import FINDING

from orbyt.core import exports


def _finding(**over):
    return {**FINDING, **over}


def test_flatten_gives_every_column_and_blanks_what_is_missing():
    row = exports.flatten(_finding())
    assert list(row) == exports.COLUMNS
    assert row["finding_id"] == "ph-eu-x-2024"
    assert row["reported_t"] is None and row["verdict"] is None
    assert row["us_test_site"] is False
    assert row["below_reliable_detection"] is None


def test_flatten_reads_estimate_ratio_detection_and_cluster():
    row = exports.flatten(
        _finding(
            claimed={"value": 1000.0, "basis": "measured", "unit": "t", "source": "EEA"},
            observed={
                "value": 1100.0,
                "lo": 900.0,
                "hi": 1400.0,
                "n_days": 90,
                "unit": "t",
                "method": "m",
            },
            ratio={"value": 1.1, "lo": 0.5, "hi": 2.4},
            verdict="consistent",
            grade="B",
            detection={
                "footprint_km": 20,
                "footprint_t": 7000.0,
                "min_reliable_t": 6000.0,
                "reliable": False,
            },
            cluster={"n_facilities": 3},
        )
    )
    assert row["estimate_hi"] == 1400.0 and row["ratio_lo"] == 0.5
    assert row["verdict"] == "consistent" and row["grade"] == "B"
    assert row["below_reliable_detection"] is True
    assert row["cluster_facilities"] == 3


def test_write_exports_writes_matching_csv_and_parquet(tmp_path):
    (tmp_path / "findings.json").write_text(
        json.dumps({"findings": [_finding(), _finding(id="b")]})
    )
    assert exports.write_exports(tmp_path) == {"rows": 2}
    text = (tmp_path / "findings.csv").read_text(encoding="utf-8").splitlines()
    assert text[0] == ",".join(exports.COLUMNS) and len(text) == 3
    n = duckdb.sql(
        f"select count(*) from '{(tmp_path / 'findings.parquet').as_posix()}'"
    ).fetchall()[0][0]
    assert n == 2
