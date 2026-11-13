"""Pass time from the sun, hour choice and wind direction."""

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import era5

LAT, LON = 51.27, 19.33
CFG = load_config()["wind"]


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def test_declination_and_equation_of_time_at_solstice_and_february():
    decl, _ = era5.declination_and_eot(172)  # 20 June
    assert abs(decl - 0.4093) < 0.005  # 23.45 degrees
    _, eot = era5.declination_and_eot(44)  # 13 February, the yearly low of about -14 minutes
    assert -15.0 < eot < -13.0


def test_pass_time_is_solar_noon_when_the_sun_is_at_its_highest():
    # At noon the zenith angle is the latitude minus the declination.
    day = date(2024, 4, 27)
    decl, eot_min = era5.declination_and_eot(day.timetuple().tm_yday + 0.5)
    noon_zenith = LAT - math.degrees(decl)
    t = era5.pass_time_from_sun(day, LAT, LON, noon_zenith + 1e-4, 180.0)
    noon_utc = 12 - LON / 15 - eot_min / 60
    got = t.hour + t.minute / 60 + t.second / 3600
    assert abs(got - noon_utc) < 0.05


def test_azimuth_sign_picks_afternoon_or_morning():
    west = era5.pass_time_from_sun(date(2024, 5, 30), LAT, LON, 33.8, -142.4)
    east = era5.pass_time_from_sun(date(2024, 5, 30), LAT, LON, 33.8, 142.4)
    assert west > east
    assert west - east == pytest.approx(timedelta(hours=2.9), abs=timedelta(minutes=15))


def test_pass_time_is_none_when_the_sun_never_gets_that_low_or_high():
    # Midsummer noon zenith here is about 28 degrees and midwinter noon about 75.
    assert era5.pass_time_from_sun(date(2024, 6, 21), LAT, LON, 20.0, -150.0) is None
    assert era5.pass_time_from_sun(date(2024, 12, 21), LAT, LON, 60.0, -150.0) is None


def meta_for(start: datetime, sza: float, saa: float) -> dict:
    return {
        "image_id": "x",
        "start_ms": ms(start),
        "end_ms": ms(start + timedelta(minutes=58)),
        "sza": sza,
        "saa": saa,
    }


def test_choose_pass_time_keeps_the_sun_time_inside_the_window():
    # 30 May 2024: afternoon sun at zenith 33.8, image window 11:29 to 12:28 UTC.
    start = datetime(2024, 5, 30, 11, 29, 54, tzinfo=UTC)
    when, source = era5.choose_pass_time(
        date(2024, 5, 30),
        LAT,
        LON,
        meta_for(start, 33.8, -142.4),
        fallback_solar_hour=CFG["fallback_solar_hour"],
        tolerance_min=CFG["window_tolerance_min"],
    )
    assert source == "solar-geometry"
    assert start - timedelta(minutes=10) <= when <= start + timedelta(minutes=68)


def test_choose_pass_time_falls_back_when_the_sun_time_is_outside_the_window():
    start = datetime(2024, 5, 30, 6, 0, tzinfo=UTC)  # window far from the sun based time
    when, source = era5.choose_pass_time(
        date(2024, 5, 30),
        LAT,
        LON,
        meta_for(start, 33.8, -142.4),
        fallback_solar_hour=13.5,
        tolerance_min=10,
    )
    assert source == "fixed-solar-time"
    assert when == datetime(2024, 5, 30, tzinfo=UTC) + timedelta(hours=13.5 - LON / 15)


def test_fixed_pass_time_matches_the_plan_example():
    # PLAN.md 4.3 step 3: about 12:15 UTC at 19 degrees east.
    t = era5.fixed_pass_time(date(2024, 5, 30), 19.0, 13.5)
    assert (t.hour, t.minute) == (12, 14)


@pytest.mark.parametrize(
    ("minute", "hour"), [(0, 12), (29, 12), (30, 13), (59, 13)]
)
def test_nearest_hour_rounds_at_half_past(minute, hour):
    got = era5.nearest_hour(datetime(2024, 5, 30, 12, minute, 40, tzinfo=UTC))
    assert (got.hour, got.minute, got.second) == (hour, 0, 0)


def test_nearest_hour_rolls_over_midnight():
    got = era5.nearest_hour(datetime(2024, 5, 30, 23, 45, tzinfo=UTC))
    assert got == datetime(2024, 5, 31, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("u", "v", "from_deg"),
    [(0.0, -5.0, 0.0), (-5.0, 0.0, 90.0), (0.0, 5.0, 180.0), (5.0, 0.0, 270.0)],
)
def test_wind_direction_is_where_it_comes_from(u, v, from_deg):
    speed, got = era5.wind_speed_and_from(u, v)
    assert speed == pytest.approx(5.0)
    assert got == pytest.approx(from_deg)


def test_build_day_winds_joins_by_hour_and_keeps_missing_hours_empty():
    start = datetime(2024, 5, 30, 11, 29, 54, tzinfo=UTC)
    metas = [meta_for(start, 33.8, -142.4)]
    _, _, _, hour = era5._day_plan(LAT, LON, metas[0], CFG)
    rows = era5.build_day_winds(LAT, LON, metas, {ms(hour): (3.0, 4.0)}, cfg=CFG)
    assert rows[0].speed_ms == pytest.approx(5.0)
    assert rows[0].pass_source == "solar-geometry"
    assert rows[0].day == "2024-05-30"
    empty = era5.build_day_winds(LAT, LON, metas, {}, cfg=CFG)
    assert empty[0].speed_ms is None and empty[0].from_deg is None


def test_winds_round_trip_through_json(tmp_path):
    start = datetime(2024, 5, 30, 11, 29, 54, tzinfo=UTC)
    metas = [meta_for(start, 33.8, -142.4)]
    _, _, _, hour = era5._day_plan(LAT, LON, metas[0], CFG)
    rows = era5.build_day_winds(LAT, LON, metas, {ms(hour): (3.0, 4.0)}, cfg=CFG)
    path = era5.write_winds(tmp_path / "wind.json", "ph-eu-test", rows, CFG)
    assert era5.read_winds(path) == rows
    assert not list(tmp_path.glob("*.part"))


def test_config_wind_constants_are_the_planned_ones():
    assert CFG["collection"] == "ECMWF/ERA5/HOURLY"
    assert CFG["u_band"] == "u_component_of_wind_100m"
    assert CFG["fallback_solar_hour"] == 13.5
    assert CFG["min_speed_ms"] == 2.0
