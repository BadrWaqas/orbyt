import type { FeatureCollection, Point } from "geojson";
import maplibregl from "maplibre-gl";
import type { ExpressionSpecification, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";

import { formatTonnes } from "../../data/format";
import type { Finding } from "../../data/types";

// FacilityMarker (PLAN.md 9.6): a circle whose radius follows the square root of the reported
// tonnes, from 4 to 18 px, with a 1.5 px ring and a dark glass fill.
const SOURCE_ID = "ph-facilities";
const LAYER_ID = "ph-facilities";

const RADIUS_MIN_PX = 4;
const RADIUS_MAX_PX = 18;
const TONNES_AT_MAX_RADIUS = 20_000; // just above the largest reporter, so area tracks tonnes
// Seen from orbit the markers shrink to quiet pale dots, so Europe does not turn into one blob
// and the glow stays the loud thing. On the way down they open into rings with a dark centre.
const ORBIT_ZOOM = 1;
const FULL_SIZE_ZOOM = 5.5;
const ORBIT_SCALE = 0.22;
const RING_FROM_ZOOM = 2.6;
const RING_BY_ZOOM = 4.2;

const TOUCH_TARGET_PX = 44; // minimum touch target
const HOVER_REACH_PX = 6;
const FADE_IN_MS = 700;

// Mirrors --panel-solid, --raised, --ledger and --text. No finding has a verdict yet, so the
// ring takes the record colour: the size of each dot is a reported number.
const FILL = "#0D1218";
const FILL_HOVER = "#161D26";
const RING = "#E9E1D0";
const RING_HOVER = "#F2F4F7";

const isHovered: ExpressionSpecification = ["boolean", ["feature-state", "hover"], false];
const isSelected: ExpressionSpecification = ["boolean", ["feature-state", "selected"], false];

function fullRadiusPx(tonnes: number): number {
  const r = RADIUS_MAX_PX * Math.sqrt(Math.max(tonnes, 0) / TONNES_AT_MAX_RADIUS);
  return Math.min(RADIUS_MAX_PX, Math.max(RADIUS_MIN_PX, r));
}

/** The radius a marker is drawn at for a given zoom. Mirrors the circle-radius expression. */
function radiusAtZoom(fullRadius: number, zoom: number): number {
  const t = Math.min(1, Math.max(0, (zoom - ORBIT_ZOOM) / (FULL_SIZE_ZOOM - ORBIT_ZOOM)));
  return fullRadius * (ORBIT_SCALE + (1 - ORBIT_SCALE) * t);
}

/** Grows with the marker, from the orbit view to full size. */
function byZoom(orbit: unknown, full: unknown): ExpressionSpecification {
  return ["interpolate", ["linear"], ["zoom"], ORBIT_ZOOM, orbit, FULL_SIZE_ZOOM, full] as ExpressionSpecification;
}

/** Switches from the dot look to the ring look over a short zoom range. */
function dotToRing(dot: unknown, ring: unknown): ExpressionSpecification {
  return ["interpolate", ["linear"], ["zoom"], RING_FROM_ZOOM, dot, RING_BY_ZOOM, ring] as ExpressionSpecification;
}

function toGeoJson(findings: Finding[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: findings
      .filter((f) => f.claimed)
      .map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [f.subject.lon, f.subject.lat] },
        properties: {
          id: f.subject.id,
          name: f.subject.name,
          tonnes: f.claimed!.value,
          year: f.period.label,
          r: fullRadiusPx(f.claimed!.value),
        },
      })),
  };
}

interface Options {
  reducedMotion: boolean;
  onSelect: (subjectId: string) => void;
}

export interface FacilityMarkers {
  /** Mark one facility as selected and draw the expanding ring around it. Null clears it. */
  setSelected(finding: Finding | null): void;
  remove(): void;
}

