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


def test_compare_stats_ignores_missing_estimates_and_zero_references():
    stats = validate.compare_stats([100.0, np.nan, 50.0, 80.0], [100.0, 10.0, 0.0, 80.0])
    assert stats["n"] == 2
    assert "pearson" not in stats  # fewer than three points


def test_a_zero_estimate_counts_in_the_bias_but_not_in_the_log_scatter():
    ref = [100.0, 200.0, 400.0, 800.0]
    stats = validate.compare_stats([100.0, 200.0, 400.0, 0.0], ref)
    assert stats["n"] == 4
    assert stats["n_no_plume"] == 1
    assert stats["bias_pct"] < -50
    assert abs(stats["log_scatter"]) < 1e-9  # the three plumes found have a ratio of one


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


def test_flag_is_unmonitored_share_of_the_monitor_total():
    assert validate.is_flagged(250.0, 1000.0, 0.25)
    assert not validate.is_flagged(249.0, 1000.0, 0.25)
    assert not validate.is_flagged(None, 1000.0, 0.25)
    assert not validate.is_flagged(500.0, None, 0.25)


def test_boot_log_sd_is_the_plan_s_boot():
    assert abs(validate.boot_log_sd(1.0, np.exp(3.92)) - 1.0) < 1e-12
    assert validate.boot_log_sd(0.0, 10.0) is None
    assert validate.boot_log_sd(None, 10.0) is None


def _gated(est, ref, lo, hi, tier=1, gates=""):
    return {
        "tier": tier,
        "level": "100m",
        "est_t_yr": est,
        "lo": lo,
        "hi": hi,
        "gates_failed": gates,
        "v2_fp_ref_t_yr": ref,
    }


def test_systematic_scatter_removes_the_bootstrap_part():
    # Log ratios -0.5, 0, 0.5: sample variance 0.25. Each interval is s_boot = 0.3.
    w = np.exp(0.3 * 3.92 / 2)
    rows = [
        _gated(100.0 * np.exp(x), 100.0, 100.0 * np.exp(x) / w, 100.0 * np.exp(x) * w)
        for x in (-0.5, 0.0, 0.5)
    ]
    s = validate.systematic_scatter(rows, "v2_fp_ref_t_yr")
    assert s["n"] == 3
    assert abs(s["observed"] - 0.5) < 1e-9
    assert abs(s["boot"] - 0.3) < 1e-9
    assert abs(s["excess"] - 0.4) < 1e-9
    assert s["upper95"] > s["observed"]
    assert abs(s["mean_log_ratio"]) < 1e-9


def test_systematic_scatter_never_negative_and_needs_three_points():
    rows = [_gated(100.0, 100.0, 10.0, 1000.0) for _ in range(3)]
    assert validate.systematic_scatter(rows, "v2_fp_ref_t_yr")["excess"] == 0.0
    assert validate.systematic_scatter(rows[:2], "v2_fp_ref_t_yr") == {"n": 2}


def test_gate_counts_and_pass_by_size():
    rows = [
        _gated(100.0, 3000.0, 1, 2),
        _gated(100.0, 5000.0, 1, 2, gates="low_signal_to_noise"),
        _gated(100.0, 9000.0, 1, 2, gates="poor_fit,source_offset"),
        _gated(100.0, 9000.0, 1, 2, tier=2, gates="source_offset"),
    ]
    g = {x["tier"]: x for x in validate.gate_counts(rows, "100m")}
    assert g[1]["n"] == 3 and g[1]["passed"] == 1
    assert g[1]["low_signal_to_noise"] == 1 and g[1]["low_signal_to_noise_alone"] == 1
    assert g[1]["source_offset"] == 1 and g[1]["source_offset_alone"] == 0
    assert g[2]["source_offset_alone"] == 1
    sizes = {(s["lo"], s["tier"]): s for s in validate.pass_by_size(rows, "100m")}
    assert sizes[(0.0, 1)]["n"] == 1 and sizes[(0.0, 1)]["passed"] == 1
    assert sizes[(6000.0, 1)]["n"] == 1 and sizes[(6000.0, 1)]["passed"] == 0
    assert sizes[(6000.0, 2)]["n"] == 1


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
    assert ("V2f", "pooled", "all") not in got  # no footprint reference in these rows


def test_summary_adds_the_footprint_reference_when_present():
    rows = [
        {
            "tier": 1,
            "level": "100m",
            "est_t_yr": e,
            "gates_failed": "",
            "v1_ref_t_yr": 100.0,
            "v2_ref_t_yr": 100.0,
            "v1_fp_ref_t_yr": 200.0,
            "v2_fp_ref_t_yr": 200.0,
        }
        for e in (180.0, 200.0, 220.0)
    ]
    got = {(s["comparison"], s["group"], s["subset"]): s for s in validate.summarise(rows)}
    assert abs(got[("V2", "tier 1", "all")]["bias_pct"] - 100.0) < 1e-9
    assert abs(got[("V2f", "tier 1", "all")]["bias_pct"]) < 1e-9
