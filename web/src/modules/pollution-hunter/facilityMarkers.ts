import type { FeatureCollection, Point } from "geojson";
import maplibregl from "maplibre-gl";
import type { ExpressionSpecification, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";

import { formatTonnes } from "../../data/format";
import type { Finding } from "../../data/types";

// FacilityMarker (PLAN.md 9.6): a circle whose radius follows the square root of the reported
// tonnes, from 4 to 18 px, with a 1.5 px ring and a dark glass fill.
//
// The marker speaks in the two voices of 9.1. The ring is the record: its size is a reported
// number, so it takes the ledger tone until a verdict gives it a verdict colour. The core is the
// instrument: a facility the satellite has measured carries a small amber light at its centre.
const SOURCE_ID = "ph-facilities";
const LAYER_ID = "ph-facilities";
const HALO_LAYER_ID = "ph-facilities-halo";
const CORE_LAYER_ID = "ph-facilities-core";

const RADIUS_MIN_PX = 4;
const RADIUS_MAX_PX = 18;
const TONNES_AT_MAX_RADIUS = 20_000; // just above the largest reporter, so area tracks tonnes
// Seen from orbit the markers shrink to quiet pale dots, so Europe does not turn into one blob
// and the glow stays the loud thing. On the way down they open into rings.
const ORBIT_ZOOM = 1;
const FULL_SIZE_ZOOM = 5.5;
const ORBIT_SCALE = 0.22;
const RING_FROM_ZOOM = 2.6;
const RING_BY_ZOOM = 4.2;

const TOUCH_TARGET_PX = 44; // minimum touch target
const HOVER_REACH_PX = 6;
const FADE_IN_MS = 700;
const CORE_RADIUS_PX = 3;
const HALO_REACH_PX = 9; // how far the soft light reaches beyond the ring

// Mirrors --panel-solid, --ledger, --text and --hue-no2-glow.
const GLASS = "#0D1218";
const LEDGER = "#E9E1D0";
const TEXT = "#F2F4F7";
const AMBER = "#FFB02E";

// The glass is kept thin, so the NO2 glow and the neighbours show through where rings overlap.
const FILL_OPACITY = 0.42;
const FILL_OPACITY_HOVER = 0.7;
const RING_OPACITY = 0.85;
// While one facility is open, the others step back.
const RING_OPACITY_ASIDE = 0.4;
const FILL_OPACITY_ASIDE = 0.25;

const isHovered: ExpressionSpecification = ["boolean", ["feature-state", "hover"], false];
const isSelected: ExpressionSpecification = ["boolean", ["feature-state", "selected"], false];
const isMeasured: ExpressionSpecification = ["==", ["get", "measured"], true];
const isLit: ExpressionSpecification = ["any", isHovered, isSelected];

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

function fillOpacity(aside: boolean): ExpressionSpecification {
  const rest = aside ? FILL_OPACITY_ASIDE : FILL_OPACITY;
  // Selected, the glass clears and takes a little of the ring's light: a lens, not a black dot.
  return dotToRing(
    ["case", isLit, 1, aside ? 0.4 : 0.7],
    ["case", isSelected, 0.16, isHovered, FILL_OPACITY_HOVER, rest],
  );
}

function ringOpacity(aside: boolean): ExpressionSpecification {
  return ["case", isLit, 1, aside ? RING_OPACITY_ASIDE : RING_OPACITY];
}

function haloOpacity(): ExpressionSpecification {
  return ["case", isSelected, 0.5, isMeasured, 0.4, 0];
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
          name: f.subject.display_name ?? f.subject.name,
          tonnes: f.claimed!.value,
          year: f.period.label,
          r: fullRadiusPx(f.claimed!.value),
          measured: f.observed !== null,
        },
      })),
  };
}

interface Options {
  /** Draw underneath this layer, so place names stay readable on top of the markers. */
  beforeId: string;
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
  { beforeId, reducedMotion, onSelect }: Options,
): FacilityMarkers {
  const fade = { duration: reducedMotion ? 0 : FADE_IN_MS, delay: 0 };
  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: toGeoJson(findings),
    promoteId: "id",
    attribution: "EEA", // kept short for the map corner, the panel names the full source
  });

  // A soft light behind the marker: amber where the satellite has an estimate, paper white
  // around the selected one.
  map.addLayer(
    {
      id: HALO_LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      paint: {
        "circle-radius": byZoom(["+", ["*", ORBIT_SCALE, ["get", "r"]], 3], ["+", ["get", "r"], HALO_REACH_PX]),
        "circle-color": ["case", isSelected, LEDGER, AMBER],
        "circle-blur": 1,
        "circle-opacity": 0,
        "circle-opacity-transition": fade,
      },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      layout: { "circle-sort-key": ["-", ["get", "tonnes"]] }, // small markers sit on top of big ones
      paint: {
        "circle-radius": byZoom(["*", ORBIT_SCALE, ["get", "r"]], ["get", "r"]),
        "circle-color": dotToRing(["case", isMeasured, AMBER, LEDGER], ["case", isSelected, LEDGER, GLASS]),
        "circle-stroke-color": ["case", isLit, TEXT, LEDGER],
        "circle-stroke-width": dotToRing(["case", isSelected, 1.5, 0], ["case", isSelected, 2, 1.5]),
        "circle-opacity": 0,
        "circle-stroke-opacity": 0,
        "circle-opacity-transition": fade,
        "circle-stroke-opacity-transition": fade,
      },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: CORE_LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      filter: isMeasured,
      paint: {
        "circle-radius": dotToRing(0, CORE_RADIUS_PX),
        "circle-color": AMBER,
        "circle-opacity": 0,
        "circle-opacity-transition": fade,
      },
    },
    beforeId,
  );

  // Fade in from clear.
  const paint = (aside: boolean) => {
    map.setPaintProperty(LAYER_ID, "circle-opacity", fillOpacity(aside));
    map.setPaintProperty(LAYER_ID, "circle-stroke-opacity", ringOpacity(aside));
  };
  paint(false);
  map.setPaintProperty(HALO_LAYER_ID, "circle-opacity", haloOpacity());
  map.setPaintProperty(CORE_LAYER_ID, "circle-opacity", 1);

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
    const { name, tonnes, year, r, measured } = hit.properties as {
      name: string;
      tonnes: number;
      year: string;
      r: number;
      measured: boolean;
    };
    const body = document.createElement("div");
    const title = document.createElement("p");
    title.className = "marker-tip-name";
    title.textContent = name;
    const reported = document.createElement("p");
    reported.className = "marker-tip-reported";
    reported.textContent = `${formatTonnes(tonnes)} t of NOx reported for ${year}`;
    body.append(title, reported);
    if (measured) {
      const estimate = document.createElement("p");
      estimate.className = "marker-tip-measured";
      estimate.textContent = "Satellite estimate available";
      body.append(estimate);
    }
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
        paint(false);
        return;
      }
      selected = { id: finding.subject.id, r: fullRadiusPx(finding.claimed.value) };
      map.setFeatureState({ source: SOURCE_ID, id: selected.id }, { selected: true });
      paint(true);
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
      for (const id of [CORE_LAYER_ID, LAYER_ID, HALO_LAYER_ID]) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    },
  };
}
