"""Orbyt Earth, Pollution Hunter: core plume math (reference implementation).

Units: columns in mol/m2, distances in km, wind in m/s, time in hours.

This is PLAN.md Appendix A with one change made in M3.5: the daily background is a plane
fitted outside the plume (background_plane) instead of one upwind median.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import curve_fit
from scipy.special import ndtr  # standard normal CDF

M_NO2 = 0.0460055                 # kg per mol
SEC_PER_YEAR = 365.25 * 24 * 3600
EARTH_R_KM = 6371.0088


def rotate_scene(field, lats, lons, lat0, lon0, u, v, xr, yr):
    """Resample one daily scene onto a wind-aligned grid centred on the source.

    field: 2D array [lat, lon], NaN = no data. lats and lons are ascending 1D arrays.
    u, v: wind components in m/s (the direction the wind blows TO).
    xr: 1D downwind distances in km (negative = upwind). yr: 1D crosswind km.
    Returns an array shaped [len(yr), len(xr)].
    """
    theta = np.arctan2(v, u)
    c, s = np.cos(theta), np.sin(theta)
    XR, YR = np.meshgrid(xr, yr)
    east, north = c * XR - s * YR, s * XR + c * YR      # back to east/north offsets
    lat = lat0 + np.degrees(north / EARTH_R_KM)
    lon = lon0 + np.degrees(east / (EARTH_R_KM * np.cos(np.radians(lat0))))
    interp = RegularGridInterpolator((lats, lons), field, method="linear",
                                     bounds_error=False, fill_value=np.nan)
    return interp(np.stack([lat.ravel(), lon.ravel()], axis=-1)).reshape(XR.shape)


def background_plane(scene, up, x_scene_km, x_up_km, yr, flank_km=60.0, clip=3.0, iters=3):
    """That day's background as a tilted plane, fitted to the cells outside the plume.

    scene: [len(yr), len(x_scene_km)] columns downwind. up: [len(yr), len(x_up_km)] columns in
    the upwind box. The fit uses the upwind box and both flanks of the scene (crosswind
    distance of at least flank_km). Cells far from the plane (other sources, noise) are clipped
    at ``clip`` robust standard deviations and the fit is repeated.
    Returns the plane on the scene grid, or None if there are too few cells.

    A single upwind value is not enough: where the region is dirtier on one side of the source
    and the wind has a prevailing direction, the difference stays in every downwind cell and
    grows with the width of the fan (M3.5, docs/decisions.md).
    """
    flank = np.abs(yr) >= flank_km
    x = np.concatenate([np.broadcast_to(x_scene_km[None, :], scene.shape)[flank].ravel(),
                        np.broadcast_to(x_up_km[None, :], up.shape).ravel()])
    y = np.concatenate([np.broadcast_to(yr[:, None], scene.shape)[flank].ravel(),
                        np.broadcast_to(yr[:, None], up.shape).ravel()])
    z = np.concatenate([scene[flank].ravel(), up.ravel()])
    ok = np.isfinite(z)
    if ok.sum() < 50:
        return None
    x, y, z = x[ok], y[ok], z[ok]
    keep = np.ones(len(z), dtype=bool)
    coef = np.array([np.median(z), 0.0, 0.0])
    for _ in range(iters):
        if keep.sum() < 50:
            break
        A = np.column_stack([np.ones(keep.sum()), x[keep], y[keep]])
        coef, *_ = np.linalg.lstsq(A, z[keep], rcond=None)
        resid = z - (coef[0] + coef[1] * x + coef[2] * y)
        centre = np.median(resid[keep])
        spread = 1.4826 * np.median(np.abs(resid[keep] - centre))
        if spread <= 0:
            break
        keep = np.abs(resid - centre) <= clip * spread
    return coef[0] + coef[1] * x_scene_km[None, :] + coef[2] * yr[:, None]


def daily_flux_density(field, lats, lons, lat0, lon0, u, v, t_hours, yr,
                       upwind_km=(-70.0, -20.0), flank_km=60.0):
    """One day's plume on a travel-time axis, as flux density in mol per m per s.

    Step 1: sample the scene at downwind distance x = wind * t, so every day
            shares one clock whatever its wind speed.
    Step 2: subtract that day's background: a plane fitted to the upwind box and
            to both flanks of the scene (background_plane).
    Step 3: multiply by wind speed (column * speed = flux through a 1 m wide gate).
    """
    speed = float(np.hypot(u, v))
    x_up = np.arange(upwind_km[0], upwind_km[1] + 1, 2.0)
    up = rotate_scene(field, lats, lons, lat0, lon0, u, v, x_up, yr)
    if np.isfinite(up).mean() < 0.3:
        return np.full((len(yr), len(t_hours)), np.nan)
    x_at_t = speed * np.asarray(t_hours) * 3.6               # km travelled after t hours
    scene = rotate_scene(field, lats, lons, lat0, lon0, u, v, x_at_t, yr)
    background = background_plane(scene, up, x_at_t, x_up, np.asarray(yr), flank_km)
    if background is None:
        return np.full((len(yr), len(t_hours)), np.nan)
    return (scene - background) * speed


def fan_half_width(t_hours, mean_wind_ms, base_km=20.0, growth=0.3, cap_km=76.0):
    """Crosswind half-width that widens downwind, so wind-direction error loses no mass.

    20 km at the source plus 0.3 km per km travelled (at the mean wind), capped.
    """
    return np.clip(base_km + growth * np.abs(mean_wind_ms * np.asarray(t_hours) * 3.6),
                   base_km, cap_km)


def stack_profile(daily, yr, half_width_km, min_days_frac=0.3, min_cover=0.8):
    """Average days cell by cell, then integrate across the wind.

    daily: [n_days, len(yr), n_x]. half_width_km: scalar or one value per column.
    Returns a 1D profile (input units times metres).
    """
    hw = np.broadcast_to(np.asarray(half_width_km, dtype=float), (daily.shape[2],))
    inside = np.abs(yr)[:, None] <= hw[None, :]
    n_in = inside.sum(axis=0)
    dy_m = (yr[1] - yr[0]) * 1000.0
    with warnings.catch_warnings():                    # all-NaN cells are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        cover = np.isfinite(daily).mean(axis=0)
        mean = np.where(cover >= min_days_frac, np.nanmean(daily, axis=0), np.nan)
        band = np.where(inside, mean, np.nan)
        prof = np.nanmean(band, axis=0) * n_in * dy_m  # mean of valid cells times full width
    prof[np.isfinite(band).sum(axis=0) / n_in < min_cover] = np.nan
    return prof


def emg(t, q, tau, sigma, t0, b):
    """Exponentially modified Gaussian: an exponential decay blurred by a Gaussian.

    q: value at the source before blurring. tau: e-folding scale. sigma: blur.
    t0: source offset. b: residual background. In the flux form q is the emission.
    """
    z = t - t0
    return q * np.exp(sigma**2 / (2 * tau**2) - z / tau) * ndtr(z / sigma - sigma / tau) + b


def fit_emg(t, y, tau_bounds=(0.5, 12.0), sigma_bounds=(0.05, 3.0), t0_bounds=(-1.5, 1.5)):
    """Least-squares EMG fit. Returns a dict of parameters, or None if it fails."""
    ok = np.isfinite(y)
    if ok.sum() < 12:
        return None
    t, y = t[ok], y[ok]
    q0 = max(float(np.max(y)), 1e-9)
    p0 = [q0, float(np.mean(tau_bounds)) / 2, float(np.mean(sigma_bounds)) / 2, 0.0, 0.0]
    lo = [0.0, tau_bounds[0], sigma_bounds[0], t0_bounds[0], -q0]
    hi = [10 * q0, tau_bounds[1], sigma_bounds[1], t0_bounds[1], q0]
    try:
        p, _ = curve_fit(emg, t, y, p0=p0, bounds=(lo, hi), maxfev=20000)
    except (RuntimeError, ValueError):
        return None
    resid = y - emg(t, *p)
    r2 = 1 - float(np.sum(resid**2) / np.sum((y - y.mean())**2))
    return dict(q=float(p[0]), tau=float(p[1]), sigma=float(p[2]), t0=float(p[3]),
                b=float(p[4]), r2=r2)


def nox_tonnes_per_year(q_no2_mol_s, nox_to_no2=1.38, amf_correction=1.0):
    """NO2 flux in mol/s to NOx in tonnes per year, expressed as NO2 mass."""
    return q_no2_mol_s * M_NO2 * nox_to_no2 * amf_correction * SEC_PER_YEAR / 1000.0


def estimate_emission(daily_flux, t_hours, yr, wind_speeds, n_boot=200, seed=0, **conv):
    """Stack daily flux densities, fit the EMG, bootstrap over days for a 95% interval.

    daily_flux: [n_days, len(yr), len(t_hours)] from daily_flux_density().
    wind_speeds: one speed per day (m/s), used only to size the integration fan.
    conv: nox_to_no2 and amf_correction passed to nox_tonnes_per_year().
    The interval covers sampling noise only. Systematic terms are added later.
    """
    rng = np.random.default_rng(seed)
    n = daily_flux.shape[0]
    hw = fan_half_width(t_hours, float(np.mean(wind_speeds)))
    best = fit_emg(t_hours, stack_profile(daily_flux, yr, hw))
    if best is None:
        return None
    boots = []
    for _ in range(n_boot):
        f = fit_emg(t_hours, stack_profile(daily_flux[rng.integers(0, n, n)], yr, hw))
        if f is not None:
            boots.append(nox_tonnes_per_year(f["q"], **conv))
    lo, hi = np.percentile(boots, [2.5, 97.5]) if len(boots) >= 50 else (np.nan, np.nan)
    return dict(best, nox_t_yr=nox_tonnes_per_year(best["q"], **conv),
                ci95=(float(lo), float(hi)), n_days=n, n_boot_ok=len(boots))


def failed_gates(est, min_days=40):
    """Names of the quality gates an estimate fails. Empty list means usable."""
    if est is None:
        return ["no_fit"]
    fails = []
    if est["n_days"] < min_days:
        fails.append("too_few_days")
    if est["r2"] < 0.85:
        fails.append("poor_fit")
    if abs(est["t0"]) > 0.5:                 # plume does not start at this site
        fails.append("source_offset")
    if not 1.0 <= est["tau"] <= 8.0:
        fails.append("lifetime_out_of_range")
    lo, hi = est["ci95"]
    if np.isfinite(lo) and est["nox_t_yr"] < 3.0 * (hi - lo) / 3.92:
        fails.append("low_signal_to_noise")
    return fails
