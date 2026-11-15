import type { No2Layers } from "./no2";

// The tiles of one NO2 layer, the annual mean or one month.
//
// A layer has tiles of its own for the whole world down to a shallow zoom, and for Europe a few
// zooms deeper (layers.json). Everywhere else a deeper tile is made here, from the part of the
// shallow tile above it, enlarged with smoothing. So the map can ask for any tile at any zoom
// and always gets a smooth picture: fine where the pipeline has a fine grid, soft elsewhere.

export interface TileSet {
  /** "2024" for the annual mean, "2024-06" for a month. */
  period: string;
  tileSize: number;
  /** Deepest zoom the whole world has tiles for. */
  globalMaxZoom: number;
  /** Deepest zoom the layer can be asked for. */
  maxZoom: number;
  /** The address of a tile, with {z}, {x} and {y} still to fill in. */
  template: string;
  url(z: number, x: number, y: number): string;
  /** Whether the layer has a file of its own for this tile. */
  has(z: number, x: number, y: number): boolean;
}

function makeSet(
  layers: No2Layers,
  period: string,
  spec: { max_zoom: number; region_tiles: Record<string, [number, number, number, number]> },
): TileSet {
  const template = window.location.origin + layers.tiles.replace("{period}", period);
  return {
    period,
    tileSize: layers.tile_size,
    globalMaxZoom: layers.global_max_zoom,
    maxZoom: spec.max_zoom,
    template,
    url: (z, x, y) => template.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y)),
    has(z, x, y) {
      if (z <= layers.global_max_zoom) return true;
      const range = spec.region_tiles[String(z)];
      return Boolean(range) && x >= range[0] && x <= range[2] && y >= range[1] && y <= range[3];
    },
  };
}

export function annualTileSet(layers: No2Layers): TileSet | null {
  return layers.annual ? makeSet(layers, layers.annual.period, layers.annual) : null;
}

export function monthTileSet(layers: No2Layers, month: string): TileSet | null {
  if (!layers.monthly?.periods.includes(month)) return null;
  return makeSet(layers, month, layers.monthly);
}

// deck.gl reads a tile's opacity apart from its colour, so the pixels are kept as they are in
// the file and not multiplied by their opacity. This is what its own image loader does too.
const AS_STORED: ImageBitmapOptions = { premultiplyAlpha: "none", colorSpaceConversion: "none" };

async function fetchBitmap(url: string, signal?: AbortSignal): Promise<ImageBitmap | null> {
  const response = await fetch(url, { signal });
  // A missing file is answered with the app's own page by the host, so the type is checked too.
  if (!response.ok || !(response.headers.get("content-type") ?? "").startsWith("image/")) return null;
  return createImageBitmap(await response.blob(), AS_STORED);
}

// The shallow tiles that deeper ones are cut from. A few stay in memory, since every deeper
// tile around the same place needs the same one.
const PARENT_CACHE_SIZE = 24;
const parents = new Map<string, Promise<ImageBitmap | null>>();

function parentBitmap(url: string): Promise<ImageBitmap | null> {
  let request = parents.get(url);
  if (request) {
    parents.delete(url); // put back as the newest
  } else {
    request = fetchBitmap(url).catch(() => null);
    void request.then((bitmap) => {
      if (!bitmap && parents.get(url) === request) parents.delete(url); // try again next time
    });
    if (parents.size >= PARENT_CACHE_SIZE) parents.delete(parents.keys().next().value as string);
  }
  parents.set(url, request);
  return request;
}

const DERIVED_SIZE_PX = 256;
// The part cut out is taken with a rim, so the pixels at its edge are blended with their real
// neighbours and two tiles made this way meet without a crease.
const RIM_PX = 2;

/** A tile the layer has no file for: the matching part of the shallow tile above it, enlarged. */
async function derivedTile(set: TileSet, z: number, x: number, y: number): Promise<ImageBitmap | null> {
  const g = set.globalMaxZoom;
  const up = z - g;
  const across = 2 ** g; // shallow tiles from one side of the world to the other
  const px = x >> up;
  const py = y >> up;
  const parent = await parentBitmap(set.url(g, px, py));
  if (!parent) return null;
  const size = parent.width;
  const side = size / 2 ** up; // the part's width in the parent's pixels
  const left = (x - (px << up)) * side;
  const top = (y - (py << up)) * side;

  // The part with its rim, pixel for pixel. At the parent's edge the rim lies in the shallow
  // tile next door, so that one is fetched too. Without it a steep glow that crosses the edge
  // would show the edge as a line.
  const span = side + 2 * RIM_PX;
  const cut = document.createElement("canvas");
  cut.width = span;
  cut.height = span;
  const cutCtx = cut.getContext("2d");
  if (!cutCtx) return null;
  for (const dy of [-1, 0, 1]) {
    const row = py + dy;
    if (row < 0 || row >= across) continue; // nothing past the poles
    if (dy !== 0 && (dy < 0 ? top - RIM_PX >= 0 : top + side + RIM_PX <= size)) continue;
    for (const dx of [-1, 0, 1]) {
      if (dx !== 0 && (dx < 0 ? left - RIM_PX >= 0 : left + side + RIM_PX <= size)) continue;
      const source =
        dx === 0 && dy === 0 ? parent : await parentBitmap(set.url(g, (px + dx + across) % across, row));
      if (source) cutCtx.drawImage(source, dx * size - (left - RIM_PX), dy * size - (top - RIM_PX));
    }
  }

  const scale = DERIVED_SIZE_PX / side;
  const canvas = document.createElement("canvas");
  canvas.width = DERIVED_SIZE_PX;
  canvas.height = DERIVED_SIZE_PX;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(cut, -RIM_PX * scale, -RIM_PX * scale, span * scale, span * scale);
  return createImageBitmap(canvas, AS_STORED);
}

/** One tile of a layer as an image, or null where there is none. Never rejects. */
export async function loadTile(
  set: TileSet,
  z: number,
  x: number,
  y: number,
  signal?: AbortSignal,
): Promise<ImageBitmap | null> {
  try {
    if (set.has(z, x, y)) return await fetchBitmap(set.url(z, x, y), signal);
    return await derivedTile(set, z, x, y);
  } catch {
    return null; // the request was dropped or the image did not decode
  }
}
