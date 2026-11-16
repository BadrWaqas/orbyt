// Writes a share page for every finding (PLAN.md 2.7, M6.5): /f/<slug>/index.html, a copy of the
// built app shell with that facility's title, description and share picture in its meta tags, so
// a link to it unfurls properly on LinkedIn, X, Slack and the like. It also gives the home page
// its own picture and tags.
//
//   npm run build        runs it after vite build
//
// Crawlers read the tags and stop. A person's browser runs one line first that moves the address
// to /explore?m=pollution-hunter&f=<id>, and the app opens on that facility as it always did.
//
// The pictures come from make-share-cards.mjs and are committed in public/img/share/. A page
// whose picture is missing stops the build, because a link with no picture is what this is for.

import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sharePath } from "../src/data/slug.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST = path.join(root, "dist");
const FINDINGS = path.join(root, "public", "data", "v1", "pollution-hunter", "findings.json");
const CARDS = path.join(root, "public", "img", "share");

// The address the pictures and links are published at. Change it when the domain is bought
// (PLAN.md M8.4), or set SITE_URL for a build. No trailing slash.
const SITE_URL = (process.env.SITE_URL ?? "https://orbyt-earth.pages.dev").replace(/\/+$/, "");
const SITE_NAME = "Orbyt Earth";
const HOME_TITLE = "Orbyt Earth: fact-checking the world from space";
const MARK_START = "<!-- share-meta:start -->";
const MARK_END = "<!-- share-meta:end -->";
// LinkedIn and others keep a card by its address. Raise this when the cards change in a way a
// stale copy would hide (v2: the shared cards rendered at 2400 x 1260), so the next scrape
// fetches them again.
const CARD_VERSION = "2";

/** Width and height of a JPEG, from its first frame header. */
function jpegSize(bytes) {
  let i = 2; // after the start of image marker
  while (i + 9 < bytes.length) {
    if (bytes[i] !== 0xff) throw new Error("not a JPEG");
    const marker = bytes[i + 1];
    const length = bytes.readUInt16BE(i + 2);
    // Start of frame: baseline, extended or progressive.
    if (marker >= 0xc0 && marker <= 0xc3) return { height: bytes.readUInt16BE(i + 5), width: bytes.readUInt16BE(i + 7) };
    i += 2 + length;
  }
  throw new Error("no frame header");
}

/** The card's address and its pixel size: make-share-cards.mjs saves some at twice the layout. */
async function cardImage(id) {
  const { width, height } = jpegSize(await readFile(path.join(CARDS, `${id}.jpg`)));
  return { url: `${SITE_URL}/img/share/${id}.jpg?v=${CARD_VERSION}`, width, height };
}

const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const regions = new Intl.DisplayNames(["en"], { type: "region" });
const tonnes = (n) => whole.format(n);
const country = (iso2) => {
  try {
    return regions.of(iso2) ?? iso2;
  } catch {
    return iso2;
  }
};

// PLAN.md 7.2: the verdict words are fixed. Keep in step with VERDICT_LABEL in VerdictBlock.tsx.
const VERDICT = {
  higher: "Higher than reported",
  consistent: "Consistent with reported",
  lower: "Lower than reported",
  inconclusive: "Inconclusive",
  unpaired: "Nothing to compare",
};

const esc = (text) =>
  String(text).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** The wording of one finding, in the same two-facts-and-a-caveat voice as the panel. */
function words(f) {
  const { subject, period, claimed, observed, verdict } = f;
  const name = subject.display_name ?? subject.name;
  const us = f.validation_site === true;
  const record = us ? "Stack monitors" : "Reported";
  const parts = [];
  if (claimed) parts.push(`${record} for ${period.label}: ${tonnes(claimed.value)} t of NOx (${claimed.source}).`);
  if (observed) {
    const days = observed.n_days ? `, from ${observed.n_days} clear days` : "";
    parts.push(
      `Satellite-based estimate: ${tonnes(observed.value)} t, 95% interval ${tonnes(observed.lo)} to ${tonnes(observed.hi)}${days}.`,
    );
    if (us) parts.push("A test site for the method.");
    else if (verdict) parts.push(`${VERDICT[verdict]}.`);
    parts.push("An estimate, not a finding of non-compliance.");
  } else {
    parts.push("No satellite estimate yet.");
  }
  const title = `${name}, ${country(subject.country)}`;
  const alt = claimed
    ? `Share card for ${name}: ${record.toLowerCase()} ${tonnes(claimed.value)} t${observed ? `, satellite estimate ${tonnes(observed.value)} t` : ", no satellite estimate yet"}.`
    : `Share card for ${name}.`;
  return { title, description: parts.join(" "), alt };
}

