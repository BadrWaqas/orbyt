import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";

// Night-side Earth. Colours mirror the --earth-* tokens in design/tokens.css (PLAN.md 9.2).
// MapLibre paints on a WebGL canvas and cannot read CSS variables, so they are repeated here.
const OCEAN = "#04070B";
const LAND = "#0C1219";
const BORDER = "#2A3440";
const LABEL = "#8A94A3";
const LABEL_MINOR = "#7D8794";

/** Data layers are inserted below this one, so borders and labels stay on top of them. */
export const FIRST_OVERLAY_LAYER_ID = "boundary-country";
/** Markers are inserted below this one, so place names are never covered by a marker. */
export const FIRST_LABEL_LAYER_ID = "label-country-major";

const TILES = "https://tiles.openfreemap.org";
const placeName: ExpressionSpecification = ["coalesce", ["get", "name_en"], ["get", "name"]];

// Night lights (M7.2, PLAN.md 3.1): NASA Black Marble, self-hosted and recoloured onto the
// night palette by pipeline/orbyt/sources/black_marble.py. The low zoom base: from orbit the
// cities glow under the NO2, and as the camera comes down the vector map takes over, so the
// lights never turn into enlarged pixels at street level.
export const NIGHT_TILES_PATH = "/tiles/night/{z}/{x}/{y}.png";
export const NIGHT_TILES_MAX_ZOOM = 5;
export const NIGHT_ATTRIBUTION = "Night lights: NASA Black Marble";
const NIGHT_FADE_FROM_ZOOM = 5;
const NIGHT_FADE_TO_ZOOM = 7.5;

export const nightStyle: StyleSpecification = {
  version: 8,
  name: "Orbyt night",
  projection: { type: "globe" },
  sky: {
    // Kept well below 1 so the haze reads as a thin limb glow and never hides the map.
    "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.3, 5, 0.3, 7, 0],
  },
  // Anchored to the viewport so the lit limb stays put while the globe spins underneath it.
  light: { anchor: "viewport", position: [1.5, 60, 50] },
  glyphs: `${TILES}/fonts/{fontstack}/{range}.pbf`,
  sources: {
    openmaptiles: { type: "vector", url: `${TILES}/planet` },
    night: {
      type: "raster",
      tiles: [NIGHT_TILES_PATH],
      tileSize: 256,
      minzoom: 0,
      maxzoom: NIGHT_TILES_MAX_ZOOM,
      attribution: NIGHT_ATTRIBUTION,
    },
  },
  layers: [
    { id: "land", type: "background", paint: { "background-color": LAND } },
    {
      // The lights lie over the land colour and under the water, so the coast stays crisp. Where
      // there is no light the tile is the land colour itself, so only the lights show.
      id: "night-lights",
      type: "raster",
      source: "night",
      paint: {
        "raster-resampling": "linear",
        "raster-fade-duration": 300,
        "raster-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          NIGHT_FADE_FROM_ZOOM,
          1,
          NIGHT_FADE_TO_ZOOM,
          0,
        ],
      },
    },
    {
      id: "water",
      type: "fill",
      source: "openmaptiles",
      "source-layer": "water",
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      paint: { "fill-color": OCEAN, "fill-antialias": true },
    },
    {
      id: "boundary-country",
      type: "line",
      source: "openmaptiles",
      "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": BORDER,
        "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.6, 5, 1, 10, 1.8],
      },
    },
    {
      id: "label-country-major",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      maxzoom: 8,
      filter: ["all", ["==", ["get", "class"], "country"], ["<=", ["get", "rank"], 2]],
      layout: {
        "text-field": placeName,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 1, 10, 5, 15],
        "text-max-width": 7,
      },
      paint: {
        "text-color": LABEL,
        "text-halo-color": OCEAN,
        "text-halo-width": 1,
        // From orbit the names step back, so the glow is the first thing seen.
        "text-opacity": ["interpolate", ["linear"], ["zoom"], 1.2, 0.55, 3, 1],
      },
    },
    {
      id: "label-country-minor",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      minzoom: 3,
      maxzoom: 9,
      filter: ["all", ["==", ["get", "class"], "country"], [">=", ["get", "rank"], 3], ["<=", ["get", "rank"], 4]],
      layout: {
        "text-field": placeName,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 3, 10, 7, 14],
        "text-max-width": 7,
      },
      paint: { "text-color": LABEL, "text-halo-color": OCEAN, "text-halo-width": 1 },
    },
    {
      // The smallest states wait until there is room for them.
      id: "label-country-small",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      minzoom: 5,
      maxzoom: 9,
      filter: ["all", ["==", ["get", "class"], "country"], [">=", ["get", "rank"], 5]],
      layout: {
        "text-field": placeName,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10, 8, 13],
        "text-max-width": 7,
      },
      paint: { "text-color": LABEL_MINOR, "text-halo-color": OCEAN, "text-halo-width": 1 },
    },
    {
      id: "label-city",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      minzoom: 4.5,
      filter: ["==", ["get", "class"], "city"],
      layout: {
        "text-field": placeName,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 4.5, 10, 10, 14],
        "text-max-width": 8,
      },
      paint: { "text-color": LABEL_MINOR, "text-halo-color": LAND, "text-halo-width": 1 },
    },
  ],
};
