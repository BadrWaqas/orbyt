"""Tests for the verdict rules of PLAN.md 4.8, checked against numbers worked out by hand."""

from __future__ import annotations

from math import exp, log, sqrt

import pytest

from orbyt.core import verdict as v
from orbyt.modules.pollution_hunter.config import load_config

RULES = v.Rules(u_sys=0.35, higher_min=1.25, lower_max=0.80, min_periods=2, grade_a_min_days=80)


def _interval(estimate: float, s_boot: float) -> tuple[float, float]:
    """A bootstrap interval around the estimate with the given log sd."""
    return estimate * exp(-1.96 * s_boot), estimate * exp(1.96 * s_boot)


def _call(label, ratio, s_boot=0.15, reported=10_000.0, gates=None, rules=RULES):
    est = ratio * reported
    lo, hi = _interval(est, s_boot)
    return v.call_period(label, est, lo, hi, reported, gates or [], rules)


def test_config_u_sys_is_the_validated_value():
    rules = v.rules_from_config(load_config())
    assert rules.u_sys == 0.35
    assert (rules.higher_min, rules.lower_max, rules.min_periods) == (1.25, 0.80, 2)


def test_sigma_boot_is_the_interval_in_log_units():
    assert v.sigma_boot(1000.0, 2000.0) == pytest.approx(log(2.0) / 3.92)
    assert v.sigma_boot(None, 2000.0) is None
    assert v.sigma_boot(0.0, 2000.0) is None
    assert v.sigma_boot(float("nan"), 2000.0) is None
    assert v.sigma_boot(2000.0, 1000.0) is None


def test_ratio_interval_adds_the_systematic_term_in_quadrature():
    lo, hi = _interval(12_000.0, 0.15)
    r = v.ratio_interval(12_000.0, lo, hi, 10_000.0, 0.35)
    assert r.value == pytest.approx(1.2)
    assert r.s_boot == pytest.approx(0.15)
    assert r.s_total == pytest.approx(sqrt(0.15**2 + 0.35**2))
    assert r.lo == pytest.approx(1.2 * exp(-1.96 * r.s_total))
    assert r.hi == pytest.approx(1.2 * exp(1.96 * r.s_total))


def test_higher_needs_the_lower_end_above_1_25():
    # s_boot 0.15 gives s_total 0.381 and a factor of 2.11, so R must be above about 2.64.
    assert _call("2024", 2.7).status == "higher"
    assert _call("2024", 2.5).status == "consistent"
    assert _call("2024", 1.2).status == "consistent"


def test_lower_needs_the_upper_end_below_0_80():
    # Same factor: R must be below about 0.38.
    assert _call("2024", 0.35).status == "lower"
    assert _call("2024", 0.42).status == "consistent"


def test_a_wide_interval_blocks_a_flag_that_a_narrow_one_allows():
    assert _call("2024", 3.0, s_boot=0.15).status == "higher"
    assert _call("2024", 3.0, s_boot=0.40).status == "consistent"


def test_failed_gate_is_inconclusive_even_when_the_number_is_far_off():
    c = _call("2024", 5.0, gates=["source_offset"])
    assert c.status == "inconclusive"
    assert "source_offset" in c.reason
    assert c.ratio is not None  # kept so a reviewer can see what the number was


def test_unpaired_when_the_register_has_no_value():
    assert v.call_period("2025", 5000.0, 4000.0, 6000.0, None, [], RULES).status == "unpaired"
    assert v.call_period("2025", 5000.0, 4000.0, 6000.0, 0.0, [], RULES).status == "unpaired"


def test_no_estimate_or_no_interval_is_inconclusive():
    assert v.call_period("2024", None, None, None, 5000.0, ["no_fit"], RULES).status == (
        "inconclusive"
    )
    nan = float("nan")
    assert v.call_period("2024", 5000.0, nan, nan, 5000.0, [], RULES).status == "inconclusive"


def test_higher_needs_two_periods_that_agree():
    both = [_call("2023", 3.0), _call("2024", 3.2)]
    assert v.combine(both, RULES) == ("higher", None)


def test_higher_in_one_period_only_is_not_called():
    only_head = [_call("2023", 1.0), _call("2024", 3.2)]
    verdict, why = v.combine(only_head, RULES)
    assert verdict == "inconclusive"
    assert "2024 only" in why
    # The second period failing its gates cannot confirm it either.
    failed = [_call("2023", 3.0, gates=["poor_fit"]), _call("2024", 3.2)]
    assert v.combine(failed, RULES)[0] == "inconclusive"
    # A single paired period cannot be confirmed.
    assert v.combine([_call("2024", 3.2)], RULES)[0] == "inconclusive"


def test_lower_follows_the_same_two_period_rule():
    assert v.combine([_call("2023", 0.3), _call("2024", 0.33)], RULES) == ("lower", None)
    assert v.combine([_call("2023", 1.0), _call("2024", 0.33)], RULES)[0] == "inconclusive"


def test_opposite_directions_do_not_confirm_each_other():
    calls = [_call("2023", 3.0), _call("2024", 0.3)]
    assert v.combine(calls, RULES)[0] == "inconclusive"


def test_consistent_headline_stands_whatever_the_other_period_says():
    assert v.combine([_call("2023", 3.0), _call("2024", 1.1)], RULES) == ("consistent", None)
    failed = [_call("2023", 1.0, gates=["poor_fit"]), _call("2024", 1.1)]
    assert v.combine(failed, RULES) == ("consistent", None)


def test_inconclusive_headline_wins_over_an_earlier_pass():
    calls = [_call("2023", 1.1), _call("2024", 1.1, gates=["low_signal_to_noise"])]
    verdict, why = v.combine(calls, RULES)
    assert verdict == "inconclusive"
    assert "low_signal_to_noise" in why


def test_headline_is_the_latest_period_with_a_register_value():
    unpaired = v.call_period("2025", 5000.0, 4000.0, 6000.0, None, [], RULES)
    assert v.combine([_call("2024", 1.0), unpaired], RULES) == ("consistent", None)
    assert v.combine([unpaired], RULES) == ("unpaired", None)
    assert v.combine([], RULES) == ("unpaired", None)


def test_grade_follows_plan_4_8():
    assert v.grade("consistent", 120, 1, [], RULES) == "A"
    assert v.grade("consistent", 80, 1, [], RULES) == "A"
    assert v.grade("consistent", 79, 1, [], RULES) == "B"
    assert v.grade("consistent", 41, 1, [], RULES) == "B"
    assert v.grade("consistent", 120, 1, ["coast"], RULES) == "B"
    assert v.grade("consistent", 120, 4, [], RULES) == "C"
    assert v.grade("consistent", 120, 1, ["coast", "terrain"], RULES) == "C"


def test_grade_only_for_a_verdict_that_carries_a_number():
    for verdict in ("inconclusive", "unpaired"):
        assert v.grade(verdict, 120, 1, [], RULES) is None
    assert v.grade("higher", 120, 1, [], RULES) == "A"
    assert v.grade("lower", 120, 1, [], RULES) == "A"