function metaBlock({ title, description, url, image, alt }) {
  const tags = [
    `<link rel="canonical" href="${esc(url)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${esc(SITE_NAME)}" />`,
    `<meta property="og:title" content="${esc(title)}" />`,
    `<meta property="og:description" content="${esc(description)}" />`,
    `<meta property="og:url" content="${esc(url)}" />`,
    `<meta property="og:image" content="${esc(image.url)}" />`,
    `<meta property="og:image:type" content="image/jpeg" />`,
    `<meta property="og:image:width" content="${image.width}" />`,
    `<meta property="og:image:height" content="${image.height}" />`,
    `<meta property="og:image:alt" content="${esc(alt)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${esc(title)}" />`,
    `<meta name="twitter:description" content="${esc(description)}" />`,
    `<meta name="twitter:image" content="${esc(image.url)}" />`,
    `<meta name="twitter:image:alt" content="${esc(alt)}" />`,
  ];
  return `    ${MARK_START}\n    ${tags.join("\n    ")}\n    ${MARK_END}\n`;
}

/** Put a title, description and the share tags into the shell. Works on a shell already patched. */
function patch(shell, { title, description, url, image, alt, redirect }) {
  let html = shell.replace(new RegExp(`\\s*${MARK_START}[\\s\\S]*?${MARK_END}\\n?`), "\n");
  html = html.replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`);
  html = html.replace(/<meta\s+name="description"[\s\S]*?\/>/, `<meta name="description" content="${esc(description)}" />`);
  if (!html.includes("</head>") || !html.includes("<title>")) throw new Error("dist/index.html has no head to patch");
  const script = redirect
    ? `    <script>history.replaceState(null, "", ${JSON.stringify(redirect)});</script>\n`
    : "";
  return html.replace("</head>", `${script}${metaBlock({ title, description, url, image, alt })}  </head>`);
}

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

const shell = await readFile(path.join(DIST, "index.html"), "utf8").catch(() => {
  throw new Error("dist/index.html not found. Run vite build first.");
});
const payload = JSON.parse(await readFile(FINDINGS, "utf8"));

const missing = [];
for (const f of payload.findings) if (!(await exists(path.join(CARDS, `${f.id}.jpg`)))) missing.push(f.id);
if (!(await exists(path.join(CARDS, "home.jpg")))) missing.push("home");
if (missing.length) {
  throw new Error(`${missing.length} share card(s) missing from public/img/share/. Run: npm run share:cards`);
}

// The home page.
const homeDescription =
  "We compare what facilities report with what satellites measure, and show our working.";
await writeFile(
  path.join(DIST, "index.html"),
  patch(shell, {
    title: HOME_TITLE,
    description: homeDescription,
    url: `${SITE_URL}/`,
    image: await cardImage("home"),
    alt: "Reported on paper. Measured from orbit. A night globe over Europe.",
  }),
);

// One page per finding.
const slugs = new Set();
for (const f of payload.findings) {
  const rel = sharePath(f.subject);
  if (slugs.has(rel)) throw new Error(`Two findings share the address ${rel}`);
  slugs.add(rel);
  const { title, description, alt } = words(f);
  const params = new URLSearchParams({ m: "pollution-hunter", f: f.subject.id });
  const html = patch(shell, {
    title: `${title} | ${SITE_NAME}`,
    description,
    url: `${SITE_URL}${rel}`,
    image: await cardImage(f.id),
    alt,
    redirect: `/explore?${params}`,
  });
  const dir = path.join(DIST, rel);
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "index.html"), html);
}

console.log(`wrote ${slugs.size} share pages and the home tags, pictures at ${SITE_URL}`);
