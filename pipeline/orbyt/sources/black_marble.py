"""NASA Black Marble night lights from GIBS, self-hosted as map tiles (M7.2, PLAN.md 3.1).

GIBS serves the VIIRS night lights composite as Web Mercator tiles. The site hosts its own copy
of zoom 0 to ``MAX_ZOOM`` (PLAN.md 7.1: nothing the site shows should depend on a server it does
not control), turned from the greyscale composite into the night-side palette of PLAN.md 9.2:
the ocean colour where there is no light, the lights as a pale warm white on top.

    uv run python -m orbyt.sources.black_marble

NASA asks for an acknowledgement (DATA_LICENSES.md).
"""

from __future__ import annotations

import argparse
import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "web" / "public" / "tiles" / "night"

# VIIRS_Night_Lights: the lights alone on black, one composite dated 2016-01-01 in the
# epsg3857 "best" endpoint. {z}/{row}/{col}, 256 px PNG.
LAYER = "VIIRS_Night_Lights"
DATE = "2016-01-01"
URL = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
    f"{LAYER}/default/{DATE}/GoogleMapsCompatible_Level8/{{z}}/{{y}}/{{x}}.png"
)
MAX_ZOOM = 5  # 1,365 tiles. Zoom 5 is 4.9 km a pixel at the equator, about the VIIRS 500 m x 10
USER_AGENT = "orbyt-earth (student project, github.com/BadrWaqas/orbyt)"

# PLAN.md 9.2 night-side Earth: where there is no light the tile is the land colour, so it
# vanishes into the map's land and the water fill covers the sea. The lights go from there
# through a warm grey to a pale paper white, so they read as city lights and never as the NO2
# amber. Positions on the light scale, 0 to 1.
LIGHT_RAMP: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (0x0C, 0x12, 0x19)),
    (0.08, (0x1A, 0x21, 0x2A)),
    (0.30, (0x5E, 0x62, 0x66)),
    (0.65, (0xB8, 0xB1, 0xA3)),
    (1.00, (0xF2, 0xEE, 0xE3)),
)
# The composite's grey is already stretched. A little gamma lifts the small towns.
GAMMA = 0.85


def recolour(grey: np.ndarray) -> np.ndarray:
    """Greyscale light [h, w] 0 to 255 to RGB uint8 [h, w, 3] on the night palette."""
    t = (grey.astype("float64") / 255.0) ** GAMMA
    pos = [p for p, _ in LIGHT_RAMP]
    rgb = np.array([c for _, c in LIGHT_RAMP], dtype="float64")
    out = np.zeros(grey.shape + (3,), dtype="uint8")
    for k in range(3):
        out[..., k] = np.rint(np.interp(t, pos, rgb[:, k])).astype("uint8")
    return out


def fetch(z: int, x: int, y: int, attempts: int = 4) -> bytes:
    request = Request(URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(3 * attempt)
    raise AssertionError("unreachable")


def convert(png: bytes) -> bytes:
    with Image.open(io.BytesIO(png)) as im:
        grey = np.asarray(im.convert("L"))
    out = io.BytesIO()
    Image.fromarray(recolour(grey), "RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def tiles(max_zoom: int) -> list[tuple[int, int, int]]:
    return [(z, x, y) for z in range(max_zoom + 1) for x in range(2**z) for y in range(2**z)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and recolour the night lights tiles")
    parser.add_argument("--max-zoom", type=int, default=MAX_ZOOM)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    def path_of(t: tuple[int, int, int]) -> Path:
        return args.out / str(t[0]) / str(t[1]) / f"{t[2]}.png"

    todo = [t for t in tiles(args.max_zoom) if not path_of(t).exists()]
    print(f"{len(todo)} tiles to fetch")

    def one(t: tuple[int, int, int]) -> int:
        z, x, y = t
        path = path_of(t)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = convert(fetch(z, x, y))
        path.write_bytes(data)
        return len(data)

    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, n in enumerate(pool.map(one, todo), 1):
            total += n
            if i % 100 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}, {total / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
