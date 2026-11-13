import json
from dataclasses import asdict
from datetime import UTC, date, datetime

import numpy as np
import pytest

from orbyt.modules.pollution_hunter import extract
from orbyt.modules.pollution_hunter.config import load_config

CFG = load_config()["extract"]
LAT0, LON0 = 51.2666664123535, 19.3166675567627  # Belchatow, as the EEA register has it

# A real Earth Engine profile table, from one patch download.
PROFILE_TEXT = """ EECU·s PeakMem Count  Description
  0.020    845k     6  Loading assets: COPERNICUS/S5P/OFFL/L3_NO2/20240501T100956_20240504T082421
  0.007     11k    35  (plumbing)
  0.005    166k     2  Algorithm Image.unmask computing pixels
  0.000    3.1k     3  Algorithm Image.select
   -        31k     2  Loading assets: COPERNICUS/S5P/OFFL/L3_NO2
   -       9.5k     4  Algorithm Image.load
"""


def ms(y, m, d, hh, mm):
    return int(datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp() * 1000)


def op(image_id, day, hh=10, vza=20.0, valid=0.9):
    return extract.Overpass(
        image_id=image_id,
        start_ms=ms(2024, 5, day, hh, 0),
        end_ms=ms(2024, 5, day, hh + 1, 42),
        sza=36.0,
        vza=vza,
        saa=200.0,
        valid_frac=valid,
    )


def test_config_holds_the_plan_thresholds():
    assert CFG["grid_step_deg"] == 0.03 and CFG["half_extent_km"] == 180
    assert CFG["min_valid_frac"] == 0.5 and CFG["valid_radius_km"] == 50
    assert CFG["max_solar_zenith_deg"] == 65 and CFG["max_sensor_zenith_deg"] == 56


def test_patch_grid_is_centred_ascending_and_covers_180_km():
    lats, lons = extract.patch_grid(LAT0, LON0, CFG["half_extent_km"], CFG["grid_step_deg"])
    assert (len(lats), len(lons)) == (109, 173)  # the size seen in the real download
    assert lats[54] == pytest.approx(LAT0) and lons[86] == pytest.approx(LON0)
    assert (np.diff(lats) > 0).all() and (np.diff(lons) > 0).all()
    assert np.diff(lats) == pytest.approx(0.03)
    # About 180 km each way, and the east-west cells are as wide on the ground as the north-south.
    assert (lats[-1] - LAT0) * 111.195 == pytest.approx(180, abs=2)
    assert (lons[-1] - LON0) * 111.195 * np.cos(np.radians(LAT0)) == pytest.approx(180, abs=2)


def test_pixel_request_places_the_grid_on_cell_edges_with_north_first_rows():
    lats, lons = extract.patch_grid(LAT0, LON0, 180, 0.03)
    req = extract.pixel_request("expr", lats, lons, 0.03)
    t = req["grid"]["affineTransform"]
    assert req["fileFormat"] == "NUMPY_NDARRAY" and req["grid"]["crsCode"] == "EPSG:4326"
    assert req["grid"]["dimensions"] == {"width": 173, "height": 109}
    assert t["translateX"] == pytest.approx(lons[0] - 0.015)
    assert t["translateY"] == pytest.approx(lats[-1] + 0.015)
    assert t["scaleX"] == 0.03 and t["scaleY"] == -0.03
    assert t["shearX"] == 0 and t["shearY"] == 0


def test_overpass_from_properties_rejects_images_with_missing_numbers():
    props = {"id": "a", "start": 1714559490000, "end": 1714565000000, "sza": 36.5, "vza": 23.4,
             "saa": 201.0, "valid": 0.99}  # fmt: skip
    got = extract.overpass_from_properties(props)
    assert got.image_id == "a" and got.vza == 23.4 and got.day == date(2024, 5, 1)
    assert extract.overpass_from_properties({**props, "sza": None}) is None
    assert extract.overpass_from_properties({**props, "valid": None}) is None
    assert extract.overpass_from_properties({**props, "end": None}).end_ms is None


def test_one_per_day_keeps_the_most_nadir_image_and_sorts_by_day():
    ops = [op("c", 3), op("a1", 1, vza=40.0), op("a2", 1, hh=11, vza=12.0), op("b", 2)]
    kept = extract.one_per_day(ops)
    assert [o.image_id for o in kept] == ["a2", "b", "c"]


