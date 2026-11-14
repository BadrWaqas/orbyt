"""Tests for the monitor comparison (M4.3): hours before the pass, statistics, flags."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import numpy as np

from orbyt.modules.pollution_hunter import validate


def _t(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 6, 1, hour, minute, tzinfo=UTC)


def test_like_for_like_uses_the_three_whole_hours_before_the_pass_hour():
    # 1000 kg/h at 15, 16, 17 UTC. A pass at 18:42 sees those three hours, not hour 18.
    series = {datetime(2024, 6, 1, h): 1000.0 for h in (15, 16, 17)}
    series[datetime(2024, 6, 1, 18)] = 9e9
    series[datetime(2024, 6, 1, 14)] = 9e9
    got = validate.like_for_like(series, [_t(18, 42)])
    assert got == 1000.0 * validate.HOURS_PER_YEAR / 1000.0


def test_like_for_like_counts_missing_hours_as_off_and_averages_days():
    series = {datetime(2024, 6, 1, 17): 3000.0}  # one hour of three, the plant was off otherwise
    a = validate.like_for_like(series, [_t(18)])
    assert a == 1000.0 * validate.HOURS_PER_YEAR / 1000.0
    b = validate.like_for_like(series, [_t(18), _t(12)])  # second day: nothing recorded
    assert b == a / 2


def test_like_for_like_with_no_days_is_none():
    assert validate.like_for_like({}, []) is None


def test_compare_stats_ratio_of_sums_and_correlation():
    ref = [100.0, 200.0, 400.0, 800.0]
    stats = validate.compare_stats([110.0, 220.0, 440.0, 880.0], ref)
    assert stats["n"] == 4
    assert abs(stats["bias_pct"] - 10.0) < 1e-9
    assert abs(stats["median_ratio"] - 1.1) < 1e-9
    assert stats["pearson"] > 0.999 and stats["spearman"] == 1.0
    assert abs(stats["log_scatter"]) < 1e-9  # constant ratio, no scatter in the log


def test_compare_stats_ignores_missing_and_zero_references():
    stats = validate.compare_stats([100.0, np.nan, 50.0, 80.0], [100.0, 10.0, 0.0, 80.0])
    assert stats["n"] == 2
    assert "pearson" not in stats  # fewer than three points


def test_annual_reference_sums_the_plants_of_a_footprint(tmp_path):
    path = tmp_path / "annual.parquet"
    duckdb.connect().execute(
        f"""copy (select * from (values (1, 2024, 10.0), (2, 2024, 5.0), (3, 2024, 99.0),
                                        (1, 2023, 7.0)) t(plant_id_eia, year, nox_t))
            to '{path.as_posix()}' (format parquet)"""
    )
    assert validate.annual_reference(path, [1, 2], 2024) == 15.0
    assert validate.annual_reference(path, [9], 2024) is None


def test_hourly_series_sums_plants_and_converts_pounds(tmp_path):
    path = tmp_path / "hourly.parquet"
    con = duckdb.connect()
    con.execute(
        f"""copy (select * from (values
              (1, timestamp '2024-06-01 15:00', 100.0),
              (2, timestamp '2024-06-01 15:00', 100.0),
              (3, timestamp '2024-06-01 15:00', 999.0),
              (1, timestamp '2024-06-01 16:00', null)) t(plant_id_eia, hour_utc, nox_mass_lbs))
            to '{path.as_posix()}' (format parquet)"""
    )
    got = validate.hourly_series(con, path, [1, 2])
    assert list(got) == [datetime(2024, 6, 1, 15)]
    assert abs(got[datetime(2024, 6, 1, 15)] - 200.0 * 0.45359237) < 1e-9


def test_flagged_names():
    assert validate.is_flagged("Midland Cogeneration Venture")
    assert validate.is_flagged("W A Parish")
    assert validate.is_flagged("R S Nelson")
    assert not validate.is_flagged("New Madrid")


def test_summary_groups_tiers_and_gate_filter():
    def row(tier, est, ref, gates):
        return {
            "tier": tier,
            "level": "100m",
            "est_t_yr": est,
            "gates_failed": gates,
            "v1_ref_t_yr": ref,
            "v2_ref_t_yr": ref,
        }

    rows = [row(1, 100.0, 100.0, ""), row(1, 200.0, 100.0, "poor_fit"), row(2, 50.0, 100.0, "")]
    got = {(s["comparison"], s["group"], s["subset"]): s for s in validate.summarise(rows)}
    assert got[("V1", "tier 1", "all")]["n"] == 2
    assert got[("V1", "tier 1", "gates passed")]["n"] == 1
    assert got[("V1", "pooled", "all")]["n"] == 3
    assert got[("V2", "tier 2", "gates passed")]["n"] == 1
