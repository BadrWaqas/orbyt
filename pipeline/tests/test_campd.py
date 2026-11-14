"""Tests for the CAMPD loader on a tiny hourly table. No network."""

from __future__ import annotations

import duckdb
import pytest

from orbyt.sources import campd

LB = 0.45359237


@pytest.fixture
def hourly(tmp_path):
    """Plant 10 has two units. Unit A runs 3 hours, unit B is off for 2 and runs for 1 with no
    NOx value. Plant 20 has one unit that is Calculated, in both years."""
    path = tmp_path / "hourly.parquet"
    con = duckdb.connect()
    con.execute(
        """
        create table h as
        select plant_id_eia, plant_id_epa, unit_id, hour_utc, year,
               operating_time_hours::double as operating_time_hours,
               gross_load_mw::double as gross_load_mw,
               nox_mass_lbs::double as nox_mass_lbs, nox_mass_measurement_code
        from (values
          (10, 100, 'A', timestamp '2024-01-01 10:00', 2024, 1.0, 300.0, 100.0, 'Measured'),
          (10, 100, 'A', timestamp '2024-01-01 11:00', 2024, 1.0, 300.0, 200.0, 'Measured'),
          (10, 100, 'A', timestamp '2024-01-01 12:00', 2024, 1.0, 300.0, 300.0, 'Measured'),
          (10, 100, 'B', timestamp '2024-01-01 10:00', 2024, 0.0, 0.0, null, null),
          (10, 100, 'B', timestamp '2024-01-01 11:00', 2024, 0.0, 0.0, null, null),
          (10, 100, 'B', timestamp '2024-01-01 12:00', 2024, 1.0, 100.0, null, 'Measured'),
          (20, 200, 'X', timestamp '2023-06-01 10:00', 2023, 1.0, 50.0, 1000.0, 'Calculated'),
          (20, 200, 'X', timestamp '2024-06-01 10:00', 2024, 1.0, 50.0, 500.0, 'Calculated')
        ) t(plant_id_eia, plant_id_epa, unit_id, hour_utc, year, operating_time_hours,
            gross_load_mw, nox_mass_lbs, nox_mass_measurement_code)
        """
    )
    con.execute(f"copy h to '{path.as_posix()}' (format parquet)")
    return path


def test_annual_converts_pounds_to_tonnes_and_flags_gaps(hourly):
    con = campd.annual_nox(duckdb.connect(), hourly)
    rows = {
        (p, y): rest
        for p, y, *rest in con.execute(
            "select plant_id_eia, year, nox_t, measured_share, n_units, unit_hours, "
            "unit_hours_operating, operating_nox_missing from annual"
        ).fetchall()
    }
    nox_t, measured, n_units, unit_hours, operating, missing = rows[(10, 2024)]
    assert nox_t == pytest.approx(600.0 * LB / 1000.0)
    assert measured == pytest.approx(1.0)
    assert (n_units, unit_hours, operating, missing) == (2, 6, 4, 1)  # B's 12:00 has no value
    nox_t, measured, *_ = rows[(20, 2024)]
    assert nox_t == pytest.approx(500.0 * LB / 1000.0) and measured == 0.0
    assert (20, 2023) in rows  # years are separate rows


def test_plant_hourly_sums_units_and_counts_operating_gaps(hourly):
    rows = campd.plant_hourly(duckdb.connect(), hourly, 10)
    assert [r["nox_kg"] for r in rows] == pytest.approx([100 * LB, 200 * LB, 300 * LB])
    assert [r["units_missing"] for r in rows] == [0, 0, 1]
    assert [r["units"] for r in rows] == [2, 2, 2]
    assert rows[0]["hour_utc"].hour == 10 and rows[0]["gross_load_mw"] == 300.0


def test_hourly_path_names_the_years(tmp_path):
    assert campd.hourly_path((2023, 2024), tmp_path).name == "hourly_nox_2023_2024.parquet"
    assert campd.LB_TO_KG == LB
    assert campd.YEARS == (2023, 2024)
