// The global NO2 layer: scale, colour ramp and tile set (PLAN.md 9.2).
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

export const NO2_YEAR = 2024;
export const NO2_TILES_PATH = `/tiles/no2-${NO2_YEAR}/{z}/{x}/{y}.png`;
export const NO2_TILES_MAX_ZOOM = 4;
export const NO2_ATTRIBUTION = `Contains modified Copernicus Sentinel data ${NO2_YEAR}`;

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

/** The ramp as a CSS gradient, with the same opacity steps the map tiles carry. */
export function no2RampGradient(): string {
  const stops = NO2_RAMP.map(([pos, hex, alpha]) => `${rgba(hex, alpha)} ${pos * 100}%`);
  return `linear-gradient(to right, ${stops.join(", ")})`;
}
