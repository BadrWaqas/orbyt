import type { Map as MapLibreMap } from "maplibre-gl";

import { NO2_ATTRIBUTION, NO2_TILES_MAX_ZOOM, NO2_TILES_PATH, NO2_YEAR } from "./no2";

const SOURCE_ID = `no2-${NO2_YEAR}`;
export const NO2_LAYER_ID = `no2-${NO2_YEAR}`;

const FADE_IN_MS = 2400; // PLAN.md 9.7: the layer fades in from 0 to full
const TILE_WAIT_MS = 4000; // start the fade anyway if the first tiles are slow

interface Options {
  /** Draw underneath this layer, so borders and labels stay readable on top of the glow. */
  beforeId: string;
  reducedMotion: boolean;
  /** Called once, when the layer starts to show. */
  onVisible?: () => void;
}

/**
 * Add the pre-coloured NO2 raster tiles (PLAN.md 9.6, PlumeLayer for M1). The layer starts
 * clear and fades in once its first tiles have arrived, so it never pops in tile by tile.
 */
export function addNo2Layer(map: MapLibreMap, { beforeId, reducedMotion, onVisible }: Options) {
  map.addSource(SOURCE_ID, {
    type: "raster",
    tiles: [`${window.location.origin}${NO2_TILES_PATH}`],
    tileSize: 256,
    minzoom: 0,
    maxzoom: NO2_TILES_MAX_ZOOM, // deeper zooms stretch these tiles, which reads as a soft glow
    attribution: NO2_ATTRIBUTION,
  });
  map.addLayer(
    {
      id: NO2_LAYER_ID,
      type: "raster",
      source: SOURCE_ID,
      paint: {
        "raster-opacity": 0,
        "raster-opacity-transition": { duration: reducedMotion ? 0 : FADE_IN_MS, delay: 0 },
        "raster-resampling": "linear",
        "raster-fade-duration": reducedMotion ? 0 : 300,
      },
    },
    beforeId,
  );

  let shown = false;
  const show = () => {
    if (shown) return;
    shown = true;
    window.clearTimeout(timer);
    map.off("sourcedata", onSourceData);
    if (!map.getLayer(NO2_LAYER_ID)) return; // the map was removed in the meantime
    map.setPaintProperty(NO2_LAYER_ID, "raster-opacity", 1);
    onVisible?.();
  };
  const onSourceData = (e: { sourceId?: string }) => {
    if (e.sourceId === SOURCE_ID && map.isSourceLoaded(SOURCE_ID)) show();
  };
  const timer = window.setTimeout(show, TILE_WAIT_MS);
  map.on("sourcedata", onSourceData);

  return () => {
    window.clearTimeout(timer);
    map.off("sourcedata", onSourceData);
  };
}
