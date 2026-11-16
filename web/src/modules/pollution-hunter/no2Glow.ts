import { COORDINATE_SYSTEM } from "@deck.gl/core";
import type { Layer } from "@deck.gl/core";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Map as MapLibreMap } from "maplibre-gl";

import { NO2_BLOOM_OPACITY, NO2_GLOW_GAMMA, NO2_HALO_OPACITY } from "./no2";
import { loadTile } from "./no2Tiles";
import type { TileSet } from "./no2Tiles";
import { plumeClock } from "./plumeClock";
import { loadSitePlume, sitePlumeBounds } from "./sitePlume";
import type { SitePlumeSpec } from "./sitePlume";

// PlumeLayer for M7 (PLAN.md 9.6): deck.gl with additive blending, plus a blurred copy
// underneath at 40% opacity as the halo.
//
// Why this fixes the muddy look. The tiles are pre-coloured with the 9.2 ramp, whose low end is
// a dark brown at 35% opacity. Painted over the night map the usual way, that brown covers the
// map: mud. Added to it as light, the same brown is a faint ember and only the bright end of the
// ramp reads as glow. Three things are added on top of each other:
//
//   sharp   the tiles themselves, with their opacity raised to a power so the faint end fades
//   halo    the same light, blurred by about half a degree
//   bloom   the same light again, blurred by a few degrees, very faint
//
// This file is the only one that imports deck.gl. It is loaded as its own chunk (PLAN.md 9.10).

/** Light is added to what is already drawn. The alpha channel of the map is left alone. */
const ADDITIVE = {
  blend: true,
  blendColorOperation: "add",
  blendColorSrcFactor: "src-alpha",
  blendColorDstFactor: "one",
  blendAlphaOperation: "add",
  blendAlphaSrcFactor: "zero",
  blendAlphaDstFactor: "one",
  // The glow lies on the globe's surface, so there is nothing to sort by depth. Culling the
  // triangles that face away keeps the far side of the Earth from shining through.
  depthWriteEnabled: false,
  depthCompare: "always",
  cullMode: "back",
} as const;

const SMOOTH = {
  minFilter: "linear",
  magFilter: "linear",
  mipmapFilter: "linear",
  addressModeU: "clamp-to-edge",
  addressModeV: "clamp-to-edge",
} as const;

/** Web Mercator's whole world, the extent the stitched halo image covers. */
const WORLD_BOUNDS: [number, number, number, number] = [-180, -85.051129, 180, 85.051129];

// The halo and bloom are built in the browser from the zoom 1 tiles: four images, stitched,
// turned into light and blurred. The numbers are pixels of that stitched image.
const HALO_TILE_ZOOM = 1;
const HALO_SIZE_PX = 512; // 0.7 degrees per pixel
const HALO_BLUR_RADIUS_PX = 1; // three box passes, about 1 degree across at the equator
const BLOOM_SHRINK = 4; // the bloom image is this many times smaller
const BLOOM_BLUR_RADIUS_PX = 2;
// Blurring spreads a hotspot's light over many pixels, so its peak drops. The gain brings the
// halo back into the visible range before it is stored in 8 bits.
const HALO_GAIN = 1.6;
const BLOOM_GAIN = 2.2;

// The bloom is for the view from orbit. Close in it would only lift the black of the whole
// screen to brown, so it steps back as the camera comes down.
const BLOOM_FULL_ZOOM = 2.5;
const BLOOM_LOW_ZOOM = 6;
const BLOOM_LOW_SHARE = 0.25;

function bloomShare(zoom: number): number {
  const t = Math.min(1, Math.max(0, (zoom - BLOOM_FULL_ZOOM) / (BLOOM_LOW_ZOOM - BLOOM_FULL_ZOOM)));
  return 1 - (1 - BLOOM_LOW_SHARE) * t;
}

