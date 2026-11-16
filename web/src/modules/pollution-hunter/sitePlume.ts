import type { FlipbookSheet } from "../../data/types";

// The daily plume of one facility, turned into light for the globe.
//
// The pipeline's flipbook sheet holds one frame per clear day: a north-up square around the
// source, coloured with the plume ramp over the night ocean colour, with cloud gaps in a grey
// blue (PLAN.md 9.6, Flipbook). On the globe a frame is added to the map as light, so here the
// ocean colour is taken back out, the cloud gaps are dropped, the faintest speckle is dimmed and
// the square's edge is faded, leaving only the plume.

export interface SitePlumeSpec {
  /** The finding the frames belong to. */
  id: string;
  lat: number;
  lon: number;
  /** URL of the flipbook sheet. */
  src: string;
  sheet: FlipbookSheet;
  /** Sheet position of each frame, in playing order. */
  positions: number[];
}

export interface SitePlumeImages {
  /** The frame at a sheet position, as an opaque image of light. */
  frame(position: number): ImageData;
}

const OCEAN = [0x04, 0x07, 0x0b]; // --earth-ocean, the colour the frames were laid over
// Ramp colours are always redder than they are blue. The ocean and the cloud gaps are not.
const WARM_MARGIN = 2;
const WARM_RAMP = 10;
// Dim the faintest pixels: in a single day they are mostly retrieval noise, and added up over
// the whole square they would show its outline.
const FAINT_RED = 22;
const FULL_RED = 96;
// The frame fades to nothing between these shares of its half-width, so no edge shows.
const FADE_FROM = 0.6;
const FADE_TO = 0.97;
// A blurred copy is added to each frame as its halo. The radius is a distance, so the halo is
// the same width whatever pixel size the pipeline draws the frames at.
const HALO_BLUR_RADIUS_KM = 3;
const HALO_SHARE = 0.7;
const CACHE_SIZE = 12;

const smoothstep = (lo: number, hi: number, v: number) => {
  const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

function boxBlur(src: Float32Array, dst: Float32Array, w: number, h: number, r: number, alongX: boolean) {
  const n = 2 * r + 1;
  const lines = alongX ? h : w;
  const length = alongX ? w : h;
  const step = alongX ? 1 : w;
  for (let line = 0; line < lines; line++) {
    const start = alongX ? line * w : line;
    let sum = 0;
    for (let i = -r; i <= r; i++) sum += src[start + Math.min(length - 1, Math.max(0, i)) * step];
    for (let i = 0; i < length; i++) {
      dst[start + i * step] = sum / n;
      sum += src[start + Math.min(length - 1, i + r + 1) * step] - src[start + Math.max(0, i - r) * step];
    }
  }
}

/** Load the sheet. Frames are cut out and converted one at a time, as they are asked for. */
export function loadSitePlume(spec: SitePlumeSpec): Promise<SitePlumeImages> {
  const { frame_w: w, frame_h: h, columns, half_km } = spec.sheet;
  const haloRadiusPx = Math.max(1, Math.round((HALO_BLUR_RADIUS_KM * w) / (2 * half_km)));
  return new Promise((resolve, reject) => {
    const sheet = new Image();
    sheet.decoding = "async";
    sheet.onerror = () => reject(new Error(`Could not load ${spec.src}`));
    sheet.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) {
        reject(new Error("No 2D canvas"));
        return;
      }

      // How much of each pixel survives the fade towards the square's edge.
      const edge = new Float32Array(w * h);
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const dx = (x + 0.5) / w - 0.5;
          const dy = (y + 0.5) / h - 0.5;
          edge[y * w + x] = 1 - smoothstep(FADE_FROM, FADE_TO, Math.hypot(dx, dy) * 2);
        }
      }

      const cache = new Map<number, ImageData>();
      const planes = [0, 1, 2].map(() => new Float32Array(w * h));
      const soft = new Float32Array(w * h);
      const scratch = new Float32Array(w * h);

      const convert = (position: number): ImageData => {
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(sheet, (position % columns) * w, Math.floor(position / columns) * h, w, h, 0, 0, w, h);
        const image = ctx.getImageData(0, 0, w, h);
        const px = image.data;
        for (let i = 0; i < w * h; i++) {
          const r = px[i * 4];
          const b = px[i * 4 + 2];
          // Soft, not a cut: where a cloud gap meets the plume the pixels are a blend of the two,
          // and a hard test would draw the gap's outline.
          const warm = smoothstep(WARM_MARGIN, WARM_MARGIN + WARM_RAMP, r - b);
          const keep = warm * smoothstep(FAINT_RED, FULL_RED, r) * edge[i];
          for (let c = 0; c < 3; c++) planes[c][i] = Math.max(0, px[i * 4 + c] - OCEAN[c]) * keep;
        }
        for (let c = 0; c < 3; c++) {
          soft.set(planes[c]);
          for (let pass = 0; pass < 3; pass++) {
            boxBlur(soft, scratch, w, h, haloRadiusPx, true);
            boxBlur(scratch, soft, w, h, haloRadiusPx, false);
          }
          for (let i = 0; i < w * h; i++) px[i * 4 + c] = Math.min(255, planes[c][i] + HALO_SHARE * soft[i]);
        }
        for (let i = 0; i < w * h; i++) px[i * 4 + 3] = 255;
        return image;
      };

      resolve({
        frame(position) {
          let image = cache.get(position);
          if (!image) {
            image = convert(position);
            if (cache.size >= CACHE_SIZE) cache.delete(cache.keys().next().value as number);
            cache.set(position, image);
          }
          return image;
        },
      });
    };
    sheet.src = spec.src;
  });
}

/** The square a frame covers, as [west, south, east, north] in degrees. */
export function sitePlumeBounds(spec: SitePlumeSpec): [number, number, number, number] {
  const dLat = spec.sheet.half_km / 110.574;
  const dLon = spec.sheet.half_km / (111.32 * Math.cos((spec.lat * Math.PI) / 180));
  return [spec.lon - dLon, spec.lat - dLat, spec.lon + dLon, spec.lat + dLat];
}
