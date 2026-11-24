// Measures the performance budgets of PLAN.md 9.10 against the production build in dist/.
//
//   npm run build && node scripts/perf.mjs --label before --out ../docs/perf/m7.5-before.json
//
// The phone is a stand-in: a 412 x 915 viewport at 2x, the CPU slowed 4x, and a 4G link
// (9 Mbit/s down, 100 ms round trip). It does not replace a run on a real mid-range Android
// phone, because the GPU here is the laptop's. The numbers are for comparing builds with each
// other on the same machine.
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { writeFile, mkdir } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";
import { chromium } from "playwright-core";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};
const dist = path.resolve(arg("dist", path.join(root, "dist")));
// Which parts to run (load, fps, hidden; default all) and CSS to add to every page, for trying
// an idea on a build without changing the code.
const only = arg("only", "load,fps,hidden").split(",");
const extraCss = arg("css", "");
const label = arg("label", "run");
const runs = Number(arg("runs", "3"));
const out = arg("out", null);
const gpu = process.argv.includes("--gpu");

const FACILITY_NEAR = "ph-eu-347c8cef"; // the Ruhr, from the share of Europe the camera opens on
const FACILITY_FAR = "ph-eu-12a5336d"; // Crete, a long flight from there
const NET = { latency: 100, downloadThroughput: (9 * 1024 * 1024) / 8, uploadThroughput: (4.5 * 1024 * 1024) / 8 };
const CPU_SLOWDOWN = 4;

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg",
  ".woff2": "font/woff2", ".pmtiles": "application/octet-stream",
};
const COMPRESSIBLE = new Set([".html", ".js", ".css", ".json", ".svg"]);
const cache = new Map();
function body(file, encoding) {
  const key = `${file}|${encoding}`;
  if (!cache.has(key)) {
    const raw = readFileSync(file);
    cache.set(
      key,
      encoding === "br"
        ? zlib.brotliCompressSync(raw, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } })
        : zlib.gzipSync(raw, { level: 6 }),
    );
  }
  return cache.get(key);
}

/** dist/ as a static site with brotli, like Cloudflare Pages, and the app's index for any other path. */
function serve() {
  const server = http.createServer((req, res) => {
    let file = path.join(dist, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(dist)) return res.writeHead(403).end();
    if (!existsSync(file) || statSync(file).isDirectory()) file = path.join(dist, "index.html");
    const ext = path.extname(file);
    const headers = { "content-type": MIME[ext] ?? "application/octet-stream", "cache-control": "no-store" };
    const accepts = String(req.headers["accept-encoding"] ?? "");
    if (COMPRESSIBLE.has(ext) && /\bbr\b/.test(accepts)) {
      const data = body(file, "br");
      res.writeHead(200, { ...headers, "content-encoding": "br", "content-length": data.length });
      return res.end(data);
    }
    res.writeHead(200, { ...headers, "content-length": statSync(file).size });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** The scripts the page needs before anything else: the ones index.html names. */
function entryScripts() {
  const html = readFileSync(path.join(dist, "index.html"), "utf8");
  return [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.js)"/g)].map((m) => m[1]);
}

const median = (xs) => {
  const s = xs.filter((x) => x !== null && Number.isFinite(x)).sort((a, b) => a - b);
  return s.length ? s[Math.floor((s.length - 1) / 2)] : null;
};
const round = (x, d = 0) => (x === null ? null : Math.round(x * 10 ** d) / 10 ** d);

// Runs in the page before any of the app's own code.
function instrument() {
  const perf = { ready: null, lcp: null, raf: 0, rafDeck: 0, timers: 0, stacks: false };
  window.__perf = perf;
  new PerformanceObserver((list) => {
    const last = list.getEntries().at(-1);
    if (last) perf.lcp = last.startTime;
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new MutationObserver(() => {
    if (perf.ready === null && document.querySelector('main[data-globe="ready"]')) perf.ready = performance.now();
  }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-globe"] });

  // Count what the app asks the browser to run, so a "hidden" tab can be checked for silence.
  const raf = window.requestAnimationFrame.bind(window);
  // deck.gl's own loop asks for a frame at the display rate for as long as the page is open, and
  // the browser stops it in a hidden tab. It is counted apart so what the app itself asks for shows.
  // The app's own fades live in that chunk too, and they only run while something is changing.
  window.requestAnimationFrame = (fn) => {
    // A production build mangles class names, so deck.gl is told by the chunk it lives in.
    const deck = perf.stacks && /assets\/no2Glow-/.test(new Error().stack);
    return raf((t) => {
      perf.raf++;
      if (deck) perf.rafDeck++;
      fn(t);
    });
  };
  for (const name of ["setTimeout", "setInterval"]) {
    const original = window[name].bind(window);
    window[name] = (fn, ms, ...rest) =>
      typeof fn === "function"
        ? original(
            (...a) => {
              perf.timers++;
              return fn(...a);
            },
            ms,
            ...rest,
          )
        : original(fn, ms, ...rest);
  }
  // Headless tabs are never hidden, so the visibility the app reads can be switched by hand.
  let hidden = false;
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (hidden ? "hidden" : "visible") });
  window.__setHidden = (value) => {
    hidden = value;
    document.dispatchEvent(new Event("visibilitychange"));
  };
  try {
    sessionStorage.setItem("orbyt:intro-seen", "1");
  } catch {
    // a blank document has no storage
  }
}

/** Frame times from requestAnimationFrame over `ms`, as the page itself sees them. */
async function sampleFrames(page, ms) {
  const times = await page.evaluate(
    (duration) =>
      new Promise((resolve) => {
        const stamps = [];
        const start = performance.now();
        const tick = (t) => {
          stamps.push(t);
          if (t - start < duration) requestAnimationFrame(tick);
          else resolve(stamps);
        };
        requestAnimationFrame(tick);
      }),
    ms,
  );
  const deltas = times.slice(1).map((t, i) => t - times[i]);
  const span = times.at(-1) - times[0];
  const sorted = [...deltas].sort((a, b) => a - b);
  const at = (p) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
  // The worst second: the fewest frames in any one-second window.
  let worst = Infinity;
  for (let i = 0, j = 0; i < times.length; i++) {
    while (times[i] - times[j] > 1000) j++;
    if (times[i] - times[0] >= 1000) worst = Math.min(worst, i - j);
  }
  return {
    fps: round((deltas.length / span) * 1000, 1),
    worstSecondFps: Number.isFinite(worst) ? worst : null,
    p50ms: round(at(0.5), 1),
    p95ms: round(at(0.95), 1),
    // Frames slower than 25 ms, under 40 fps, which is what reads as stutter.
    over25msPct: round((deltas.filter((d) => d > 25).length / deltas.length) * 100, 1),
  };
}

async function newPage(browser, base, { throttle }) {
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  if (extraCss) {
    await page.addInitScript((css) => {
      document.addEventListener("DOMContentLoaded", () => {
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);
      });
    }, extraCss);
  }
  const cdp = await context.newCDPSession(page);
  if (throttle) {
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, ...NET });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: CPU_SLOWDOWN });
  }
  return { context, page, cdp };
}

