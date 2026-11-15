"""Tests for the European comparison (M5.3): what is published and what is held back."""

from __future__ import annotations

import json
from math import exp

from orbyt.core import verdict as vd
from orbyt.modules.pollution_hunter import compare

RULES = vd.Rules(u_sys=0.35, higher_min=1.25, lower_max=0.80, min_periods=2, grade_a_min_days=80)


def _estimate(value, s_boot=0.1, gates=None, days=100):
    return {
        "method": "ph-emg-1.1",
        "observed": {
            "nox_t_yr": value,
            "lo": value * exp(-1.96 * s_boot),
            "hi": value * exp(1.96 * s_boot),
            "lifetime_h": 2.0,
        },
        "gates_failed": gates or [],
        "days": {"used": days},
        "profile": {"fit": {"t0": 0.1, "r2": 0.95}},
    }


def _subject(reported_by_year, n_facilities=1):
    years = {
        str(y): None
        if t is None
        else {"footprint_t": t, "members": [{"register_id": "x", "name": "X", "reported_t": t}]}
        for y, t in reported_by_year.items()
    }
    return {"subject_id": "ph-eu-test", "n_facilities": n_facilities, "years": years}


def _write(tmp_path, year, est):
    d = tmp_path / "ph-eu-test"
    d.mkdir(exist_ok=True)
    (d / f"estimate-{year}.json").write_text(json.dumps(est), encoding="utf-8")


CFG = {"europe": {"register_years": [2023, 2024]}, "method_version": "ph-emg-1.1"}


def _evaluate(tmp_path, ests, reported, flags=()):
    for y, e in ests.items():
        _write(tmp_path, y, e)
    return compare.evaluate(_subject(reported), {"flags": list(flags)}, tmp_path, RULES, CFG)


def test_two_years_far_above_the_register_are_higher_and_held(tmp_path):
    r = _evaluate(
        tmp_path,
        {2023: _estimate(30_000), 2024: _estimate(31_000)},
        {2023: 10_000.0, 2024: 10_000.0},
    )
    assert r["verdict"] == "higher"
    assert r["exceeds_higher"] == [2023, 2024]
    assert not compare.publish_side(r, approved=set())
    assert compare.publish_side(r, approved={"ph-eu-test"})


def test_consistent_result_is_published_without_review(tmp_path):
    r = _evaluate(
        tmp_path,
        {2023: _estimate(11_000), 2024: _estimate(9_000)},
        {2023: 10_000.0, 2024: 10_000.0},
    )
    assert r["verdict"] == "consistent"
    assert r["grade"] == "A"
    assert compare.publish_side(r, approved=set())


def test_failed_gate_publishes_no_number(tmp_path):
    r = _evaluate(
        tmp_path,
        {2023: _estimate(50_000, gates=["poor_fit"]), 2024: _estimate(50_000, gates=["poor_fit"])},
        {2023: 10_000.0, 2024: 10_000.0},
    )
    assert r["verdict"] == "inconclusive"
    assert r["grade"] is None
    assert not compare.publish_side(r, approved=set())
    period = compare.period_json(r["periods"][1])
    assert period["observed"] is None
    assert period["ratio"] is None
    assert period["gates_failed"] == ["poor_fit"]


def test_missing_register_year_is_unpaired_and_the_headline_moves_back(tmp_path):
    r = _evaluate(
        tmp_path,
        {2023: _estimate(10_000), 2024: _estimate(10_000)},
        {2023: 10_000.0, 2024: None},
    )
    assert r["headline"]["year"] == 2023
    assert r["periods"][1]["call"].status == "unpaired"
    assert r["verdict"] == "consistent"


def test_estimate_file_of_another_method_is_refused(tmp_path):
    import pytest

    bad = _estimate(10_000)
    bad["method"] = "ph-emg-1.0"
    _write(tmp_path, 2023, bad)
    _write(tmp_path, 2024, _estimate(10_000))
    with pytest.raises(SystemExit):
        compare.evaluate(
            _subject({2023: 10_000.0, 2024: 10_000.0}), {"flags": []}, tmp_path, RULES, CFG
        )


def test_merge_replaces_a_finding_and_drops_the_old_detail_file(tmp_path):
    payload = {"findings": [{"id": "ph-eu-test-2023", "subject": {"id": "ph-eu-test"}}]}
    (tmp_path / "ph-eu-test-2023.json").write_text("{}", encoding="utf-8")
    new = {"id": "ph-eu-test-2024", "subject": {"id": "ph-eu-test"}}
    compare.merge(payload, [(new, {"id": "ph-eu-test-2024"})], tmp_path)
    assert [f["id"] for f in payload["findings"]] == ["ph-eu-test-2024"]
    assert payload["count"] == 1
    assert not (tmp_path / "ph-eu-test-2023.json").exists()
    assert (tmp_path / "ph-eu-test-2024.json").exists()


def test_approved_ids_reads_the_review_file(tmp_path):
    path = tmp_path / "higher_review.json"
    assert compare.approved_ids(path) == set()
    path.write_text(json.dumps({"approved": ["ph-eu-a"]}), encoding="utf-8")
    assert compare.approved_ids(path) == {"ph-eu-a"}