def test_month_ranges_split_at_month_boundaries_and_clip_to_the_window():
    assert extract.month_ranges(date(2024, 11, 15), date(2025, 2, 10)) == [
        (date(2024, 11, 15), date(2024, 12, 1)),
        (date(2024, 12, 1), date(2025, 1, 1)),
        (date(2025, 1, 1), date(2025, 2, 1)),
        (date(2025, 2, 1), date(2025, 2, 10)),
    ]
    assert len(extract.month_ranges(date(2024, 1, 1), date(2025, 1, 1))) == 12
    assert extract.month_ranges(date(2024, 5, 1), date(2024, 5, 1)) == []


def test_parse_eecu_seconds_sums_the_first_column_and_skips_dashes():
    assert extract.parse_eecu_seconds(PROFILE_TEXT) == pytest.approx(0.032)
    assert extract.parse_eecu_seconds("") == 0.0


def test_patch_round_trip_keeps_values_nan_grid_and_meta(tmp_path):
    lats, lons = extract.patch_grid(LAT0, LON0, 30, 0.03)
    field = np.random.default_rng(1).random((len(lats), len(lons)), dtype="float32")
    field[2, 3] = np.nan
    o = op("20240501T100956_20240504T082421", 1)
    path = extract.patch_path(tmp_path, "ph-eu-test", o)
    assert path.name == "20240501_20240501T100956_20240504T082421.npz"
    extract.save_patch(path, field, lats, lons, o)
    assert not list(path.parent.glob("*.part"))
    got, glats, glons, meta = extract.load_patch(path)
    np.testing.assert_array_equal(got, field)
    np.testing.assert_array_equal(glats, lats)
    np.testing.assert_array_equal(glons, lons)
    assert got.dtype == np.float32 and meta["vza"] == 20.0 and meta["image_id"] == o.image_id


def test_extract_subject_downloads_one_patch_per_day_and_resumes_from_the_cache(tmp_path):
    subject = extract.Subject("ph-eu-test", "Test plant", LAT0, LON0)
    listed = [op("a1", 1, vza=40.0), op("a2", 1, hh=11, vza=12.0), op("b", 2), op("c", 4)]
    calls = {"list": 0, "fetch": []}

    def lister(lat, lon, start, end, meter, cfg, log):
        calls["list"] += 1
        assert (lat, lon) == (LAT0, LON0) and start < end
        return listed

    def fetcher(image_id, lats, lons, step):
        calls["fetch"].append(image_id)
        assert step == 0.03 and (len(lats), len(lons)) == (109, 173)
        return np.full((len(lats), len(lons)), 5e-5, dtype="float32")

    args = (subject, date(2024, 5, 1), date(2024, 6, 1))
    kw = dict(
        out_dir=tmp_path, measure_eecu=False, lister=lister, fetcher=fetcher, log=lambda s: None
    )
    first = extract.extract_subject(*args, **kw)
    assert (first.n_overpasses, first.n_days) == (4, 3)
    assert (first.n_downloaded, first.n_cached) == (3, 0)
    assert sorted(calls["fetch"]) == ["a2", "b", "c"]  # a1 loses to a2 on the same day
    assert all(p.exists() for p in first.paths)
    listing = tmp_path / "ph-eu-test" / "overpasses_2024-05-01_2024-06-01.json"
    assert len(json.loads(listing.read_text(encoding="utf-8"))["overpasses"]) == 4

    again = extract.extract_subject(*args, **kw)
    assert (again.n_downloaded, again.n_cached) == (0, 3)
    assert calls["list"] == 1 and len(calls["fetch"]) == 3  # nothing was fetched or listed again


def test_extract_subject_limit_stops_after_that_many_days(tmp_path):
    subject = extract.Subject("ph-eu-test", "Test plant", LAT0, LON0)
    listed = [op(f"d{d}", d) for d in range(1, 6)]
    res = extract.extract_subject(
        subject,
        date(2024, 5, 1),
        date(2024, 6, 1),
        out_dir=tmp_path,
        limit=2,
        measure_eecu=False,
        lister=lambda *a, **k: listed,
        fetcher=lambda i, la, lo, s: np.zeros((len(la), len(lo)), dtype="float32"),
        log=lambda s: None,
    )
    assert res.n_days == 5 and res.n_downloaded == 2 and len(res.paths) == 2