// The sharp layer holds what the satellite resolves: its deepest tiles are about 1 km a pixel
// over Europe, one pixel a screen pixel near zoom 6. Deeper than that the camera only enlarges
// them, so the layer steps back, and the soft halo is what stays. It never ends as squares.
const DEEP_FADE_FROM_ZOOM = 8;
const DEEP_FADE_TO_ZOOM = 10;
const DEEP_SHARE = 0.25;
// Around an open facility that has daily frames, its own plume is the picture (sitePlume.ts).
// There the mean steps back sooner, as the camera comes down to the facility.
const SITE_FADE_FROM_ZOOM = 6.25;
const SITE_FADE_TO_ZOOM = 7.5;
const SITE_SHARE = 0.3;
const SITE_DIM_MS = 500;

const smoothstep = (lo: number, hi: number, v: number) => {
  const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

/** Share of the sharp mean layer at a zoom. `siteDim` is 1 while a facility's plume is drawn. */
function meanShare(zoom: number, siteDim: number): number {
  const deep = 1 - (1 - DEEP_SHARE) * smoothstep(DEEP_FADE_FROM_ZOOM, DEEP_FADE_TO_ZOOM, zoom);
  const site = 1 - (1 - SITE_SHARE) * smoothstep(SITE_FADE_FROM_ZOOM, SITE_FADE_TO_ZOOM, zoom);
  return deep + (Math.min(deep, site) - deep) * siteDim;
}

const HALO_FADE_MS = 900;
const FIRST_TILES_WAIT_MS = 4000;

// The open facility's own plume, one clear day at a time (sitePlume.ts). Two layers take turns:
// each new day fades in on one while the day before fades out on the other.
const SITE_FADE_IN_MS = 700;
const SITE_CROSS_FADE_MS = 150;

// A wide, dark gradient drawn in 8 bits shows as stripes. A little screen-space noise, half a
// colour step either way, breaks the stripes up without being visible itself.
// (Interleaved gradient noise, Jimenez 2014.)
const DITHER = `
  float glowNoise = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5;
`;

// Close in, one pixel of an image covers many pixels of the screen, and the GPU's own linear
// filter shows the grid as creases and squares. The satellite's real pixel is about 5 km, so
// there is no detail to lose: where an image is enlarged, it is read through a cubic B-spline
// instead, which is smooth to the second derivative and reads as a soft glow. Four linear reads
// make one cubic read (GPU Gems 2, chapter 20). Where the image is shown at its own size or
// smaller, the plain read is kept, so the view from orbit stays as sharp as before.
const SMOOTH_SAMPLE = `
vec4 orbytCubicWeights(float v) {
  vec4 n = vec4(1.0, 2.0, 3.0, 4.0) - v;
  vec4 s = n * n * n;
  float x = s.x;
  float y = s.y - 4.0 * s.x;
  float z = s.z - 4.0 * s.y + 6.0 * s.x;
  return vec4(x, y, z, 6.0 - x - y - z) * (1.0 / 6.0);
}

vec4 orbytSmoothSample(sampler2D tex, vec2 uv) {
  vec2 size = vec2(textureSize(tex, 0));
  vec4 plain = texture(tex, uv);
  // Screen pixels per image pixel. Below 1.5 the image is not enlarged enough to show its grid.
  vec2 texels = uv * size;
  float enlarged = 1.0 / max(max(fwidth(texels.x), fwidth(texels.y)), 1e-6);
  float share = smoothstep(1.5, 3.0, enlarged);
  if (share <= 0.0) return plain;

  vec2 st = texels - 0.5;
  vec2 f = fract(st);
  st -= f;
  vec4 wx = orbytCubicWeights(f.x);
  vec4 wy = orbytCubicWeights(f.y);
  vec4 c = st.xxyy + vec2(-0.5, 1.5).xyxy;
  vec4 s = vec4(wx.xz + wx.yw, wy.xz + wy.yw);
  vec4 at = (c + vec4(wx.yw, wy.yw) / s) / size.xxyy;
  vec4 s0 = textureLod(tex, at.xz, 0.0);
  vec4 s1 = textureLod(tex, at.yz, 0.0);
  vec4 s2 = textureLod(tex, at.xw, 0.0);
  vec4 s3 = textureLod(tex, at.yw, 0.0);
  float sx = s.x / (s.x + s.y);
  float sy = s.z / (s.z + s.w);
  vec4 cubic = mix(mix(s3, s2, sx), mix(s1, s0, sx), sy);
  return mix(plain, cubic, share);
}
`;

const TEXTURE_READ = "texture(bitmapTexture, uv)";
const MAIN = "void main(void) {";

/** The bitmap layer's fragment shader with the cubic read in place of the plain one. */
function withSmoothSampling(fs: string): string {
  if (!fs.includes(TEXTURE_READ) || !fs.includes(MAIN)) return fs; // a deck.gl that changed: keep its own read
  return fs.replace(MAIN, `${SMOOTH_SAMPLE}\n${MAIN}`).replace(TEXTURE_READ, "orbytSmoothSample(bitmapTexture, uv)");
}

/**
 * A tile whose opacity is raised to a power before it is added. `layer.opacity` is divided out
 * first and put back after, so fading the layer in stays linear.
 */
class GlowBitmapLayer extends BitmapLayer {
  static layerName = "GlowBitmapLayer";

  getShaders() {
    const shaders = super.getShaders();
    return {
      ...shaders,
      fs: withSmoothSampling(shaders.fs),
      inject: {
        ...shaders.inject,
        "fs:DECKGL_FILTER_COLOR": `
          ${DITHER}
          float glowLayerOpacity = max(layer.opacity, 0.0001);
          float glowTileAlpha = clamp(color.a / glowLayerOpacity, 0.0, 1.0);
          float glowLight = pow(glowTileAlpha, ${NO2_GLOW_GAMMA.toFixed(3)});
          glowLight = max(0.0, glowLight + glowNoise * (1.5 / 255.0)) * step(0.5 / 255.0, glowTileAlpha);
          color.a = glowLight * glowLayerOpacity;
        `,
      },
    };
  }
}

/** The halo, bloom and site plume images: already light, so only the dither is added. */
class SoftBitmapLayer extends BitmapLayer {
  static layerName = "SoftBitmapLayer";

  getShaders() {
    const shaders = super.getShaders();
    return {
      ...shaders,
      fs: withSmoothSampling(shaders.fs),
      inject: {
        ...shaders.inject,
        "fs:DECKGL_FILTER_COLOR": `
          ${DITHER}
          color.rgb += glowNoise * (1.0 / 255.0) / max(color.a, 0.05);
        `,
      },
    };
  }
}

/** One pass of a box blur along x. The image wraps around the date line. */
function blurX(src: Float32Array, dst: Float32Array, w: number, h: number, r: number) {
  const n = 2 * r + 1;
  for (let y = 0; y < h; y++) {
    const row = y * w;
    let sum = 0;
    for (let i = -r; i <= r; i++) sum += src[row + ((i + w) % w)];
    for (let x = 0; x < w; x++) {
      dst[row + x] = sum / n;
      sum += src[row + ((x + r + 1) % w)] - src[row + ((x - r + w) % w)];
    }
  }
}

/** One pass of a box blur along y. The poles are held at their edge value. */
function blurY(src: Float32Array, dst: Float32Array, w: number, h: number, r: number) {
  const n = 2 * r + 1;
  for (let x = 0; x < w; x++) {
    let sum = 0;
    for (let i = -r; i <= r; i++) sum += src[Math.min(h - 1, Math.max(0, i)) * w + x];
    for (let y = 0; y < h; y++) {
      dst[y * w + x] = sum / n;
      sum += src[Math.min(h - 1, y + r + 1) * w + x] - src[Math.max(0, y - r) * w + x];
    }
  }
}

/** Three box passes each way, which is close to a Gaussian. Blurs `plane` in place. */
function blur(plane: Float32Array, w: number, h: number, r: number) {
  const scratch = new Float32Array(plane.length);
  for (let pass = 0; pass < 3; pass++) {
    blurX(plane, scratch, w, h, r);
    blurY(scratch, plane, w, h, r);
  }
}

/** Average `factor` by `factor` blocks. */
function shrink(plane: Float32Array, w: number, h: number, factor: number): Float32Array {
  const sw = w / factor;
  const sh = h / factor;
  const out = new Float32Array(sw * sh);
  for (let y = 0; y < sh; y++) {
    for (let x = 0; x < sw; x++) {
      let sum = 0;
      for (let dy = 0; dy < factor; dy++) {
        const row = (y * factor + dy) * w + x * factor;
        for (let dx = 0; dx < factor; dx++) sum += plane[row + dx];
      }
      out[y * sw + x] = sum / (factor * factor);
    }
  }
  return out;
}

/** Three planes of light, 0 to 1, as an opaque image. Added to the map, black adds nothing. */
function toImage(planes: Float32Array[], w: number, h: number, gain: number): ImageData {
  const image = new ImageData(w, h);
  const px = image.data;
  for (let i = 0; i < w * h; i++) {
    px[i * 4] = Math.min(255, planes[0][i] * gain * 255);
    px[i * 4 + 1] = Math.min(255, planes[1][i] * gain * 255);
    px[i * 4 + 2] = Math.min(255, planes[2][i] * gain * 255);
    px[i * 4 + 3] = 255;
  }
  return image;
}

interface SoftLight {
  halo: ImageData;
  bloom: ImageData;
}

/** Stitch a layer's coarse tiles, turn colour and opacity into light, and blur it twice. */
async function buildSoftLight(set: TileSet): Promise<SoftLight> {
  const across = 2 ** HALO_TILE_ZOOM;
  const cell = HALO_SIZE_PX / across;
  const jobs: Promise<{ image: ImageBitmap | null; x: number; y: number }>[] = [];
  for (let x = 0; x < across; x++) {
    for (let y = 0; y < across; y++) {
      jobs.push(loadTile(set, HALO_TILE_ZOOM, x, y).then((image) => ({ image, x, y })));
    }
  }
  const tiles = await Promise.all(jobs);
  if (tiles.every((tile) => !tile.image)) throw new Error(`No tiles for ${set.period}`);

  const canvas = document.createElement("canvas");
  canvas.width = HALO_SIZE_PX;
  canvas.height = HALO_SIZE_PX;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("No 2D canvas");
  ctx.imageSmoothingQuality = "high";
  for (const { image, x, y } of tiles) if (image) ctx.drawImage(image, x * cell, y * cell, cell, cell);
  const { data } = ctx.getImageData(0, 0, HALO_SIZE_PX, HALO_SIZE_PX);

  // The same curve the sharp layer applies in its shader.
  const light = new Float32Array(256);
  for (let a = 0; a < 256; a++) light[a] = (a / 255) ** NO2_GLOW_GAMMA / 255;

  const n = HALO_SIZE_PX * HALO_SIZE_PX;
  const planes = [new Float32Array(n), new Float32Array(n), new Float32Array(n)];
  for (let i = 0; i < n; i++) {
    const k = light[data[i * 4 + 3]];
    planes[0][i] = data[i * 4] * k;
    planes[1][i] = data[i * 4 + 1] * k;
    planes[2][i] = data[i * 4 + 2] * k;
  }

  const small = HALO_SIZE_PX / BLOOM_SHRINK;
  const bloomPlanes = planes.map((p) => shrink(p, HALO_SIZE_PX, HALO_SIZE_PX, BLOOM_SHRINK));
  for (const p of bloomPlanes) blur(p, small, small, BLOOM_BLUR_RADIUS_PX);
  for (const p of planes) blur(p, HALO_SIZE_PX, HALO_SIZE_PX, HALO_BLUR_RADIUS_PX);

  return {
    halo: toImage(planes, HALO_SIZE_PX, HALO_SIZE_PX, HALO_GAIN),
    bloom: toImage(bloomPlanes, small, small, BLOOM_GAIN),
  };
}

/** Run `step` with 0 to 1 over `ms`. Returns a function that stops it. */
function animate(ms: number, step: (t: number) => void): () => void {
  if (ms <= 0) {
    step(1);
    return () => {};
  }
  let frame = 0;
  const started = performance.now();
  const tick = (now: number) => {
    const t = Math.min(1, (now - started) / ms);
    step(t);
    if (t < 1) frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}


interface Options {
  /** The layer the glow starts with. */
  tiles: TileSet;
  /** Draw underneath this map layer, so borders and labels stay readable on top of the glow. */
  beforeId: string;
  /** deck.gl reported an error. The caller falls back to the plain raster layer. */
  onFail: () => void;
}

export interface No2Glow {
  /** Resolves once the first tiles are on screen, or after a few seconds if they are slow. */
  ready: Promise<void>;
  /** Fade the whole glow to `level`, 0 to 1. */
  fadeTo(level: number, ms: number): void;
  /**
   * Change to another layer: the annual mean or a month. Its tiles are loaded unseen for the
   * part of the globe on screen, then it cross-fades in over `ms`. Resolves true once it has
   * taken over, and false if a later call came first.
   */
  show(tiles: TileSet, ms: number): Promise<boolean>;
  /** Load another layer's tiles unseen, ahead of the change to it. Null drops them. */
  preload(tiles: TileSet | null): void;
  /**
   * Draw one facility's daily plume around it, following the plume clock. Null takes it off.
   * `onShown` reports when the plume is on the map and when it has gone.
   */
  setSitePlume(spec: SitePlumeSpec | null, onShown?: (shown: boolean) => void): void;
  remove(): void;
}

interface SitePlume {
  spec: SitePlumeSpec;
  bounds: [number, number, number, number];
  /** The two images that take turns, and which of them is fading in. */
  slots: [ImageData | null, ImageData | null];
  front: 0 | 1;
  /** Share of the front slot, 0 to 1. The back slot has the rest. */
  mix: number;
  level: number;
  shownIndex: number;
  stop: () => void;
}

/** A layer on the globe: its tiles, its halo once built, and which pair of halo layers it uses. */
interface Shown {
  set: TileSet;
  soft: SoftLight | null;
  slot: 0 | 1;
}

const SOFT_CACHE_SIZE = 8;
const INCOMING_WAIT_MS = 5000; // cross-fade to a new layer anyway if its tiles are this slow

/** Add the glow to a loaded map. Returns null where the map has no WebGL2 context. */
export function addNo2Glow(map: MapLibreMap, { tiles, beforeId, onFail }: Options): No2Glow | null {
  // deck.gl 9 draws into the map's own context and needs WebGL2 for that.
  if (!map.getCanvas().getContext("webgl2")) return null;

  let level = 0;
  let haloLevel = 0;
  let current: Shown = { set: tiles, soft: null, slot: 0 };
  let incoming: Shown | null = null; // the layer a cross-fade is bringing in
  let preloaded: TileSet | null = null;
  let mix = 0; // share of `incoming`, 0 to 1
  let showToken = 0;
  let site: SitePlume | null = null;
  let siteDim = 0; // 1 while a facility's own plume is drawn, see meanShare
  let removed = false;
  let stopFade = () => {};
  let stopHaloFade = () => {};
  let stopMix = () => {};
  let stopDim = () => {};
  let markReady = () => {};
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  const readyTimer = window.setTimeout(markReady, FIRST_TILES_WAIT_MS);

  // Which layers have their tiles for the part of the globe on screen.
  const loaded = new Set<string>();
  const waiting = new Map<string, (() => void)[]>();
  const markLoaded = (period: string) => {
    loaded.add(period);
    if (period === tiles.period) markReady();
    for (const resolve of waiting.get(period) ?? []) resolve();
    waiting.delete(period);
  };
  const whenLoaded = (period: string) =>
    new Promise<void>((resolve) => {
      if (loaded.has(period)) {
        resolve();
        return;
      }
      waiting.set(period, [...(waiting.get(period) ?? []), resolve]);
      window.setTimeout(resolve, INCOMING_WAIT_MS);
    });
  /** A layer that is no longer drawn loses its tiles, so it is no longer counted as loaded. */
  const prune = () => {
    const kept = new Set([current.set.period, incoming?.set.period, preloaded?.period]);
    for (const period of loaded) if (!kept.has(period)) loaded.delete(period);
  };

  // Halos already built, newest last.
  const softCache = new Map<string, Promise<SoftLight | null>>();
  const softFor = (set: TileSet): Promise<SoftLight | null> => {
    let request = softCache.get(set.period);
    if (request) softCache.delete(set.period);
    else {
      request = buildSoftLight(set).catch(() => null); // no halo, the sharp layer still glows
      if (softCache.size >= SOFT_CACHE_SIZE) softCache.delete(softCache.keys().next().value as string);
    }
    softCache.set(set.period, request);
    return request;
  };

  // `beforeId` places a deck.gl layer in the map's layer stack. It is not part of the layer
  // prop types, so it is passed alongside them.
  const place = { beforeId } as object;

  const sharp = (set: TileSet, opacity: number) =>
    new TileLayer<ImageBitmap | null>({
      ...place,
      id: `no2-glow-sharp-${set.period}`,
      getTileData: (tile) => loadTile(set, tile.index.z, tile.index.x, tile.index.y, tile.signal),
      minZoom: 0,
      maxZoom: set.maxZoom, // deeper zooms stretch these tiles, which reads as soft light
      tileSize: set.tileSize,
      // Light adds up, so a parent tile must never be drawn under its children.
      refinementStrategy: "no-overlap",
      opacity,
      parameters: ADDITIVE,
      onViewportLoad: () => markLoaded(set.period),
      renderSubLayers: (props) => {
        // The tile's image arrives as `data`. A bitmap layer takes it as `image`.
        const { data: image, ...rest } = props;
        if (!image) return null;
        const [[west, south], [east, north]] = props.tile.boundingBox;
        return new GlowBitmapLayer(rest as object, {
          image,
          bounds: [west, south, east, north],
          _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          textureParameters: SMOOTH,
          parameters: ADDITIVE,
        });
      },
    });

  const soft = (item: Shown, share: number, zoom: number): Layer[] => {
    if (!item.soft || share <= 0) return [];
    return [
      new SoftBitmapLayer({
        ...place,
        id: `no2-glow-bloom-${item.slot}`,
        image: item.soft.bloom,
        bounds: WORLD_BOUNDS,
        _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        opacity: NO2_BLOOM_OPACITY * level * haloLevel * share * bloomShare(zoom),
        textureParameters: SMOOTH,
        parameters: ADDITIVE,
      }),
      new SoftBitmapLayer({
        ...place,
        id: `no2-glow-halo-${item.slot}`,
        image: item.soft.halo,
        bounds: WORLD_BOUNDS,
        _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
        opacity: NO2_HALO_OPACITY * level * haloLevel * share,
        textureParameters: SMOOTH,
        parameters: ADDITIVE,
      }),
    ];
  };

  const layers = (): Layer[] => {
    const zoom = map.getZoom();
    const mean = level * meanShare(zoom, siteDim);
    // During a cross-fade the two layers share the light, so the sum stays level.
    const parts: [Shown, number][] = incoming ? [[current, 1 - mix], [incoming, mix]] : [[current, 1]];
    const list: Layer[] = [];
    if (haloLevel > 0) for (const [item, share] of parts) list.push(...soft(item, share, zoom));
    for (const [item, share] of parts) list.push(sharp(item.set, mean * share));
    if (preloaded && parts.every(([item]) => item.set.period !== preloaded?.period)) {
      list.push(sharp(preloaded, 0));
    }
    if (site) {
      for (const slot of [0, 1] as const) {
        const image = site.slots[slot];
        const share = slot === site.front ? site.mix : 1 - site.mix;
        if (!image || share <= 0) continue;
        list.push(
          new SoftBitmapLayer({
            ...place,
            id: `no2-site-plume-${slot}`,
            image,
            bounds: site.bounds,
            opacity: level * site.level * share,
            textureParameters: SMOOTH,
            parameters: ADDITIVE,
          }),
        );
      }
    }
    return list;
  };

  const overlay = new MapboxOverlay({
    interleaved: true,
    layers: layers(),
    onError: (error) => {
      console.warn("NO2 glow layer failed, falling back to the raster layer.", error);
      if (!removed) onFail();
    },
  });
  map.addControl(overlay);
  const draw = () => {
    if (!removed) overlay.setProps({ layers: layers() });
  };
  map.on("zoom", draw); // the bloom and the sharp layer follow the zoom

  // The halo is built once the sharp tiles are in, so it never competes with them for the network.
  void ready.then(async () => {
    const first = current;
    const built = await softFor(first.set);
    if (removed || !built) return;
    first.soft = built;
    stopHaloFade = animate(level > 0 ? HALO_FADE_MS : 0, (t) => {
      haloLevel = t;
      draw();
    });
  });

  const dimFor = (target: number) => {
    stopDim();
    const from = siteDim;
    stopDim = animate(SITE_DIM_MS, (t) => {
      siteDim = from + (target - from) * t;
      draw();
    });
  };

  return {
    ready,
    fadeTo(target, ms) {
      stopFade();
      const from = level;
      stopFade = animate(ms, (t) => {
        level = from + (target - from) * t;
        draw();
      });
    },
    async show(set, ms) {
      const token = ++showToken;
      stopMix(); // ends a cross-fade that is under way, and its call resolves false
      // Of the two layers of that cross-fade, the one with more of the light stays.
      if (incoming && mix >= 0.5) current = incoming;
      incoming = null;
      mix = 0;
      if (set.period === current.set.period) {
        prune();
        draw();
        return true;
      }
      const item: Shown = { set, soft: null, slot: current.slot === 0 ? 1 : 0 };
      incoming = item;
      prune();
      draw();
      const [built] = await Promise.all([softFor(set), whenLoaded(set.period)]);
      if (removed || token !== showToken) return false;
      item.soft = built;
      const finished = await new Promise<boolean>((resolve) => {
        stopMix = () => resolve(false);
        const stop = animate(ms, (t) => {
          mix = t;
          draw();
          if (t >= 1) resolve(true);
        });
        stopMix = () => {
          stop();
          resolve(false);
        };
      });
      if (!finished || removed || token !== showToken) return false;
      stopMix = () => {};
      current = item;
      incoming = null;
      mix = 0;
      prune();
      draw();
      return true;
    },
    preload(set) {
      preloaded = set;
      prune();
      draw();
    },
    setSitePlume(spec, onShown) {
      if (spec?.id === site?.spec.id) return;
      site?.stop();
      site = null;
      draw();
      if (!spec || removed) return;

      const mine: SitePlume = {
        spec,
        bounds: sitePlumeBounds(spec),
        slots: [null, null],
        front: 0,
        mix: 1,
        level: 0,
        shownIndex: -1,
        stop: () => {},
      };
      site = mine;
      let stopped = false;
      let stopCross = () => {};
      let stopLevel = () => {};
      let detach = () => {};
      let unsubscribe = () => {};
      mine.stop = () => {
        stopped = true;
        stopCross();
        stopLevel();
        detach();
        unsubscribe();
        dimFor(0);
        onShown?.(false);
      };

      void loadSitePlume(spec)
        .then((images) => {
          if (stopped) return;
          const show = (crossFadeMs: number) => {
            const index = Math.min(plumeClock.get().index, spec.positions.length - 1);
            if (index === mine.shownIndex) return;
            mine.shownIndex = index;
            stopCross();
            // Whatever was fading in becomes the day before, and the new day takes the other slot.
            mine.front = mine.front === 0 ? 1 : 0;
            mine.slots[mine.front] = images.frame(spec.positions[index]);
            stopCross = animate(crossFadeMs, (t) => {
              mine.mix = t;
              draw();
            });
          };
          show(0);
          unsubscribe = plumeClock.subscribe(() => show(SITE_CROSS_FADE_MS));
          detach = plumeClock.attach(spec.positions.length);
          stopLevel = animate(SITE_FADE_IN_MS, (t) => {
            mine.level = t;
            draw();
          });
          dimFor(1);
          onShown?.(true);
        })
        .catch(() => {
          // The sheet did not load. The panel's flipbook reports that, the globe just goes without.
        });
    },
    remove() {
      if (removed) return;
      site?.stop();
      site = null;
      removed = true;
      window.clearTimeout(readyTimer);
      stopFade();
      stopHaloFade();
      stopMix();
      stopDim();
      map.off("zoom", draw);
      map.removeControl(overlay);
    },
  };
}
