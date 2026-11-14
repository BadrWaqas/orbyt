import { COORDINATE_SYSTEM } from "@deck.gl/core";
import type { Layer } from "@deck.gl/core";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Map as MapLibreMap } from "maplibre-gl";

import {
  NO2_BLOOM_OPACITY,
  NO2_GLOW_GAMMA,
  NO2_HALO_OPACITY,
  NO2_TILES_MAX_ZOOM,
  NO2_TILES_PATH,
} from "./no2";

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

// The halo and bloom are built in the browser from the zoom 2 tiles: 16 small images, stitched,
// turned into light and blurred. The numbers are pixels of that stitched image.
const HALO_TILE_ZOOM = 2;
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

const HALO_FADE_MS = 900;
const FIRST_TILES_WAIT_MS = 4000;

// A wide, dark gradient drawn in 8 bits shows as stripes. A little screen-space noise, half a
// colour step either way, breaks the stripes up without being visible itself.
// (Interleaved gradient noise, Jimenez 2014.)
const DITHER = `
  float glowNoise = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5;
`;

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

/** The halo and bloom images: already light, so only the dither is added. */
class SoftBitmapLayer extends BitmapLayer {
  static layerName = "SoftBitmapLayer";

  getShaders() {
    const shaders = super.getShaders();
    return {
      ...shaders,
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

function tileUrl(z: number, x: number, y: number): string {
  const path = NO2_TILES_PATH.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  return `${window.location.origin}${path}`;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = "async";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Could not load ${url}`));
    image.src = url;
  });
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

/** Stitch the coarse tiles, turn colour and opacity into light, and blur it twice. */
async function buildSoftLight(): Promise<SoftLight> {
  const across = 2 ** HALO_TILE_ZOOM;
  const cell = HALO_SIZE_PX / across;
  const jobs: Promise<{ image: HTMLImageElement; x: number; y: number }>[] = [];
  for (let x = 0; x < across; x++) {
    for (let y = 0; y < across; y++) {
      jobs.push(loadImage(tileUrl(HALO_TILE_ZOOM, x, y)).then((image) => ({ image, x, y })));
    }
  }
  const tiles = await Promise.all(jobs);

  const canvas = document.createElement("canvas");
  canvas.width = HALO_SIZE_PX;
  canvas.height = HALO_SIZE_PX;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("No 2D canvas");
  ctx.imageSmoothingQuality = "high";
  for (const { image, x, y } of tiles) ctx.drawImage(image, x * cell, y * cell, cell, cell);
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
  remove(): void;
}

/** Add the glow to a loaded map. Returns null where the map has no WebGL2 context. */
export function addNo2Glow(map: MapLibreMap, { beforeId, onFail }: Options): No2Glow | null {
  // deck.gl 9 draws into the map's own context and needs WebGL2 for that.
  if (!map.getCanvas().getContext("webgl2")) return null;

  let level = 0;
  let haloLevel = 0;
  let soft: SoftLight | null = null;
  let removed = false;
  let stopFade = () => {};
  let stopHaloFade = () => {};
  let markReady = () => {};
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  const readyTimer = window.setTimeout(markReady, FIRST_TILES_WAIT_MS);

  // `beforeId` places a deck.gl layer in the map's layer stack. It is not part of the layer
  // prop types, so it is passed alongside them.
  const place = { beforeId } as object;

  const layers = (): Layer[] => {
    const list: Layer[] = [];
    if (soft && haloLevel > 0) {
      list.push(
        new SoftBitmapLayer({
          ...place,
          id: "no2-glow-bloom",
          image: soft.bloom,
          bounds: WORLD_BOUNDS,
          _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          opacity: NO2_BLOOM_OPACITY * level * haloLevel * bloomShare(map.getZoom()),
          textureParameters: SMOOTH,
          parameters: ADDITIVE,
        }),
        new SoftBitmapLayer({
          ...place,
          id: "no2-glow-halo",
          image: soft.halo,
          bounds: WORLD_BOUNDS,
          _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          opacity: NO2_HALO_OPACITY * level * haloLevel,
          textureParameters: SMOOTH,
          parameters: ADDITIVE,
        }),
      );
    }
    list.push(
      new TileLayer<ImageBitmap>({
        ...place,
        id: "no2-glow-sharp",
        data: `${window.location.origin}${NO2_TILES_PATH}`,
        minZoom: 0,
        maxZoom: NO2_TILES_MAX_ZOOM, // deeper zooms stretch these tiles, which reads as soft light
        tileSize: 256,
        // Light adds up, so a parent tile must never be drawn under its children.
        refinementStrategy: "no-overlap",
        opacity: level,
        parameters: ADDITIVE,
        onViewportLoad: markReady,
        renderSubLayers: (props) => {
          const [[west, south], [east, north]] = props.tile.boundingBox;
          // The tile's image arrives as `data`. A bitmap layer takes it as `image`.
          const { data: image, ...rest } = props;
          return new GlowBitmapLayer(rest as object, {
            image,
            bounds: [west, south, east, north],
            _imageCoordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
            textureParameters: SMOOTH,
            parameters: ADDITIVE,
          });
        },
      }),
    );
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
  map.on("zoom", draw); // the bloom follows the zoom

  // The halo is built once the sharp tiles are in, so it never competes with them for the network.
  void ready
    .then(buildSoftLight)
    .then((built) => {
      if (removed) return;
      soft = built;
      stopHaloFade = animate(level > 0 ? HALO_FADE_MS : 0, (t) => {
        haloLevel = t;
        draw();
      });
    })
    .catch(() => {
      // No halo. The sharp layer still glows.
    });

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
    remove() {
      if (removed) return;
      removed = true;
      window.clearTimeout(readyTimer);
      stopFade();
      stopHaloFade();
      map.off("zoom", draw);
      map.removeControl(overlay);
    },
  };
}
