"""Populated places for the isolation rule (PLAN.md 4.5).

Source: Natural Earth 1:10m populated places, public domain (naturalearthdata.com). The
``pop_max`` field is the largest population figure for the place, which for big cities is the
urban agglomeration, not the municipality. That is the right size for "how much NO2 does this
place put into the air".

    uv run python -m orbyt.sources.cities
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from orbyt.core.geo import haversine_km

SOURCE = "Natural Earth 1:10m populated places (simple), version 5.1.2"
URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip"
REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "cities"
SHAPEFILE = RAW_DIR / "ne" / "ne_10m_populated_places_simple.shp"


@dataclass(frozen=True)
class Cities:
    """Parallel arrays, one entry per populated place."""

    name: np.ndarray
    country: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    population: np.ndarray  # pop_max

    def __len__(self) -> int:
        return len(self.name)

    def near(self, lat: float, lon: float, radius_km: float, min_pop: float) -> list[dict]:
        """Places of at least ``min_pop`` within ``radius_km``, largest first."""
        dist = haversine_km(lat, lon, self.lat, self.lon)
        idx = np.where((dist <= radius_km) & (self.population >= min_pop))[0]
        idx = idx[np.argsort(-self.population[idx])]
        return [
            {
                "name": str(self.name[i]),
                "country": str(self.country[i]),
                "population": int(self.population[i]),
                "distance_km": float(dist[i]),
            }
            for i in idx
        ]


def download(raw_dir: Path = RAW_DIR) -> Path:
    """Fetch and unpack the shapefile once. Returns the .shp path."""
    shp = raw_dir / "ne" / SHAPEFILE.name
    if shp.exists():
        return shp
    with urllib.request.urlopen(URL, timeout=120) as resp:  # noqa: S310 (fixed https URL)
        data = resp.read()
    (raw_dir / "ne").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(raw_dir / "ne")
    return shp


def load_cities(path: Path = SHAPEFILE) -> Cities:
    import shapefile

    reader = shapefile.Reader(str(path), encoding="utf-8")
    rows = [
        (r["nameascii"], r["adm0name"], r["latitude"], r["longitude"], r["pop_max"])
        for r in reader.iterRecords()
    ]
    name, country, lat, lon, pop = zip(*rows, strict=True)
    return Cities(
        np.array(name),
        np.array(country),
        np.array(lat, dtype=float),
        np.array(lon, dtype=float),
        np.array(pop, dtype=float),
    )


def main() -> None:
    path = download()
    cities = load_cities(path)
    big = int((cities.population >= 200_000).sum())
    print(f"{SOURCE}: {len(cities)} places, {big} of 200,000 or more")


if __name__ == "__main__":
    main()
