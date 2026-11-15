"""Tests for the rolling 12-month windows (M5.2): month arithmetic and which windows exist."""

from __future__ import annotations

from datetime import date

from orbyt.modules.pollution_hunter import windows


def test_add_months_crosses_years_both_ways():
    assert windows.add_months(date(2022, 7, 1), 12) == date(2023, 7, 1)
    assert windows.add_months(date(2022, 11, 1), 3) == date(2023, 2, 1)
    assert windows.add_months(date(2023, 1, 1), -1) == date(2022, 12, 1)


def test_first_incomplete_month():
    # Data to 5 November: November is not complete, so October is the last whole month.
    assert windows.first_incomplete_month(date(2026, 11, 5)) == date(2026, 11, 1)
    # Data to the last day of October: October is complete.
    assert windows.first_incomplete_month(date(2026, 10, 31)) == date(2026, 11, 1)
    assert windows.first_incomplete_month(date(2026, 12, 31)) == date(2027, 1, 1)


def test_rolling_windows_first_and_last():
    wins = windows.rolling_windows(date(2022, 7, 1), date(2026, 11, 5))
    assert wins[0] == (date(2022, 7, 1), date(2023, 7, 1))
    assert wins[-1] == (date(2025, 11, 1), date(2026, 11, 1))
    # One window per month from the one ending June 2023 to the one ending October 2026.
    assert len(wins) == 41
    assert all(b > a and windows.add_months(a, 12) == b for a, b in wins)


def test_rolling_windows_none_before_a_full_year():
    assert windows.rolling_windows(date(2022, 7, 1), date(2023, 5, 20)) == []


def test_calendar_year_windows_are_found():
    wins = windows.rolling_windows(date(2022, 7, 1), date(2026, 11, 5))
    years = [windows.is_calendar_year(a, b) for a, b in wins]
    assert [y for y in years if y] == [2023, 2024, 2025]
    assert windows.is_calendar_year(date(2023, 2, 1), date(2024, 2, 1)) is None


def test_window_label_names_first_and_last_month():
    assert windows.window_label(date(2023, 1, 1), date(2024, 1, 1)) == "Jan 2023 to Dec 2023"
    assert windows.window_label(date(2022, 7, 1), date(2023, 7, 1)) == "Jul 2022 to Jun 2023"


def test_passing_needs_an_estimate_and_no_failed_gate():
    ok = {"nox_t_yr": 5000.0, "gates_failed": []}
    assert windows.passing(ok)
    assert not windows.passing({"nox_t_yr": 5000.0, "gates_failed": ["poor_fit"]})
    assert not windows.passing({"nox_t_yr": None, "gates_failed": ["no_fit"]})
