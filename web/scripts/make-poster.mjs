// Renders the poster of the Earth for the home screen (PLAN.md 2.7): the globe as the live map
// draws it in the home view, without place names, on a clear background. The page shows it at
// once and the live map cross-fades in over it when its tiles have arrived.
//
//   npm run poster
//
// It starts the dev server, opens the home screen in a browser that is already on the machine
// (Edge or Chrome, through playwright-core, so nothing is downloaded), and photographs the
// map's own canvas. Run it again whenever the base style or the home view changes.

import { writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";
import { createServer } from "vite";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(root, "public", "img", "earth-poster.webp");

// A wide window, where the globe is half the window's height (app/layout.ts, the orbit layout).
const VIEWPORT = { width: 2000, height: 1000 };
const PIXEL_RATIO = 2;
// The picture is a square this many times the globe's diameter, so the haze round the limb is
// in it. The CSS twins are ".earth-poster::after" in design/index.css and the shell in
// index.html: both draw the picture at this size around the globe.
const POSTER_SCALE = 1.12;
const POSTER_PX = 1120; // a globe of 1000 px, sharp on a phone and on a large desktop window
const WEBP_QUALITY = 0.86;

async function launch() {
  for (const channel of ["msedge", "chrome"]) {
    try {
      return await chromium.launch({ channel, headless: true, args: ["--enable-unsafe-swiftshader"] });
    } catch {
      // Not installed. Try the next one.
    }
  }
  throw new Error("No Edge or Chrome found for the poster.");
}

// The map's handle on window exists in a development build only (globe/Globe.tsx), so the dev
// server must not be started as production, whatever the shell says.
process.env.NODE_ENV = "development";
const server = await createServer({ root, logLevel: "error", server: { port: 5199, strictPort: false } });
await server.listen();
const url = server.resolvedUrls.local[0];
const browser = await launch();

try {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: PIXEL_RATIO,
    reducedMotion: "reduce", // the globe holds still at its starting place
  });
  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (error) => problems.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  await page.goto(url, { waitUntil: "load" });
  try {
    await page.waitForFunction(() => window.__orbytMap?.loaded() && window.__orbytMap.areTilesLoaded(), null, {
      timeout: 60_000,
    });
  } catch (error) {
    const state = await page.evaluate(() => ({
      map: Boolean(window.__orbytMap),
      loaded: window.__orbytMap?.loaded(),
      tiles: window.__orbytMap?.areTilesLoaded(),
    }));
    throw new Error(`The map did not finish loading: ${JSON.stringify(state)}\n${problems.join("\n")}`, {
      cause: error,
    });
  }

  const dataUrl = await page.evaluate(
    async ({ scale, size, quality }) => {
      const map = window.__orbytMap;
      for (const layer of map.getStyle().layers) {
        if (layer.type === "symbol") map.setLayoutProperty(layer.id, "visibility", "none");
      }
      await new Promise((resolve) => {
        map.once("idle", resolve);
        map.triggerRepaint();
      });

      const main = document.querySelector("main");
      const read = (name) => Number.parseFloat(getComputedStyle(main).getPropertyValue(name));
      const ratio = map.getCanvas().width / map.getCanvas().clientWidth;
      const side = read("--globe-d") * scale * ratio;
      const left = read("--globe-cx") * ratio - side / 2;
      const top = read("--globe-cy") * ratio - side / 2;

      const poster = document.createElement("canvas");
      poster.width = size;
      poster.height = size;
      const ctx = poster.getContext("2d");
      ctx.imageSmoothingQuality = "high";
      // The map's canvas keeps its picture only until the frame ends, so it is copied inside
      // the render event.
      await new Promise((resolve) => {
        map.once("render", () => {
          ctx.drawImage(map.getCanvas(), left, top, side, side, 0, 0, size, size);
          resolve();
        });
        map.triggerRepaint();
      });
      return poster.toDataURL("image/webp", quality);
    },
    { scale: POSTER_SCALE, size: POSTER_PX, quality: WEBP_QUALITY },
  );

  const bytes = Buffer.from(dataUrl.split(",")[1], "base64");
  await writeFile(OUT, bytes);
  console.log(`wrote ${path.relative(root, OUT)}, ${(bytes.length / 1024).toFixed(1)} KB`);
} finally {
  await browser.close();
  await server.close();
}
