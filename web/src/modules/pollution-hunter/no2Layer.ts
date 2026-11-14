import type { Map as MapLibreMap } from "maplibre-gl";

import { NO2_HALO_OPACITY, NO2_TILES_MAX_ZOOM, NO2_TILES_PATH, NO2_YEAR } from "./no2";
import type { No2Glow } from "./no2Glow";

// The NO2 layer is drawn one of two ways.
//
//   glow    deck.gl, additive blending and a blurred halo (no2Glow.ts). The look the site wants.
//   raster  MapLibre raster tiles. Used while deck.gl is still downloading on a slow connection,
//           and for good where the browser has no WebGL2 or deck.gl fails.
//
// deck.gl is its own chunk (PLAN.md 2.7 and 9.10). Its download starts when this module loads,
// which is while the map is still fetching its style, so on most connections the glow is ready
// before the first fade and the raster layer is never added.
const glowModule = import("./no2Glow").catch(() => null);

const SOURCE_ID = `no2-${NO2_YEAR}`;
export const NO2_LAYER_ID = `no2-${NO2_YEAR}`;
const HALO_SOURCE_ID = `no2-${NO2_YEAR}-halo`;
const HALO_LAYER_ID = `no2-${NO2_YEAR}-halo`;

// Raster fallback: the halo reads the same tiles but only down to a coarse zoom, and stretching
// those gives the soft copy.
const RASTER_HALO_MAX_ZOOM = 2;
const RASTER_SATURATION = 0.25;

const FADE_IN_MS = 2400; // PLAN.md 9.7: the layer fades in from 0 to full
const TILE_WAIT_MS = 4000; // start the fade anyway if the first tiles are slow
const GLOW_WAIT_MS = 2500; // how long the first fade waits for deck.gl before using the raster
const SWAP_MS = 800; // cross-fade from the raster to the glow when deck.gl arrives late

interface Options {
  /** Draw underneath this layer, so borders and labels stay readable on top of the glow. */
  beforeId: string;
  reducedMotion: boolean;
  /** Called once, when the layer starts to show. */
  onVisible?: () => void;
}

const wait = (ms: number) => new Promise<null>((resolve) => window.setTimeout(() => resolve(null), ms));

interface RasterLayers {
  /** Resolves when the first tiles have arrived, or after a few seconds if they are slow. */
  ready: Promise<void>;
  setOpacity(level: number, ms: number): void;
  remove(): void;
}

/** The pre-coloured NO2 tiles as MapLibre raster layers (PLAN.md 9.6, PlumeLayer for M1). */
function addRaster(map: MapLibreMap, beforeId: string, reducedMotion: boolean): RasterLayers {
  const tiles = [`${window.location.origin}${NO2_TILES_PATH}`];
  map.addSource(SOURCE_ID, {
    type: "raster",
    tiles,
    tileSize: 256,
    minzoom: 0,
    maxzoom: NO2_TILES_MAX_ZOOM, // deeper zooms stretch these tiles, which reads as a soft glow
  });
  map.addSource(HALO_SOURCE_ID, {
    type: "raster",
    tiles,
    tileSize: 256,
    minzoom: 0,
    maxzoom: RASTER_HALO_MAX_ZOOM,
  });
  map.addLayer(
    {
      id: HALO_LAYER_ID,
      type: "raster",
      source: HALO_SOURCE_ID,
      paint: { "raster-opacity": 0, "raster-resampling": "linear", "raster-fade-duration": 0 },
    },
    beforeId,
  );
  map.addLayer(
    {
      id: NO2_LAYER_ID,
      type: "raster",
      source: SOURCE_ID,
      paint: {
        "raster-opacity": 0,
        "raster-resampling": "linear",
        "raster-fade-duration": reducedMotion ? 0 : 300,
        "raster-saturation": RASTER_SATURATION,
      },
    },
    beforeId,
  );

  let removed = false;
  let markReady = () => {};
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  const onSourceData = (e: { sourceId?: string }) => {
    if (e.sourceId === SOURCE_ID && map.isSourceLoaded(SOURCE_ID)) markReady();
  };
  const timer = window.setTimeout(markReady, TILE_WAIT_MS);
  map.on("sourcedata", onSourceData);
  void ready.then(() => {
    window.clearTimeout(timer);
    map.off("sourcedata", onSourceData);
  });

  return {
    ready,
    setOpacity(level, ms) {
      if (removed) return;
      const transition = { duration: ms, delay: 0 };
      map.setPaintProperty(NO2_LAYER_ID, "raster-opacity-transition", transition);
      map.setPaintProperty(HALO_LAYER_ID, "raster-opacity-transition", transition);
      map.setPaintProperty(NO2_LAYER_ID, "raster-opacity", level);
      map.setPaintProperty(HALO_LAYER_ID, "raster-opacity", NO2_HALO_OPACITY * level);
    },
    remove() {
      if (removed) return;
      removed = true;
      window.clearTimeout(timer);
      map.off("sourcedata", onSourceData);
      for (const id of [NO2_LAYER_ID, HALO_LAYER_ID]) if (map.getLayer(id)) map.removeLayer(id);
      for (const id of [SOURCE_ID, HALO_SOURCE_ID]) if (map.getSource(id)) map.removeSource(id);
    },
  };
}

/**
 * Add the NO2 layer to a loaded map. It starts clear and fades in once its first tiles have
 * arrived, so it never pops in tile by tile. Returns a function that takes it off again.
 */
export function addNo2Layer(map: MapLibreMap, { beforeId, reducedMotion, onVisible }: Options) {
  const fadeMs = reducedMotion ? 0 : FADE_IN_MS;
  let cancelled = false;
  let glow: No2Glow | null = null;
  let raster: RasterLayers | null = null;

  const showRaster = async () => {
    raster = addRaster(map, beforeId, reducedMotion);
    await raster.ready;
    if (cancelled) return;
    raster.setOpacity(1, fadeMs);
  };

  /** deck.gl failed after it was added: take it off and make sure the raster is there instead. */
  const onFail = () => {
    if (cancelled) return;
    glow?.remove();
    glow = null;
    if (raster) raster.setOpacity(1, 0);
    else void showRaster();
  };

  const tryGlow = (mod: typeof import("./no2Glow")) => {
    try {
      return mod.addNo2Glow(map, { beforeId, onFail });
    } catch {
      return null;
    }
  };

  const start = async () => {
    const early = await Promise.race([glowModule, wait(GLOW_WAIT_MS)]);
    if (cancelled) return;
    if (early) glow = tryGlow(early);
    if (glow) {
      await glow.ready;
      if (cancelled) return;
      glow?.fadeTo(1, fadeMs);
      onVisible?.();
      return;
    }

    await showRaster();
    if (cancelled) return;
    onVisible?.();
    if (early) return; // deck.gl was there and could not draw here: the raster stays

    // deck.gl arrived after the raster was shown: cross-fade to the glow and drop the raster.
    const late = await glowModule;
    if (cancelled || !late) return;
    glow = tryGlow(late);
    if (!glow) return;
    await glow.ready;
    if (cancelled || !glow) return;
    const swapMs = reducedMotion ? 0 : SWAP_MS;
    glow.fadeTo(1, swapMs);
    raster?.setOpacity(0, swapMs);
    await wait(swapMs + 100);
    if (cancelled || !glow) return; // the glow failed during the swap, the raster is back
    raster?.remove();
    raster = null;
  };
  void start();

  return () => {
    cancelled = true;
    glow?.remove();
    raster?.remove();
  };
}
