// A night globe drawn as lines of latitude and longitude, turned to face one place, with a
// glowing marker on it. The card for a facility with no satellite picture uses it, so that every
// card still shows where on Earth the facility is. No data, just the projection.

const R = 196; // globe radius in px
const CX = 260;
const CY = 300;
const STEP = 15; // degrees between lines
const SAMPLE = 3; // degrees between points along a line

const rad = (d: number) => (d * Math.PI) / 180;

/** Orthographic projection centred on (lat0, lon0). Null when the point is on the far side. */
function project(lat: number, lon: number, lat0: number, lon0: number): [number, number] | null {
  const dl = rad(lon - lon0);
  const cosC = Math.sin(rad(lat0)) * Math.sin(rad(lat)) + Math.cos(rad(lat0)) * Math.cos(rad(lat)) * Math.cos(dl);
  if (cosC <= 0) return null;
  const x = R * Math.cos(rad(lat)) * Math.sin(dl);
  const y = R * (Math.cos(rad(lat0)) * Math.sin(rad(lat)) - Math.sin(rad(lat0)) * Math.cos(rad(lat)) * Math.cos(dl));
  return [CX + x, CY - y];
}

/** A line of points as SVG path data, lifting the pen wherever it passes round the back. */
function pathFor(points: { lat: number; lon: number }[], lat0: number, lon0: number): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    const xy = project(p.lat, p.lon, lat0, lon0);
    if (!xy) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${xy[0].toFixed(1)} ${xy[1].toFixed(1)}`;
    pen = true;
  }
  return d;
}

function gratPaths(lat0: number, lon0: number): string[] {
  const paths: string[] = [];
  for (let lon = -180; lon < 180; lon += STEP) {
    const pts = [];
    for (let lat = -90; lat <= 90; lat += SAMPLE) pts.push({ lat, lon });
    paths.push(pathFor(pts, lat0, lon0));
  }
  for (let lat = -75; lat <= 75; lat += STEP) {
    const pts = [];
    for (let lon = -180; lon <= 180; lon += SAMPLE) pts.push({ lat, lon });
    paths.push(pathFor(pts, lat0, lon0));
  }
  return paths.filter(Boolean);
}

function coordText(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
}

interface Props {
  lat: number;
  lon: number;
  /** The amber marker and the coordinates under the globe. Off for the home card. */
  marker?: boolean;
}

export function Graticule({ lat, lon, marker = true }: Props) {
  return (
    <svg className="sc-globe" viewBox="0 0 520 630" width="520" height="630">
      <defs>
        <radialGradient id="sc-sea" cx="42%" cy="38%" r="75%">
          <stop offset="0" stopColor="#0c1219" />
          <stop offset="1" stopColor="#04070b" />
        </radialGradient>
        <radialGradient id="sc-limb" cx="50%" cy="50%" r="50%">
          <stop offset="0.9" stopColor="#7cc4ff" stopOpacity="0" />
          <stop offset="0.97" stopColor="#7cc4ff" stopOpacity="0.22" />
          <stop offset="1" stopColor="#7cc4ff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="sc-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#ffb02e" stopOpacity="0.55" />
          <stop offset="1" stopColor="#ffb02e" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={CX} cy={CY} r={R * 1.12} fill="url(#sc-limb)" />
      <circle cx={CX} cy={CY} r={R} fill="url(#sc-sea)" stroke="#2a3440" strokeWidth="1" />
      <g fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="1">
        {gratPaths(lat, lon).map((d, i) => (
          <path key={i} d={d} />
        ))}
      </g>
      {marker && (
        <>
          <circle cx={CX} cy={CY} r="46" fill="url(#sc-glow)" />
          <circle cx={CX} cy={CY} r="17" fill="none" stroke="#ffb02e" strokeOpacity="0.55" strokeWidth="1.5" />
          <circle cx={CX} cy={CY} r="6.5" fill="#fdf6d8" />
          <text x={CX} y={CY + R + 52} textAnchor="middle" className="sc-coord">
            {coordText(lat, lon)}
          </text>
        </>
      )}
    </svg>
  );
}
