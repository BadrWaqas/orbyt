import type { Map as MapLibreMap, RasterTileSource } from "maplibre-gl";

import { loadNo2Layers, NO2_HALO_OPACITY, NO2_YEAR } from "./no2";
import type { No2Layers } from "./no2";
import type { No2Glow } from "./no2Glow";
import { annualTileSet, monthTileSet } from "./no2Tiles";
import type { TileSet } from "./no2Tiles";
import type { SitePlumeSpec } from "./sitePlume";

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
// The list of layers and their tiles is asked for at the same moment, for the same reason.
const layersManifest = loadNo2Layers().catch(() => null);

const SOURCE_ID = `no2-${NO2_YEAR}`;
export const NO2_LAYER_ID = `no2-${NO2_YEAR}`;
const HALO_SOURCE_ID = `no2-${NO2_YEAR}-halo`;
const HALO_LAYER_ID = `no2-${NO2_YEAR}-halo`;

// Raster fallback: the halo reads the same tiles but only down to a coarse zoom, and stretching
// those gives the soft copy.
const RASTER_HALO_MAX_ZOOM = 1;
const RASTER_SATURATION = 0.25;

const FADE_IN_MS = 2400; // PLAN.md 9.7: the layer fades in from 0 to full
const TILE_WAIT_MS = 4000; // start the fade anyway if the first tiles are slow
const GLOW_WAIT_MS = 2500; // how long the first fade waits for deck.gl before using the raster
const SWAP_MS = 800; // cross-fade from the raster to the glow when deck.gl arrives late

interface Options {
  /** Draw underneath this layer, so borders and labels stay readable on top of the glow. */
  beforeId: string;
  reducedMotion: boolean;
  /** Whether the layer shows from the start. On the home screen it waits, loaded but dark. */
  shown: boolean;
  /** Called once, when the layer is ready and starts to show, or would if it were asked to. */
  onVisible?: () => void;
}

const wait = (ms: number) => new Promise<null>((resolve) => window.setTimeout(() => resolve(null), ms));

interface RasterLayers {
  /** Resolves when the first tiles have arrived, or after a few seconds if they are slow. */
  ready: Promise<void>;
  setOpacity(level: number, ms: number): void;
  /** Show another layer's tiles. The raster layers have no cross-fade: it is a cut. */
  setTiles(set: TileSet): void;
  remove(): void;
}