def test_eecu_cost_scales_the_found_profiles_up_to_all_calls():
    assert extract.EecuCost(measured_s=6.0, n_calls=10, n_found=5).estimated_s == 12.0
    assert extract.EecuCost(measured_s=6.0, n_calls=5, n_found=5).estimated_s == 6.0
    assert extract.EecuCost(measured_s=0.0, n_calls=4, n_found=0).estimated_s == 0.0


def test_meter_counts_missing_profiles_instead_of_failing(monkeypatch):
    table = " EECU·s PeakMem Count  Description\n  0.250    1k     1  (plumbing)\n"

    class FakeCall:
        def __init__(self, ids):
            self.ids = ids

        def getInfo(self):  # noqa: N802 (Earth Engine's own method name)
            if self.ids == ["gone"]:
                raise extract.ee.EEException("Profile.getProfiles: Profile not found.")
            if self.ids == ["broken"]:
                raise extract.ee.EEException("Quota exceeded")
            return table

    class FakeFunction:
        def call(self, ids):
            return FakeCall(ids)

    monkeypatch.setattr(
        extract.ee.apifunction.ApiFunction, "lookup", staticmethod(lambda name: FakeFunction())
    )
    meter = extract.EecuMeter()
    for pid in ("a", "gone", "b"):
        meter.hook(pid)
    cost = meter.cost(wait_s=0)
    assert (cost.n_calls, cost.n_found) == (3, 2)
    assert cost.measured_s == pytest.approx(0.5) and cost.estimated_s == pytest.approx(0.75)

    meter.hook("broken")  # any other failure must not be swallowed
    with pytest.raises(extract.ee.EEException, match="Quota"):
        meter.cost(wait_s=0)


def test_cost_summary_needs_both_costs_and_reports_the_quota_share(tmp_path):
    subject = extract.Subject("ph-eu-test", "Test plant", LAT0, LON0)
    base = dict(subject_id="ph-eu-test", start=date(2024, 1, 1), end=date(2025, 1, 1),
                n_overpasses=200, n_days=150, n_downloaded=150, n_cached=0, paths=[])  # fmt: skip
    (tmp_path / "ph-eu-test").mkdir()
    partial = extract.ExtractResult(
        listing_cost=extract.EecuCost(100.0, 12, 12), patch_cost=None, **base
    )
    assert extract.write_cost_summary(subject, partial, tmp_path) is None
    full = extract.ExtractResult(
        listing_cost=extract.EecuCost(3000.0, 12, 12),
        patch_cost=extract.EecuCost(300.0, 150, 75),  # half the profiles found, so 600 s in all
        **base,
    )
    path = extract.write_cost_summary(subject, full, tmp_path)
    s = json.loads(path.read_text(encoding="utf-8"))
    assert s["eecu_seconds"] == {"listing": 3000.0, "patches": 600.0, "total": 3600.0}
    assert s["profiles_found"] == {"listing": "12 of 12", "patches": "75 of 150"}
    assert s["eecu_hours_total"] == 1.0
    assert s["share_of_community_quota"] == pytest.approx(1 / 150, abs=1e-5)


def test_cached_listing_keeps_its_cost_for_later_runs(tmp_path):
    subject = extract.Subject("ph-eu-test", "Test plant", LAT0, LON0)
    listed = [op("a", 1)]
    cost = extract.EecuCost(12.0, 1, 1)
    d = tmp_path / "ph-eu-test"
    d.mkdir()
    (d / "overpasses_2024-05-01_2024-06-01.json").write_text(
        json.dumps({"listing_cost": asdict(cost), "overpasses": [asdict(o) for o in listed]}),
        encoding="utf-8",
    )
    res = extract.extract_subject(
        subject,
        date(2024, 5, 1),
        date(2024, 6, 1),
        out_dir=tmp_path,
        measure_eecu=False,
        lister=lambda *a, **k: pytest.fail("listing must come from the file"),
        fetcher=lambda i, la, lo, s: np.zeros((len(la), len(lo)), dtype="float32"),
        log=lambda s: None,
    )
    assert res.listing_cost == cost and res.patch_cost is None
