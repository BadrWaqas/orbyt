"""Tests for the null-test report (M4.5)."""

from __future__ import annotations

import json
from pathlib import Path

from orbyt.modules.pollution_hunter import null_report

SITE = {
    "subject_id": "ph-null-01",
    "name": "Town, Germany",
    "region": "europe",
    "stratum": "far",
    "nearest_big_city": "",
}


def _write(tmp: Path, sid: str, gates: list[str], est: float | None = 100.0) -> None:
    d = tmp / sid
    d.mkdir(parents=True)
    doc = {
        "gates_failed": gates,
        "days": {"used": 80},
        "observed": None if est is None else {"nox_t_yr": est},
    }
    (d / "estimate-2024.json").write_text(json.dumps(doc), encoding="utf-8")


def test_a_site_that_fails_a_gate_does_not_pass(tmp_path: Path):
    _write(tmp_path, "ph-null-01", ["poor_fit", "source_offset"])
    row = null_report.site_row(SITE, 2024, tmp_path)
    assert row["passes_all_gates"] is False
    assert row["n_gates_failed"] == 2


def test_a_site_with_no_failed_gate_is_reported_as_a_pass(tmp_path: Path):
    _write(tmp_path, "ph-null-01", [])
    text = null_report.report_markdown([null_report.site_row(SITE, 2024, tmp_path)], 2024)
    assert "1 passed every gate" in text
    assert "NONE" in text


def test_a_site_that_did_not_run_is_not_counted(tmp_path: Path):
    row = null_report.site_row(SITE, 2024, tmp_path)
    assert row["gates_failed"] is None
    text = null_report.report_markdown([row], 2024)
    assert "0 of 1 sites ran" in text


def test_gate_counts():
    rows = [{"gates_failed": "poor_fit,source_offset"}, {"gates_failed": "poor_fit"}]
    counts = null_report.gate_counts(rows)
    assert counts["poor_fit"] == 2 and counts["source_offset"] == 1
    assert counts["too_few_days"] == 0