/** The pre-coloured NO2 tiles as MapLibre raster layers (PLAN.md 9.6, PlumeLayer for M1). */
function addRaster(map: MapLibreMap, set: TileSet, beforeId: string, reducedMotion: boolean): RasterLayers {
  const tiles = [set.template];
  map.addSource(SOURCE_ID, {
    type: "raster",
    tiles,
    tileSize: set.tileSize,
    minzoom: 0,
    // The tiles the whole world has. Deeper zooms stretch them, which reads as a soft glow.
    maxzoom: set.globalMaxZoom,
  });
  map.addSource(HALO_SOURCE_ID, {
    type: "raster",
    tiles,
    tileSize: set.tileSize,
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
    setTiles(next) {
      if (removed) return;
      for (const id of [SOURCE_ID, HALO_SOURCE_ID]) {
        (map.getSource(id) as RasterTileSource | undefined)?.setTiles([next.template]);
      }
    },
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

export interface No2Layer {
  /** Fade the whole layer in or out over `ms`. Asked before the tiles are in, it is remembered. */
  setShown(shown: boolean, ms: number): void;
  /**
   * Draw one facility's daily plume around it (sitePlume.ts). Null takes it off. Only the glow
   * can draw it: with the raster fallback `onShown` is never called with true.
   */
  setSitePlume(spec: SitePlumeSpec | null, onShown?: (shown: boolean) => void): void;
  /**
   * Change to a month, "2024-06", or back to the annual mean with null. The month's tiles are
   * loaded unseen first, then it cross-fades in over `ms`. Resolves true once it has taken
   * over, and false if a later call came first or the layer has no such month.
   */
  showPeriod(month: string | null, ms: number): Promise<boolean>;
  /** Load a month's tiles unseen, ahead of the change to it. Null drops them. */
  preload(month: string | null): void;
  remove(): void;
}

/**
 * Add the NO2 layer to a loaded map. It starts clear and fades in once its first tiles have
 * arrived, so it never pops in tile by tile.
 */
export function addNo2Layer(
  map: MapLibreMap,
  { beforeId, reducedMotion, shown, onVisible }: Options,
): No2Layer {
  const fadeMs = reducedMotion ? 0 : FADE_IN_MS;
  let cancelled = false;
  let glow: No2Glow | null = null;
  let raster: RasterLayers | null = null;
  // The level the layer should be at, 0 or 1. Whichever way it is drawn follows this.
  let want = shown ? 1 : 0;
  let glowLive = false; // the glow has its first tiles and is the layer on show
  let rasterLive = false; // the same for the raster fallback
  // The site plume asked for last, kept so it can be handed to the glow when that arrives.
  let sitePlume: { spec: SitePlumeSpec | null; onShown?: (shown: boolean) => void } = { spec: null };

  // The annual mean, the layer everything starts with. Set once the manifest has arrived.
  let annual: TileSet | null = null;
  let manifest: No2Layers | null = null;
  // The month asked for last, null for the annual mean. Kept so a layer that arrives later
  // starts on it.
  let month: string | null = null;
  const tilesFor = (period: string | null): TileSet | null =>
    period === null ? annual : manifest ? monthTileSet(manifest, period) : null;

  const showRaster = async () => {
    const first = tilesFor(month) ?? annual;
    if (!first) return;
    raster = addRaster(map, first, beforeId, reducedMotion);
    await raster.ready;
    if (cancelled) return;
    rasterLive = true;
    raster.setOpacity(want, fadeMs);
  };

  /** deck.gl failed after it was added: take it off and make sure the raster is there instead. */
  const onFail = () => {
    if (cancelled) return;
    glow?.remove();
    glow = null;
    glowLive = false;
    if (raster) {
      rasterLive = true;
      raster.setOpacity(want, 0);
    } else void showRaster();
  };

  const tryGlow = (mod: typeof import("./no2Glow")) => {
    const first = tilesFor(month) ?? annual;
    if (!first) return null;
    try {
      const added = mod.addNo2Glow(map, { tiles: first, beforeId, onFail });
      added?.setSitePlume(sitePlume.spec, sitePlume.onShown);
      return added;
    } catch {
      return null;
    }
  };

  const start = async () => {
    const [early, layers] = await Promise.all([Promise.race([glowModule, wait(GLOW_WAIT_MS)]), layersManifest]);
    if (cancelled) return;
    manifest = layers;
    annual = manifest ? annualTileSet(manifest) : null;
    if (!annual) return; // the manifest is missing or names no annual mean: there is nothing to draw
    if (early) glow = tryGlow(early);
    if (glow) {
      await glow.ready;
      if (cancelled) return;
      if (glow) {
        glowLive = true;
        glow.fadeTo(want, fadeMs);
      }
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
    glowLive = true;
    rasterLive = false;
    glow.fadeTo(want, swapMs);
    raster?.setOpacity(0, swapMs);
    await wait(swapMs + 100);
    if (cancelled || !glow) return; // the glow failed during the swap, the raster is back
    raster?.remove();
    raster = null;
  };
  void start();

  return {
    setShown(next, ms) {
      want = next ? 1 : 0;
      if (cancelled) return;
      if (glowLive) glow?.fadeTo(want, ms);
      if (rasterLive) raster?.setOpacity(want, ms);
    },
    setSitePlume(spec, onShown) {
      sitePlume = { spec, onShown };
      glow?.setSitePlume(spec, onShown);
    },
    showPeriod(next, ms) {
      month = next;
      const set = tilesFor(next);
      if (cancelled || !set) return Promise.resolve(false); // not there yet: it starts on `month`
      if (glow && !rasterLive) return glow.show(set, ms);
      if (rasterLive && raster) {
        raster.setTiles(set);
        return Promise.resolve(true);
      }
      return Promise.resolve(false);
    },
    preload(next) {
      if (cancelled) return;
      glow?.preload(next === null ? null : tilesFor(next));
    },
    remove() {
      cancelled = true;
      glow?.remove();
      raster?.remove();
    },
  };
}
