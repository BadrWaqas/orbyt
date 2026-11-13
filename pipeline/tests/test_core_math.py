"""Synthetic end-to-end tests: can the pipeline recover a known emission,
and does it refuse to report one where there is none?"""
import warnings

import numpy as np
from scipy.ndimage import gaussian_filter

from orbyt.modules.pollution_hunter.core_math import (
    EARTH_R_KM,
    M_NO2,
    SEC_PER_YEAR,
    daily_flux_density,
    estimate_emission,
    failed_gates,
)

LAT0, LON0 = 51.27, 19.33
YR = np.arange(-80.0, 80.1, 2.0)          # crosswind grid, km
T = np.arange(-2.0, 6.01, 0.1)            # travel-time grid, hours


def mol_s(nox_t_yr):
    """NOx tonnes per year (as NO2) to NO2 mol/s, the inverse of the pipeline's conversion."""
    return nox_t_yr * 1000.0 / SEC_PER_YEAR / M_NO2 / 1.38


def make_days(n_days, centre_t_yr, neighbour_t_yr, tau_h=3.5, seed=0, dir_err_deg=15.0,
              spd_err=0.15, noise=10e-6, cloud_frac=0.3):
    """Daily scenes: decaying Gaussian plumes, noise, cloud gaps, imperfect wind."""
    rng = np.random.default_rng(seed)
    lats = np.arange(LAT0 - 2.4, LAT0 + 2.4001, 0.03)
    lons = np.arange(LON0 - 3.8, LON0 + 3.8001, 0.03)
    LON, LAT = np.meshgrid(lons, lats)
    X = np.radians(LON - LON0) * EARTH_R_KM * np.cos(np.radians(LAT0))
    Y = np.radians(LAT - LAT0) * EARTH_R_KM
    days = []
    while len(days) < n_days:
        w = float(np.clip(rng.weibull(2.0) * 6.0, 0.5, 14.0))
        if w < 2.0:                                   # calm days are excluded
            continue
        th = rng.uniform(0, 2 * np.pi)

        def plume(xs, ys, q):
            c, s = np.cos(th), np.sin(th)
            xr = c * (X - xs) + s * (Y - ys)
            yr = -s * (X - xs) + c * (Y - ys)
            sig = np.sqrt(3.0**2 + (0.10 * np.clip(xr, 0, None))**2) * 1000.0
            col = (q / (np.sqrt(2 * np.pi) * sig * w)
                   * np.exp(-(yr * 1000.0)**2 / (2 * sig**2))
                   * np.exp(-np.clip(xr, 0, None) * 1000.0 / (w * tau_h * 3600.0)))
            return np.where(xr > 0, col, 0.0)

        f = plume(0, 0, mol_s(centre_t_yr)) + plume(38.0, 22.0, mol_s(neighbour_t_yr))
        f = gaussian_filter(f, sigma=(2.5 / 3.34, 2.5 / 2.09))   # pixel footprint blur
        f += 30e-6 + rng.normal(0, 8e-6) + 4e-6 * (X / 200.0)    # background + gradient
        f += gaussian_filter(rng.normal(0, noise, f.shape), 1.0) * 2.5
        mask = gaussian_filter(rng.normal(0, 1, f.shape), 8.0)
        f[mask > np.quantile(mask, 1 - cloud_frac)] = np.nan     # cloud gaps
        th_e = th + np.radians(rng.normal(0, dir_err_deg))       # reanalysis wind is not the truth
        w_e = w * (1 + rng.normal(0, spd_err))
        days.append(dict(field=f, u=w_e * np.cos(th_e), v=w_e * np.sin(th_e)))
    return lats, lons, days


def run(centre_t_yr, neighbour_t_yr, seed, n_days=120, n_boot=0, **kw):
    lats, lons, days = make_days(n_days, centre_t_yr, neighbour_t_yr, seed=seed, **kw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        flux = np.array([daily_flux_density(d["field"], lats, lons, LAT0, LON0,
                                            d["u"], d["v"], T, YR) for d in days])
    speeds = [np.hypot(d["u"], d["v"]) for d in days]
    return estimate_emission(flux, T, YR, speeds, n_boot=n_boot)


def test_recovers_large_source():
    ratios = [run(20000.0, 5000.0, s)["nox_t_yr"] / 20000.0 for s in range(4)]
    assert 0.9 < np.mean(ratios) < 1.1


def test_recovers_small_source():
    ratios = [run(4000.0, 1000.0, s)["nox_t_yr"] / 4000.0 for s in range(4)]
    assert 0.8 < np.mean(ratios) < 1.25


def test_large_source_passes_gates():
    assert failed_gates(run(20000.0, 5000.0, 0, n_boot=100)) == []


def test_empty_site_next_to_big_neighbour_is_rejected():
    assert failed_gates(run(0.0, 20000.0, 0, n_boot=100)) != []


def test_pure_noise_is_rejected():
    assert failed_gates(run(0.0, 0.0, 0, n_boot=100)) != []
