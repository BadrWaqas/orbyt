"""Distances and local map offsets on a sphere. Units: degrees in, kilometres out."""

from __future__ import annotations

import numpy as np

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km. Accepts scalars or arrays, broadcast together."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def offsets_km(lat0: float, lon0: float, lats, lons) -> tuple[np.ndarray, np.ndarray]:
    """East and north offsets in km of points from (lat0, lon0), flat-earth around the origin.

    Good to a fraction of a percent within a few hundred km, the scale used here. Same
    convention as rotate_scene() in core_math.py.
    """
    east = np.radians(np.asarray(lons) - lon0) * EARTH_R_KM * np.cos(np.radians(lat0))
    north = np.radians(np.asarray(lats) - lat0) * EARTH_R_KM
    return east, north
