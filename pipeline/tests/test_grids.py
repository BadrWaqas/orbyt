import numpy as np

from orbyt.modules.pollution_hunter import grids
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import gee


def test_month_range_and_dates_cross_the_year_end():
    assert grids.month_range("2022-11", "2023-02") == ["2022-11", "2022-12", "2023-01", "2023-02"]
    assert grids.month_range("2024-05", "2024-05") == ["2024-05"]
    assert grids.month_range("2024-06", "2024-05") == []
    assert grids.month_dates("2022-12") == ("2022-12-01", "2023-01-01")
    assert grids.month_dates("2024-02") == ("2024-02-01", "2024-03-01")


def test_latest_complete_month_needs_the_last_day():
    assert grids.latest_complete_month("2026-10-31") == "2026-10"
    assert grids.latest_complete_month("2026-11-05") == "2026-10"
    assert grids.latest_complete_month("2026-10-30") == "2026-09"
    assert grids.latest_complete_month("2025-01-12") == "2024-12"
    assert grids.latest_complete_month("2024-02-29") == "2024-02"


def test_grid_paths_name_period_scope_and_step(tmp_path):
    assert grids.step_tag(0.1) == "0p1deg" and grids.step_tag(0.02) == "0p02deg"
    path = grids.grid_path("2024-06", "region", 0.04, tmp_path)
    assert path == tmp_path / "no2_mean_2024-06_region_0p04deg.tif"


def test_jobs_cover_the_world_and_the_region_on_whole_cells():
    cfg = load_config()["layers"]
    region = tuple(cfg["region_bounds_deg"])
    jobs = grids.monthly_jobs(cfg, ["2022-07", "2022-08"])
    assert [(j.period, j.scope) for j in jobs] == [
        ("2022-07", "global"), ("2022-07", "region"), ("2022-08", "global"), ("2022-08", "region"),
    ]  # fmt: skip
    assert jobs[0].bounds == gee.WORLD and jobs[1].bounds == region
    assert (jobs[1].start, jobs[1].end) == ("2022-07-01", "2022-08-01")
    (annual,) = grids.annual_jobs(cfg, 2024)
    assert (annual.start, annual.end, annual.scope) == ("2024-01-01", "2025-01-01", "region")
    # The region is a whole number of cells on both of its grids.
    for step in (cfg["region_step_annual_deg"], cfg["region_step_monthly_deg"]):
        width, height = gee.grid_shape(region, step)
        assert np.isclose(width * step, region[2] - region[0])
        assert np.isclose(height * step, region[3] - region[1])


def test_run_skips_grids_that_are_already_there(tmp_path, capsys):
    cfg = load_config()["layers"]
    jobs = grids.monthly_jobs(cfg, ["2022-07"])
    for job in jobs:
        job.path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        job.path(tmp_path).write_bytes(b"")
    grids.run(jobs, measure_grids=0, chunk=600, grid_dir=tmp_path)  # no Earth Engine call is made
    assert "2 of 2 grids already there" in capsys.readouterr().out


def test_download_image_stitches_windows_and_enters_the_context_per_call(monkeypatch):
    truth = np.arange(40 * 60, dtype="float32").reshape(40, 60)
    monkeypatch.setattr(
        gee, "_ee_fetch", lambda image, bounds, step: lambda c, r, w, h: truth[r : r + h, c : c + w]
    )
    entered = []

    class Around:
        def __enter__(self):
            entered.append(1)

        def __exit__(self, *exc):
            return False

    out = gee.download_image(None, (0.0, 0.0, 6.0, 4.0), 0.1, chunk=25, around=Around)
    np.testing.assert_array_equal(out, truth)
    assert len(entered) == 6  # 3 x 2 windows
