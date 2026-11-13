"""The daily background plane (M3.5): unit checks, and the synthetic scene that the single
upwind median failed, a regional gradient together with a prevailing wind."""

import warnings

import numpy as np
from scipy.ndimage import gaussian_filter

from orbyt.modules.pollution_hunter.core_math import (
    EARTH_R_KM,
    M_NO2,
    SEC_PER_YEAR,
    background_plane,
    daily_flux_density,
    estimate_emission,
    failed_gates,
)

LAT0, LON0 = 51.27, 19.33
YR = np.arange(-80.0, 80.1, 2.0)  # crosswind grid, km
T = np.arange(-2.0, 6.01, 0.1)  # travel-time grid, hours
X_SCENE = np.arange(-40.0, 120.1, 4.0)
X_UP = np.arange(-70.0, -19.0, 2.0)


def plane(x, y, a=30e-6, bx=4e-8, by=-2e-8):
    return a + bx * x[None, :] + by * y[:, None]


def test_plane_is_recovered_under_a_plume_and_a_hotspot_in_one_flank():
    scene = plane(X_SCENE, YR)
    truth = scene.copy()
    scene[np.abs(YR) <= 20, :] += 80e-6  # the plume, outside the fitted cells
    hot = np.ix_(YR >= 70, (X_SCENE >= 20) & (X_SCENE <= 60))
    scene[hot] += 50e-6  # another source in a flank, clipped by the robust fit
    got = background_plane(scene, plane(X_UP, YR), X_SCENE, X_UP, YR, flank_km=60.0)
    assert np.max(np.abs(got - truth)) < 1e-9


def test_plane_ignores_cloud_gaps_and_gives_up_when_almost_nothing_is_left():
    scene, up = plane(X_SCENE, YR), plane(X_UP, YR)
    scene[::2, ::3] = np.nan
    got = background_plane(scene, up, X_SCENE, X_UP, YR)
    assert np.max(np.abs(got - plane(X_SCENE, YR))) < 1e-9
    empty = np.full_like(scene, np.nan)
    up[:, 1:] = np.nan
    up[10:, :] = np.nan
    assert background_plane(empty, up, X_SCENE, X_UP, YR) is None


def test_a_tilted_background_with_no_source_gives_no_flux():
    lats = np.arange(LAT0 - 2.4, LAT0 + 2.4001, 0.03)
    lons = np.arange(LON0 - 3.8, LON0 + 3.8001, 0.03)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    field = 30e-6 + 6e-6 * (lon_grid - LON0) - 3e-6 * (lat_grid - LAT0)
    flux = daily_flux_density(field, lats, lons, LAT0, LON0, -4.0, 2.0, T, YR)
    assert np.nanmax(np.abs(flux)) < 1e-8  # the plume signal is of order 1e-4


def mol_s(nox_t_yr):
    return nox_t_yr * 1000.0 / SEC_PER_YEAR / M_NO2 / 1.38


def make_days(n_days, centre_t_yr, neighbour_t_yr, seed, gradient, prevailing, tau_h=3.5):
    """The scenes of test_core_math.py with a steeper regional gradient (mol/m2 per 200 km
    eastwards) and a wind that blows towards the east on a share ``prevailing`` of the days."""
    rng = np.random.default_rng(seed)
    lats = np.arange(LAT0 - 2.4, LAT0 + 2.4001, 0.03)
    lons = np.arange(LON0 - 3.8, LON0 + 3.8001, 0.03)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    east = np.radians(lon_grid - LON0) * EARTH_R_KM * np.cos(np.radians(LAT0))
    north = np.radians(lat_grid - LAT0) * EARTH_R_KM
    days = []
    while len(days) < n_days:
        w = float(np.clip(rng.weibull(2.0) * 6.0, 0.5, 14.0))
        if w < 2.0:
            continue
        th = rng.uniform(0, 2 * np.pi)
        if rng.uniform() < prevailing:
            th = rng.normal(0.0, np.radians(35.0))
        c, s = np.cos(th), np.sin(th)
        f = np.zeros_like(east)
        for xs, ys, q in ((0.0, 0.0, mol_s(centre_t_yr)), (38.0, 22.0, mol_s(neighbour_t_yr))):
            xr = c * (east - xs) + s * (north - ys)
            yr = -s * (east - xs) + c * (north - ys)
            sig = np.sqrt(3.0**2 + (0.10 * np.clip(xr, 0, None)) ** 2) * 1000.0
            col = (
                q
                / (np.sqrt(2 * np.pi) * sig * w)
                * np.exp(-((yr * 1000.0) ** 2) / (2 * sig**2))
                * np.exp(-np.clip(xr, 0, None) * 1000.0 / (w * tau_h * 3600.0))
            )
            f += np.where(xr > 0, col, 0.0)
        f = gaussian_filter(f, sigma=(2.5 / 3.34, 2.5 / 2.09))
        f += 30e-6 + rng.normal(0, 8e-6) + gradient * (east / 200.0)
        f += gaussian_filter(rng.normal(0, 10e-6, f.shape), 1.0) * 2.5
        mask = gaussian_filter(rng.normal(0, 1, f.shape), 8.0)
        f[mask > np.quantile(mask, 0.7)] = np.nan
        th_e = th + np.radians(rng.normal(0, 15.0))
        w_e = w * (1 + rng.normal(0, 0.15))
        days.append(dict(field=f, u=w_e * np.cos(th_e), v=w_e * np.sin(th_e)))
    return lats, lons, days


def run(centre_t_yr, neighbour_t_yr, seed, gradient, n_boot=0):
    lats, lons, days = make_days(120, centre_t_yr, neighbour_t_yr, seed, gradient, prevailing=0.6)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        flux = np.array(
            [
                daily_flux_density(d["field"], lats, lons, LAT0, LON0, d["u"], d["v"], T, YR)
                for d in days
            ]
        )
        speeds = [np.hypot(d["u"], d["v"]) for d in days]
        return estimate_emission(flux, T, YR, speeds, n_boot=n_boot)


# 12 micromol/m2 across 200 km, about a third of a typical European background column.
GRADIENT = 12e-6


def test_large_source_is_recovered_whichever_way_the_gradient_runs():
    for gradient in (GRADIENT, -GRADIENT):
        ests = [run(20000.0, 5000.0, s, gradient) for s in range(2)]
        assert 0.9 < np.mean([e["nox_t_yr"] for e in ests]) / 20000.0 < 1.1
        assert all(1.0 <= e["tau"] <= 8.0 for e in ests)


def test_small_source_is_recovered_whichever_way_the_gradient_runs():
    # The single upwind median gave about 3 and 8 times the truth here (docs/decisions.md).
    for gradient in (GRADIENT, -GRADIENT):
        ests = [run(4000.0, 1000.0, s, gradient) for s in range(2)]
        assert 0.8 < np.mean([e["nox_t_yr"] for e in ests]) / 4000.0 < 1.25
        assert all(1.0 <= e["tau"] <= 8.0 for e in ests)


def test_gradient_alone_is_still_rejected():
    assert failed_gates(run(0.0, 0.0, 0, GRADIENT, n_boot=100)) != []
