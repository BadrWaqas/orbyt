// Renders the 1200 x 630 share card of every finding (PLAN.md 9.6, M6.5), plus the card for the
// home link. Linked from LinkedIn and the like through the share pages that make-share-pages.mjs
// writes.
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

const WIDTH = 1200;
const HEIGHT = 630;
const JPEG_QUALITY = 78; // the cards are committed, so keep them small: about 55 KB each
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
  const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("pageerror", (error) => problems.push(String(error)));
  while (queue.length) {
    const id = queue.shift();
    try {
      await page.goto(`${base}card/${id}`, { waitUntil: "load" });
      await page.waitForFunction(() => document.documentElement.dataset.cardReady === "true", null, {
        timeout: READY_TIMEOUT_MS,
      });
      const bytes = await page.screenshot({
        type: "jpeg",
        quality: JPEG_QUALITY,
        clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
      });
      await writeFile(path.join(OUT_DIR, `${id}.jpg`), bytes);
    } catch (error) {
      problems.push(`${id}: ${error.message.split("\n")[0]}`);
    }
    done += 1;
    if (done % 25 === 0 || done === ids.length) console.log(`${done} of ${ids.length}`);
  }
  await context.close();
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
