// The global NO2 layer: scale, colour ramp and tile sets (PLAN.md 9.2).
// The ramp and the scale mirror RAMP, LO_UMOL and HI_UMOL in
// pipeline/orbyt/modules/pollution_hunter/layers.py, which colours the tiles.

/** Position on the ramp, colour, opacity. Lightness rises at every step. */
export const NO2_RAMP: readonly (readonly [number, string, number])[] = [
  [0.0, "#4F1C00", 0.0],
  [0.15, "#7D3501", 0.35],
  [0.35, "#AF5504", 0.6],
  [0.55, "#D97A05", 0.8],
  [0.75, "#F5A420", 0.9],
  [0.9, "#FCD583", 0.95],
  [1.0, "#FDF6D8", 1.0],
];

/** Tropospheric column in micromol/m2. Clipped at both ends, square-root scale in between. */
export const NO2_LO_UMOL = 20;
export const NO2_HI_UMOL = 250;

/** The year of the annual mean, the layer the module opens with. */
export const NO2_YEAR = 2024;
export const NO2_ATTRIBUTION = `Contains modified Copernicus Sentinel data ${NO2_YEAR}`;

/** First and last tile of a zoom that a layer has for the region: x0, y0, x1, y1, all included. */
type TileRange = [number, number, number, number];

interface LayerTiles {
  /** Deepest zoom with tiles, inside the region. */
  max_zoom: number;
  /** The region's tiles at each zoom past `global_max_zoom`. */
  region_tiles: Record<string, TileRange>;
}

/**
 * /data/v1/pollution-hunter/layers.json (PLAN.md 2.5), written by the pipeline's layers step.
 * A layer covers the whole world down to `global_max_zoom` and Europe on a finer grid below that.
 */
export interface No2Layers {
  /** Tile address with {period}, {z}, {x} and {y}. */
  tiles: string;
  tile_size: number;
  global_max_zoom: number;
  /** West, south, east, north of the region with the finer grid. */
  region_bounds: [number, number, number, number];
  annual: (LayerTiles & { period: string }) | null;
  monthly: (LayerTiles & { periods: string[] }) | null;
  attribution: string;
}

const LAYERS_URL = "/data/v1/pollution-hunter/layers.json";
let layersRequest: Promise<No2Layers> | null = null;

/** The layer manifest. Fetched once, and asked for early so it is there before the map is. */
export function loadNo2Layers(): Promise<No2Layers> {
  layersRequest ??= fetch(LAYERS_URL).then((response) => {
    if (!response.ok) throw new Error(`${LAYERS_URL} answered ${response.status}`);
    return response.json() as Promise<No2Layers>;
  });
  return layersRequest;
}

// The glow (PLAN.md 9.6, PlumeLayer for M7). The tiles are added to the map as light, with
// their opacity raised to this power first. Above 1 it dims the faint end of the ramp, so wide
// areas of slightly raised NO2 stay dark and the plumes carry the picture.
export const NO2_GLOW_GAMMA = 1.6;
/** The blurred copy under the sharp layer. */
export const NO2_HALO_OPACITY = 0.4;
/** A second, much wider and fainter blur: the haze over a whole industrial region. */
export const NO2_BLOOM_OPACITY = 0.3;

/** Where a column value sits on the ramp, from 0 to 1. */
export function no2RampPosition(umol: number): number {
  const lo = Math.sqrt(NO2_LO_UMOL);
  const hi = Math.sqrt(NO2_HI_UMOL);
  const t = (Math.sqrt(Math.max(umol, 0)) - lo) / (hi - lo);
  return Math.min(1, Math.max(0, t));
}

function rgba(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** The ramp as a CSS gradient, with the same opacity curve the glow on the map has. */
export function no2RampGradient(): string {
  const stops = NO2_RAMP.map(
    ([pos, hex, alpha]) => `${rgba(hex, Number((alpha ** NO2_GLOW_GAMMA).toFixed(3)))} ${pos * 100}%`,
  );
  return `linear-gradient(to right, ${stops.join(", ")})`;
}
