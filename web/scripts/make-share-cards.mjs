// Renders the share card of every finding (PLAN.md 9.6, M6.5), plus the card for the home link.
// Linked from LinkedIn and the like through the share pages that make-share-pages.mjs writes.
//
//   npm run share:cards                 every finding and the home card
//   npm run share:cards -- <id> <id>    only these findings (use "home" for the home card)
//
// It starts the dev server and opens the hidden /card/<id> route in a browser that is already on
// the machine (Edge or Chrome, through playwright-core, so nothing is downloaded). The pictures
// land in public/img/share/ and are committed, because the hosting build cannot run a browser.
// Run it again whenever the data, the card design or a plume picture changes.

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";
import { createServer } from "vite";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FINDINGS = path.join(root, "public", "data", "v1", "pollution-hunter", "findings.json");
const OUT_DIR = path.join(root, "public", "img", "share");

// The card is laid out at 1200 x 630. The cards people share most, the home card and every
// finding with a plume picture, are photographed at twice that, 2400 x 1260, at a high JPEG
// quality, so they stay sharp when LinkedIn scales them for high-density screens and the glow
// does not band. The other few hundred are type and thin lines and stay at 1200 x 630, which
// keeps the committed folder near 20 MB instead of 45. make-share-pages.mjs reads each card's
// size from its file.
const WIDTH = 1200;
const HEIGHT = 630;
const SHARP = { scale: 2, quality: 85 };
const PLAIN = { scale: 1, quality: 78 };
const WORKERS = 4;
const READY_TIMEOUT_MS = 30_000;

async function launch() {
  for (const channel of ["msedge", "chrome"]) {
    try {
      return await chromium.launch({ channel, headless: true });
    } catch {
      // Not installed. Try the next one.
    }
  }
  throw new Error("No Edge or Chrome found for the share cards.");
}

const payload = JSON.parse(await readFile(FINDINGS, "utf8"));
const wanted = process.argv.slice(2);
const all = [...payload.findings.map((f) => f.id), "home"];
const ids = wanted.length ? wanted : all;
// Findings with a satellite estimate are the ones whose card shows the plume picture.
const sharp = new Set([...payload.findings.filter((f) => f.observed).map((f) => f.id), "home"]);
const unknown = ids.filter((id) => !all.includes(id));
if (unknown.length) throw new Error(`No such finding: ${unknown.join(", ")}`);

await mkdir(OUT_DIR, { recursive: true });
const server = await createServer({ root, logLevel: "error", server: { port: 5198, strictPort: false } });
await server.listen();
const base = server.resolvedUrls.local[0];
const browser = await launch();

const problems = [];
let done = 0;

async function worker(queue) {
  // One page per pixel scale: the scale belongs to the browser context.
  const pages = new Map();
  for (const kind of [SHARP, PLAIN]) {
    const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: kind.scale });
    const page = await context.newPage();
    page.on("pageerror", (error) => problems.push(String(error)));
    pages.set(kind, page);
  }
  while (queue.length) {
    const id = queue.shift();
    const kind = sharp.has(id) ? SHARP : PLAIN;
    const page = pages.get(kind);
    try {
      await page.goto(`${base}card/${id}`, { waitUntil: "load" });
      await page.waitForFunction(() => document.documentElement.dataset.cardReady === "true", null, {
        timeout: READY_TIMEOUT_MS,
      });
      const bytes = await page.screenshot({
        type: "jpeg",
        quality: kind.quality,
        clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
      });
      await writeFile(path.join(OUT_DIR, `${id}.jpg`), bytes);
    } catch (error) {
      problems.push(`${id}: ${error.message.split("\n")[0]}`);
    }
    done += 1;
    if (done % 25 === 0 || done === ids.length) console.log(`${done} of ${ids.length}`);
  }
  for (const page of pages.values()) await page.context().close();
}

try {
  const queue = [...ids];
  await Promise.all(Array.from({ length: Math.min(WORKERS, queue.length) }, () => worker(queue)));
} finally {
  await browser.close();
  await server.close();
}

if (problems.length) {
  console.error(`${problems.length} problem(s):\n${problems.slice(0, 20).join("\n")}`);
  process.exit(1);
}
console.log(`wrote ${ids.length} card(s) to ${path.relative(root, OUT_DIR)}`);
