import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { useFindingDetail, useFindings } from "../data/findings";
import { Stars } from "../globe/Stars";
import { Legend } from "../modules/pollution-hunter/Legend";
import { plumeClock, plumeFrames } from "../modules/pollution-hunter/plumeClock";
import type { SitePlumeSpec } from "../modules/pollution-hunter/sitePlume";
import { FacilityPanel } from "../panels/FacilityPanel";
import { STORY_FLIGHT_MS, STORY_PANEL_LEAD_MS } from "./layout";
import { useSelection } from "./useSelection";

// MapLibre is the heaviest dependency. Loading it as its own chunk lets the text paint first.
const Globe = lazy(() => import("../globe/Globe").then((m) => ({ default: m.Globe })));

// The intro (PLAN.md 9.7): the one orchestrated moment. Times are from the moment the live map
// is ready. The matching animations are in design/index.css under "The intro".
//
//   0.0 s  the map cross-fades in over the stars, turning slowly, and the NO2 starts to glow
//   0.6 s  the wordmark
//   1.2 s  hero line 1, the record voice
//   2.0 s  hero line 2, the instrument voice
//   2.8 s  the tagline
//   3.5 s  the button
//
// Any input skips it. It plays once per browser session, never for visitors who ask for reduced
// motion, and never on a link that opens a facility.
const INTRO_AT_MS = { wordmark: 600, record: 1200, instrument: 2000, tagline: 2800, button: 3500 };
const INTRO_END_MS = INTRO_AT_MS.button + 900;
const INTRO_SEEN_KEY = "orbyt:intro-seen";
const GLOBE_MAX_WAIT_MS = 5000; // show whatever the map has by then, tiles or not

type Intro = "waiting" | "playing" | "done";

function introWanted(): boolean {
  if (new URLSearchParams(window.location.search).has("f")) return false;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
  try {
    return window.sessionStorage.getItem(INTRO_SEEN_KEY) === null;
  } catch {
    return true; // storage is blocked: play it, there is no way to remember
  }
}

const at = (ms: number) => ({ "--intro-at": `${ms}ms` }) as CSSProperties;

