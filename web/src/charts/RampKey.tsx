import { NO2_RAMP } from "../modules/pollution-hunter/no2";

// Colour key for the panel images. They use the plume ramp with its opacity laid over the night
// ocean colour, on a linear scale (pipeline: evidence.colourise_glow).
const BASE = [0x04, 0x07, 0x0b]; // --earth-ocean

function overBase(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const rgb = [n >> 16, (n >> 8) & 255, n & 255];
  const mixed = rgb.map((c, i) => Math.round(c * alpha + BASE[i] * (1 - alpha)));
  return `rgb(${mixed.join(", ")})`;
}

const GRADIENT = `linear-gradient(to right, ${NO2_RAMP.map(
  ([pos, hex, alpha]) => `${overBase(hex, alpha)} ${pos * 100}%`,
).join(", ")})`;

interface Props {
  /** The value at the top of the ramp, micromol/m2. */
  fullScale: number;
  /** True when values above the full scale exist and take the top colour. */
  clipped?: boolean;
}

export function RampKey({ fullScale, clipped = false }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="axis-text">0</span>
      <span
        role="img"
        aria-label={`Colour scale from 0 to ${fullScale} micromoles of NO2 per square metre above background. Brighter means more.`}
        className="legend-ramp block w-24"
        style={{ backgroundImage: GRADIENT }}
      />
      <span className="axis-text">
        {fullScale}
        {clipped ? "+" : ""} µmol/m² above background
      </span>
    </div>
  );
}