export function addFacilityMarkers(
  map: MapLibreMap,
  findings: Finding[],
  { reducedMotion, onSelect }: Options,
): FacilityMarkers {
  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: toGeoJson(findings),
    promoteId: "id",
    attribution: "EEA", // kept short for the map corner, the panel names the full source
  });
  map.addLayer({
    id: LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    layout: { "circle-sort-key": ["-", ["get", "tonnes"]] }, // small dots sit on top of big ones
    paint: {
      "circle-radius": byZoom(["*", ORBIT_SCALE, ["get", "r"]], ["get", "r"]),
      "circle-color": dotToRing(RING, ["case", isHovered, FILL_HOVER, FILL]),
      "circle-stroke-color": ["case", ["any", isHovered, isSelected], RING_HOVER, RING],
      "circle-stroke-width": dotToRing(["case", isSelected, 1.5, 0], ["case", isSelected, 2.5, 1.5]),
      "circle-opacity": 0,
      "circle-stroke-opacity": 0,
      "circle-opacity-transition": { duration: reducedMotion ? 0 : FADE_IN_MS, delay: 0 },
      "circle-stroke-opacity-transition": { duration: reducedMotion ? 0 : FADE_IN_MS, delay: 0 },
    },
  });
  // Fade in from clear. As rings, the fill keeps the panel's 0.84 opacity so the glow shows
  // through. As dots they sit a little further back.
  map.setPaintProperty(LAYER_ID, "circle-opacity", dotToRing(0.6, 0.84));
  map.setPaintProperty(LAYER_ID, "circle-stroke-opacity", 1);

  /** The marker nearest to a screen point, if one lies within `reach` px of it. */
  const pick = (point: { x: number; y: number }, reach: number) => {
    const hits = map.queryRenderedFeatures(
      [
        [point.x - reach, point.y - reach],
        [point.x + reach, point.y + reach],
      ],
      { layers: [LAYER_ID] },
    );
    let best: (typeof hits)[number] | null = null;
    let bestDistance = Infinity;
    for (const hit of hits) {
      const [lon, lat] = (hit.geometry as Point).coordinates;
      const p = map.project([lon, lat]);
      const distance = Math.hypot(p.x - point.x, p.y - point.y);
      if (distance < bestDistance) {
        best = hit;
        bestDistance = distance;
      }
    }
    return best;
  };

  const onClick = (e: MapMouseEvent) => {
    const hit = pick(e.point, TOUCH_TARGET_PX / 2);
    if (hit) onSelect(String(hit.id));
  };
  map.on("click", onClick);

  // Hover: only where there is a pointer that can hover, so a tap never leaves a tooltip behind.
  const canHover = window.matchMedia("(hover: hover)").matches;
  const tip = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    focusAfterOpen: false,
    className: "marker-tip",
    maxWidth: "280px",
  });
  let hoveredId: string | null = null;
  const setHovered = (hit: ReturnType<typeof pick>) => {
    const id = hit ? String(hit.id) : null;
    if (id === hoveredId) return;
    if (hoveredId) map.setFeatureState({ source: SOURCE_ID, id: hoveredId }, { hover: false });
    hoveredId = id;
    map.getCanvas().style.cursor = hit ? "pointer" : "";
    if (!hit || !id) {
      tip.remove();
      return;
    }
    map.setFeatureState({ source: SOURCE_ID, id }, { hover: true });
    const { name, tonnes, year, r } = hit.properties as {
      name: string;
      tonnes: number;
      year: string;
      r: number;
    };
    const body = document.createElement("div");
    const title = document.createElement("p");
    title.className = "marker-tip-name";
    title.textContent = name;
    const reported = document.createElement("p");
    reported.className = "marker-tip-reported";
    reported.textContent = `${formatTonnes(tonnes)} t of NOx reported for ${year}`;
    body.append(title, reported);
    const [lon, lat] = (hit.geometry as Point).coordinates;
    tip
      .setLngLat([lon, lat])
      .setOffset(Math.round(radiusAtZoom(r, map.getZoom())) + 8)
      .setDOMContent(body)
      .addTo(map);
  };
  const onMouseMove = (e: MapMouseEvent) => setHovered(pick(e.point, HOVER_REACH_PX));
  const onMouseOut = () => setHovered(null);
  if (canHover) {
    map.on("mousemove", onMouseMove);
    map.on("mouseout", onMouseOut);
    map.on("movestart", onMouseOut);
  }

  // Selection: a single expanding ring (1.6 s loop, see .selected-ring in design/index.css).
  const ringElement = document.createElement("div");
  ringElement.className = "selected-ring";
  ringElement.setAttribute("aria-hidden", "true");
  const ring = new maplibregl.Marker({ element: ringElement, opacityWhenCovered: "0" });
  let selected: { id: string; r: number } | null = null;
  const sizeRing = () => {
    if (!selected) return;
    const r = radiusAtZoom(selected.r, map.getZoom());
    ringElement.style.setProperty("--r", `${r.toFixed(1)}px`);
  };
  map.on("zoom", sizeRing);

  return {
    setSelected(finding) {
      if (selected) map.setFeatureState({ source: SOURCE_ID, id: selected.id }, { selected: false });
      if (!finding?.claimed) {
        selected = null;
        ring.remove();
        return;
      }
      selected = { id: finding.subject.id, r: fullRadiusPx(finding.claimed.value) };
      map.setFeatureState({ source: SOURCE_ID, id: selected.id }, { selected: true });
      sizeRing();
      ring.setLngLat([finding.subject.lon, finding.subject.lat]).addTo(map);
    },
    remove() {
      map.off("click", onClick);
      map.off("mousemove", onMouseMove);
      map.off("mouseout", onMouseOut);
      map.off("movestart", onMouseOut);
      map.off("zoom", sizeRing);
      tip.remove();
      ring.remove();
      if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    },
  };
}