export function App() {
  const [no2Visible, setNo2Visible] = useState(false);
  const showLegend = useCallback(() => setNo2Visible(true), []);

  const findings = useFindings();
  const list = findings.status === "ready" ? findings.data.findings : null;
  const [selectedId, select] = useSelection();
  const selected = useMemo(
    () => list?.find((f) => f.subject.id === selectedId) ?? null,
    [list, selectedId],
  );
  const showcaseId = findings.status === "ready" ? (findings.data.showcase ?? null) : null;

  // A link can name a facility that is no longer in the data. Drop it from the address.
  useEffect(() => {
    if (list && selectedId && !selected) select(null);
  }, [list, selectedId, selected, select]);

  // The live map cross-fades in when it has drawn its first complete frame.
  const [globeReady, setGlobeReady] = useState(false);
  const showGlobe = useCallback(() => setGlobeReady(true), []);
  useEffect(() => {
    if (globeReady) return;
    const timer = window.setTimeout(showGlobe, GLOBE_MAX_WAIT_MS);
    return () => window.clearTimeout(timer);
  }, [globeReady, showGlobe]);

  // The intro.
  const [intro, setIntro] = useState<Intro>(() => (introWanted() ? "waiting" : "done"));
  const introRuns = useRef(intro !== "done").current; // fixed for this page view
  useEffect(() => {
    if (intro !== "waiting" || !globeReady) return;
    setIntro("playing");
    try {
      window.sessionStorage.setItem(INTRO_SEEN_KEY, "1");
    } catch {
      // Storage is blocked. The intro will play again on the next visit.
    }
  }, [intro, globeReady]);
  useEffect(() => {
    if (intro !== "playing") return;
    const timer = window.setTimeout(() => setIntro("done"), INTRO_END_MS);
    return () => window.clearTimeout(timer);
  }, [intro]);
  useEffect(() => {
    if (intro === "done") return;
    const skip = () => setIntro("done");
    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    for (const name of events) window.addEventListener(name, skip, { capture: true, passive: true });
    return () => {
      for (const name of events) window.removeEventListener(name, skip, { capture: true });
    };
  }, [intro]);

  // "Explore the globe" flies to the first story facility. The flight is the long one of 9.7,
  // and the panel waits for it: it slides in 300 ms before arrival.
  const [storyId, setStoryId] = useState<string | null>(null);
  const storyTimer = useRef(0);
  const explore = useCallback(() => {
    if (!showcaseId) return;
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStoryId(showcaseId);
      window.clearTimeout(storyTimer.current);
      storyTimer.current = window.setTimeout(() => setStoryId(null), STORY_FLIGHT_MS - STORY_PANEL_LEAD_MS);
    }
    select(showcaseId);
  }, [showcaseId, select]);
  useEffect(() => () => window.clearTimeout(storyTimer.current), []);
  // Anything else the visitor picks in the meantime ends the wait.
  const inFlight = storyId !== null && storyId === selectedId;
  const shown = inFlight ? null : selected;
  const close = useCallback(() => {
    setStoryId(null);
    select(null);
  }, [select]);

  // A facility with a satellite estimate has a frame for each clear day. The globe draws them
  // around the site, one day at a time, and the legend names the day on show.
  const detail = useFindingDetail(selected?.observed ? selected.id : null);
  const detailData = detail.status === "ready" ? detail.data : null;
  const site = useMemo(() => {
    if (!selected || detailData?.id !== selected.id) return null;
    const { evidence, days } = detailData;
    if (!evidence || !days) return null;
    const frames = plumeFrames(days);
    if (frames.length === 0) return null;
    const plume: SitePlumeSpec = {
      id: selected.id,
      lat: selected.subject.lat,
      lon: selected.subject.lon,
      src: evidence.flipbook,
      sheet: evidence.flipbook_sheet,
      positions: frames.map((d) => d.frame as number),
    };
    return { plume, frames, fullScale: evidence.flipbook_sheet.full_scale_umol_m2 };
  }, [selected, detailData]);
  const siteId = site?.plume.id;
  useEffect(() => plumeClock.rewind(), [siteId]);
  const [sitePlumeShown, setSitePlumeShown] = useState(false);

  // The hero belongs to the opening view. It steps aside once the visitor zooms in or opens a
  // facility, and a short prompt takes its place.
  const [zoomedIn, setZoomedIn] = useState(false);
  const [hasSelected, setHasSelected] = useState(selectedId !== null);
  if (selectedId && !hasSelected) setHasSelected(true);
  const explored = zoomedIn || hasSelected;
  const noteZoom = useCallback(() => setZoomedIn(true), []);
  const heroHidden = explored || findings.status === "error"; // the error notice takes its place

  return (
    <main
      className="relative h-dvh w-full overflow-hidden bg-void text-text"
      data-panel={shown ? "open" : "closed"}
      data-globe={globeReady ? "ready" : "loading"}
      data-intro={intro}
      data-intro-runs={introRuns}
    >
      <Stars />
      <Suspense fallback={null}>
        <Globe
          findings={list}
          selected={selected}
          storyId={storyId}
          intro={introRuns}
          sitePlume={site?.plume ?? null}
          onSitePlume={setSitePlumeShown}
          onSelect={select}
          onReady={showGlobe}
          onNo2Visible={showLegend}
          onExplore={noteZoom}
        />
      </Suspense>

      <header
        className="intro-item pointer-events-none absolute left-[var(--margin-outer)] top-[max(var(--margin-outer),env(safe-area-inset-top))]"
        style={at(INTRO_AT_MS.wordmark)}
      >
        <span className="wordmark text-[18px] leading-6">Orbyt Earth</span>
      </header>

      <Legend
        visible={no2Visible}
        site={site && sitePlumeShown ? { frames: site.frames, fullScale: site.fullScale } : null}
      />

      <section
        aria-hidden={heroHidden}
        inert={heroHidden || intro === "waiting"}
        className={`pointer-events-none absolute inset-x-0 bottom-[max(48px,env(safe-area-inset-bottom))] px-[var(--margin-outer)] text-center motion-safe:transition-opacity motion-safe:duration-[240ms] ${
          heroHidden ? "opacity-0" : "opacity-100"
        }`}
      >
        <h1 className="hero-title">
          <span className="intro-item voice-record block" style={at(INTRO_AT_MS.record)}>
            Reported on paper.
          </span>
          <span className="intro-item voice-instrument hero-glow block" style={at(INTRO_AT_MS.instrument)}>
            Measured from orbit.
          </span>
        </h1>
        <p className="intro-item mt-3 text-[14px] leading-5 text-text-2 md:text-[16px] md:leading-6" style={at(INTRO_AT_MS.tagline)}>
          Fact-checking the world from space.
        </p>
        {/* PLAN.md 9.7: a quiet button that flies to the first story facility. */}
        {showcaseId && (
          <button
            type="button"
            className={`intro-item glass quiet-button mt-4 ${heroHidden ? "" : "pointer-events-auto"}`}
            style={at(INTRO_AT_MS.button)}
            onClick={explore}
          >
            Explore the globe
          </button>
        )}
      </section>

      {findings.status === "error" ? (
        <p className="glass absolute bottom-[max(48px,env(safe-area-inset-bottom))] left-1/2 w-max max-w-[calc(100%-2*var(--margin-outer))] -translate-x-1/2 px-4 py-1 text-[14px] leading-5 text-text-2">
          Could not load the facilities.{" "}
          <button type="button" className="text-button underline underline-offset-4" onClick={findings.retry}>
            Try again
          </button>
        </p>
      ) : (
        explored &&
        list &&
        !selectedId && (
          <p className="glass pointer-events-none absolute bottom-[max(48px,env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 whitespace-nowrap px-4 py-2 text-[14px] leading-5 text-text-2">
            Pick a facility on the globe
          </p>
        )
      )}

      <FacilityPanel
        finding={shown}
        lastYear={findings.status === "ready" ? Number(findings.data.period) : 0}
        onClose={close}
      />
    </main>
  );
}