/** Cold load of the home screen on the throttled phone: paints, bytes and the live globe. */
async function loadRun(browser, base) {
  const { context, page } = await newPage(browser, base, { throttle: true });
  await page.addInitScript(instrument);
  const entry = new Set(entryScripts());
  const responses = [];
  page.on("requestfinished", async (request) => {
    const sizes = await request.sizes().catch(() => null);
    const response = await request.response().catch(() => null);
    if (!sizes || !response) return;
    const url = new URL(request.url());
    responses.push({
      path: url.origin === base ? url.pathname : url.host + url.pathname,
      external: url.origin !== base,
      type: request.resourceType(),
      bytes: sizes.responseBodySize,
      start: request.timing().startTime ? request.timing().startTime - t0 : 0,
    });
  });
  let t0 = 0;
  page.on("request", () => {
    if (!t0) t0 = Date.now();
  });
  await page.goto(base + "/", { waitUntil: "commit" });
  await page.waitForFunction(() => window.__perf?.ready !== null && window.__perf?.ready !== undefined, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const result = await page.evaluate(() => ({
    fcp: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
    lcp: window.__perf.lcp,
    ready: window.__perf.ready,
    renderer: (() => {
      const gl = document.createElement("canvas").getContext("webgl2");
      const info = gl?.getExtension("WEBGL_debug_renderer_info");
      return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : "no webgl2";
    })(),
  }));
  await context.close();
  const js = responses.filter((r) => r.type === "script");
  const entryJs = js.filter((r) => entry.has(r.path));
  const sum = (xs) => xs.reduce((a, r) => a + r.bytes, 0);
  return {
    fcpMs: round(result.fcp),
    lcpMs: round(result.lcp),
    globeReadyMs: round(result.ready),
    renderer: result.renderer,
    entryJsKB: round(sum(entryJs) / 1024, 1),
    allJsKB: round(sum(js) / 1024, 1),
    cssKB: round(sum(responses.filter((r) => r.type === "stylesheet")) / 1024, 1),
    totalKB: round(sum(responses) / 1024),
    files: js.map((r) => `${r.path} ${round(r.bytes / 1024, 1)} KB`).sort(),
    requests: responses.length,
  };
}

/** Frame rate in the module: the turn, then two flights to a facility, on the throttled phone. */
async function fpsRun(browser, base) {
  const { context, page } = await newPage(browser, base, { throttle: true });
  await page.addInitScript(instrument);
  await page.goto(base + "/explore?m=pollution-hunter", { waitUntil: "commit" });
  await page.waitForFunction(() => window.__perf?.ready != null, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(7000); // tiles in, the glow faded up
  const turn = await sampleFrames(page, 4000);
  const open = (id) =>
    page.evaluate((facility) => {
      history.pushState(null, "", `/explore?m=pollution-hunter&f=${facility}`);
      dispatchEvent(new PopStateEvent("popstate"));
    }, id);
  await open(FACILITY_NEAR);
  const flyNear = await sampleFrames(page, 4500);
  await page.waitForTimeout(2500);
  await open(FACILITY_FAR);
  const flyFar = await sampleFrames(page, 4500);
  await context.close();
  return { turn, flyNear, flyFar };
}

/**
 * What the app still asks the browser to run while the tab is hidden, against the same time
 * visible. Two views: the globe turning on its own, and a facility open with its flipbook playing.
 */
async function hiddenRun(browser, base, route) {
  const { context, page } = await newPage(browser, base, { throttle: false });
  await page.addInitScript(instrument);
  await page.goto(base + route, { waitUntil: "commit" });
  await page.waitForFunction(() => window.__perf?.ready != null, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(9000); // any flight is over
  await page.evaluate(() => (window.__perf.stacks = true));
  const read = () => page.evaluate(() => ({ raf: window.__perf.raf - window.__perf.rafDeck, timers: window.__perf.timers }));
  const count = async (ms) => {
    const before = await read();
    await page.waitForTimeout(ms);
    const after = await read();
    return {
      appFramesPerSec: round(((after.raf - before.raf) / ms) * 1000, 1),
      timersPerSec: round(((after.timers - before.timers) / ms) * 1000, 1),
    };
  };
  const visible = await count(3000);
  await page.evaluate(() => window.__setHidden(true));
  await page.waitForTimeout(500);
  const hidden = await count(3000);
  await page.evaluate(() => window.__setHidden(false));
  await page.waitForTimeout(800);
  const back = await count(2000);
  await context.close();
  return { visible, hidden, backVisible: back };
}

const server = await serve();
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({
  channel: "msedge",
  headless: true,
  args: gpu ? ["--ignore-gpu-blocklist", "--use-angle=d3d11"] : ["--enable-unsafe-swiftshader"],
});
const report = { label, at: new Date().toISOString(), gpu, phone: { viewport: "412x915 @2.625x", cpuSlowdown: CPU_SLOWDOWN, net: "9 Mbit/s, 100 ms RTT, brotli" } };
try {
  const loads = [];
  if (only.includes("load")) for (let i = 0; i < runs; i++) loads.push(await loadRun(browser, base));
  if (loads.length) report.load = {
    runs: loads.length,
    fcpMs: median(loads.map((r) => r.fcpMs)),
    lcpMs: median(loads.map((r) => r.lcpMs)),
    globeReadyMs: median(loads.map((r) => r.globeReadyMs)),
    entryJsKB: loads[0].entryJsKB,
    allJsKB: loads[0].allJsKB,
    cssKB: loads[0].cssKB,
    totalKB: loads[0].totalKB,
    renderer: loads[0].renderer,
    files: loads[0].files,
    each: loads.map((r) => ({ fcpMs: r.fcpMs, globeReadyMs: r.globeReadyMs })),
  };
  const fps = [];
  if (only.includes("fps")) for (let i = 0; i < Math.max(1, runs - 1); i++) fps.push(await fpsRun(browser, base));
  if (fps.length) {
    report.fps = {};
    for (const phase of ["turn", "flyNear", "flyFar"]) {
      report.fps[phase] = Object.fromEntries(
        Object.keys(fps[0][phase]).map((k) => [k, median(fps.map((r) => r[phase][k]))]),
      );
    }
  }
  if (only.includes("hidden")) {
    report.hidden = {
      turning: await hiddenRun(browser, base, "/explore?m=pollution-hunter"),
      facilityOpen: await hiddenRun(browser, base, `/explore?m=pollution-hunter&f=${FACILITY_FAR}`),
    };
  }
} finally {
  await browser.close();
  server.close();
}
console.log(JSON.stringify(report, null, 2));
if (out) {
  const file = path.resolve(process.cwd(), out);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify(report, null, 2) + "\n");
  console.log("wrote", file);
}
