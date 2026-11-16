import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { useFindingDetail, useFindings } from "../data/findings";
import { Stars } from "../globe/Stars";
import { Legend } from "../modules/pollution-hunter/Legend";
import { plumeClock, plumeFrames } from "../modules/pollution-hunter/plumeClock";
import type { SitePlumeSpec } from "../modules/pollution-hunter/sitePlume";
import { timeClock } from "../modules/pollution-hunter/timeClock";
import type { HueName } from "../modules/registry";
import { FacilityPanel } from "../panels/FacilityPanel";
import { TimeRail, useNo2Layers } from "../panels/TimeRail";
import { EarthHalo, Home, OrbitRing } from "./Home";
import { homeLayout, STORY_FLIGHT_MS, STORY_PANEL_LEAD_MS } from "./layout";
import { Link } from "./Link";
import { Page, PAGE_TITLES } from "./Page";
import { navigate, selectFacility, useRoute, type PageView } from "./route";
import type { ChapterView } from "../globe/Globe";
import { chapters, type ChapterFacts } from "../story/chapters";
import { Story } from "../story/Story";

// MapLibre is the heaviest dependency. Loading it as its own chunk lets the text paint first.
const Globe = lazy(() => import("../globe/Globe").then((m) => ({ default: m.Globe })));

// The intro (PLAN.md 9.7): the one orchestrated moment. It belongs to Pollution Hunter and plays
// when the module opens. The matching animations are in design/index.css under "The intro".
//
// A visitor who lands in the module directly gets it as the page loads. Times are from the
// moment the live map is ready:
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
// A visitor who comes in from the home screen gets the same lines at the end of the dive toward
// the Earth. Times are from the click on the module's card. The logo is already there.
const DIVE_AT_MS = { wordmark: 0, record: 1500, instrument: 2200, tagline: 2900, button: 3400 };
const INTRO_TAIL_MS = 900; // the last piece's own animation
const INTRO_SEEN_KEY = "orbyt:intro-seen";
const GLOBE_MAX_WAIT_MS = 5000; // show whatever the map has by then, tiles or not

const NAV: readonly ("story" | PageView)[] = ["story", "leaderboard", "method", "data", "about"];
const NAV_TITLES: Record<"story" | PageView, string> = { story: "Story", ...PAGE_TITLES };

type Intro = "waiting" | "playing" | "done";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function introSeen() {
  try {
    window.sessionStorage.setItem(INTRO_SEEN_KEY, "1");
  } catch {
    // Storage is blocked. The intro will play again on the next visit.
  }
}

/** Whether a page that loads straight into the module opens with the intro. */
function introWanted(inModule: boolean, facilityOpen: boolean): boolean {
  if (!inModule || facilityOpen || reducedMotion()) return false;
  try {
    return window.sessionStorage.getItem(INTRO_SEEN_KEY) === null;
  } catch {
    return true; // storage is blocked: play it, there is no way to remember
  }
}

const at = (ms: number) => ({ "--intro-at": `${ms}ms` }) as CSSProperties;

function useWindowSize(): { width: number; height: number } {
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight });
  useEffect(() => {
    const update = () => setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return size;
}

export function App() {
  const { view, selectedId } = useRoute();
  const inStory = view === "story";
  const inModule = view === "module" || inStory; // the story is the module's globe with the chapters over it
  const onGlobe = view === "home" || inModule;
  const page = onGlobe ? null : (view as PageView);
  const select = selectFacility;

  useEffect(() => {
    const here = inStory ? "Story" : inModule ? "Pollution Hunter" : page ? PAGE_TITLES[page] : null;
    document.title = here ? `${here} | Orbyt Earth` : "Orbyt Earth";
  }, [inModule, inStory, page]);

  // The home screen's geometry: where the Earth sits and how large, and where the cards go.
  const size = useWindowSize();
  const layout = useMemo(() => homeLayout(size.width, size.height), [size.width, size.height]);
  const [hue, setHue] = useState<HueName | null>(null);
  // Coming back to the home screen, its pieces wait for the camera to pull away first.
  const [hasLeftHome, setHasLeftHome] = useState(view !== "home");
  if (view !== "home" && !hasLeftHome) setHasLeftHome(true);
  const entry = useRef(view).current; // the view this page load opened on

  const [no2Visible, setNo2Visible] = useState(false);
  const showLegend = useCallback(() => setNo2Visible(true), []);
  // The NO2 layers the pipeline published: the annual mean and the months for the time rail.
  const no2Layers = useNo2Layers();
  const months = useMemo(() => no2Layers?.monthly?.periods ?? [], [no2Layers]);

  const findings = useFindings();
  const list = findings.status === "ready" ? findings.data.findings : null;
  const showcaseId = findings.status === "ready" ? (findings.data.showcase ?? null) : null;

  // The scroll story (M7.4): which chapter is in the middle of the screen, and what it asks
  // of the globe. In the story the open facility is the chapter's, not the address's.
  const [chapterIndex, setChapterIndex] = useState(0);
  const chapter = inStory ? chapters[chapterIndex] : null;
  const chapterFacilityId = chapter?.show.facility === "showcase" ? showcaseId : null;
  const chapterView = useMemo<ChapterView | null>(() => {
    if (!chapter) return null;
    const showcase = list?.find((f) => f.subject.id === showcaseId);
    const { camera } = chapter;
    const center: [number, number] =
      camera.center === "showcase"
        ? showcase
          ? [showcase.subject.lon, showcase.subject.lat]
          : [14, 28]
        : camera.center;
    return { index: chapterIndex, center, zoom: camera.zoom, pitch: camera.pitch, bearing: camera.bearing };
  }, [chapter, chapterIndex, list, showcaseId]);
  useEffect(() => {
    if (!inStory) setChapterIndex(0);
  }, [inStory]);
  // The last chapter plays the months; the others show the annual mean. The chapters with a
  // facility play its daily frames, whatever the motion setting: a single frame is often a
  // cloudy day, and the chapter is about the plume.
  useEffect(() => {
    if (!chapter) return;
    if (chapter.show.time === "play") timeClock.setPlaying(true);
    else timeClock.reset();
    if (chapter.show.facility) plumeClock.setPlaying(true);
  }, [chapter]);
  const facts = useMemo<ChapterFacts>(
    () => ({
      reporters: list?.filter((f) => f.subject.register === "EEA" && f.claimed).length ?? 0,
      year: findings.status === "ready" ? findings.data.period : "",
    }),
    [list, findings],
  );

  const selected = useMemo(() => {
    const id = inStory ? chapterFacilityId : selectedId;
    return list?.find((f) => f.subject.id === id) ?? null;
  }, [list, selectedId, inStory, chapterFacilityId]);

  // A link can name a facility that is no longer in the data. Drop it from the address.
  useEffect(() => {
    if (list && selectedId && !inStory && !selected) select(null);
  }, [list, selectedId, selected, select, inStory]);

  // The map is only fetched once a view needs it. From then on the one instance lives for the
  // whole session (PLAN.md 2.7), and every view drives the same camera.
  const [globeWanted, setGlobeWanted] = useState(onGlobe);
  if (onGlobe && !globeWanted) setGlobeWanted(true);

  // The live map cross-fades in when it has drawn its first complete frame.
  const [globeReady, setGlobeReady] = useState(false);
  const showGlobe = useCallback(() => setGlobeReady(true), []);
  useEffect(() => {
    if (globeReady || !globeWanted) return;
    const timer = window.setTimeout(showGlobe, GLOBE_MAX_WAIT_MS);
    return () => window.clearTimeout(timer);
  }, [globeReady, globeWanted, showGlobe]);

  // The intro.
  const [intro, setIntro] = useState<Intro>(() =>
    introWanted(inModule && !inStory, selectedId !== null) ? "waiting" : "done",
  );
  const [introTimes, setIntroTimes] = useState(INTRO_AT_MS);
  const introRuns = useRef(intro !== "done").current; // fixed for this page view
  useEffect(() => {
    if (intro !== "waiting" || !globeReady) return;
    setIntro("playing");
    introSeen();
  }, [intro, globeReady]);
  useEffect(() => {
    if (intro !== "playing") return;
    const timer = window.setTimeout(() => setIntro("done"), introTimes.button + INTRO_TAIL_MS);
    return () => window.clearTimeout(timer);
  }, [intro, introTimes]);
  useEffect(() => {
    if (intro === "done") return;
    const skip = () => setIntro("done");
    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    for (const name of events) window.addEventListener(name, skip, { capture: true, passive: true });
    return () => {
      for (const name of events) window.removeEventListener(name, skip, { capture: true });
    };
  }, [intro]);

  // The module's card on the home screen: the camera dives toward the Earth (globe/Globe.tsx
  // does that when the view changes) and the hero lines arrive as it settles.
  const enterModule = useCallback(() => {
    setHue(null);
    if (!reducedMotion()) {
      setIntroTimes(DIVE_AT_MS);
      setIntro("playing");
      introSeen();
    }
    navigate("module");
  }, []);

  // "Explore the globe" flies to the first story facility. The flight is the long one of 9.7,
  // and the panel waits for it: it slides in 300 ms before arrival.
  const [storyId, setStoryId] = useState<string | null>(null);
  const storyTimer = useRef(0);
  const explore = useCallback(() => {
    if (!showcaseId) return;
    if (!reducedMotion()) {
      setStoryId(showcaseId);
      window.clearTimeout(storyTimer.current);
      storyTimer.current = window.setTimeout(() => setStoryId(null), STORY_FLIGHT_MS - STORY_PANEL_LEAD_MS);
    }
    select(showcaseId);
  }, [showcaseId, select]);
  useEffect(() => () => window.clearTimeout(storyTimer.current), []);
  // Anything else the visitor picks in the meantime ends the wait. In the story the chapter
  // card is the text, so the panel stays closed.
  const inFlight = storyId !== null && storyId === selectedId;
  const shown = inFlight || inStory ? null : selected;
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

  // The hero belongs to the module's opening view. It steps aside once the visitor zooms in or
  // opens a facility, and a short prompt takes its place.
  const [zoomedIn, setZoomedIn] = useState(false);
  const [hasSelected, setHasSelected] = useState(selectedId !== null);
  if (selectedId && !hasSelected) setHasSelected(true);
  const explored = zoomedIn || hasSelected;
  const noteZoom = useCallback(() => setZoomedIn(true), []);
  const heroHidden = !inModule || inStory || explored || findings.status === "error"; // the error notice takes its place

  // Leaving the module ends its stay: the next visit starts from the opening view again.
  useEffect(() => {
    if (inModule) return;
    setZoomedIn(false);
    setHasSelected(false);
    setStoryId(null);
    setIntro("done");
    timeClock.reset();
  }, [inModule]);

  const fromLoad = introTimes === INTRO_AT_MS;
  const vars = {
    "--globe-cx": `${Math.round(layout.cx)}px`,
    "--globe-cy": `${Math.round(layout.cy)}px`,
    "--globe-d": `${Math.round(layout.diameter)}px`,
    "--home-delay": hasLeftHome ? "700ms" : "0ms",
  } as CSSProperties;

  return (
    <main
      className="relative h-dvh w-full overflow-hidden bg-void text-text"
      style={vars}
      data-view={page ? "page" : view}
      data-entry={entry === "home" ? "home" : "other"}
      data-panel={shown ? "open" : "closed"}
      data-globe={globeReady ? "ready" : "loading"}
      data-intro={intro}
      data-intro-runs={introRuns}
    >
      <Stars />
      <EarthHalo hue={hue} />
      <OrbitRing half="far" diameter={layout.diameter} />
      {globeWanted && (
        <Suspense fallback={null}>
          <Globe
            mode={page ? "idle" : inModule ? "module" : "home"}
            chapter={chapterView}
            findings={inModule && (!chapter || chapter.show.markers) ? list : null}
            selected={selected}
            storyId={storyId}
            intro={introRuns}
            months={months}
            sitePlume={site?.plume ?? null}
            onSitePlume={setSitePlumeShown}
            onSelect={select}
            onReady={showGlobe}
            onNo2Visible={showLegend}
            onExplore={noteZoom}
          />
        </Suspense>
      )}
      <OrbitRing half="near" diameter={layout.diameter} />

      {!page && <Home shown={view === "home"} layout={layout} onEnter={enterModule} onHue={setHue} />}
      {page && <Page view={page} />}
      {inStory && (
        <Story
          facts={facts}
          showcase={list?.find((f) => f.subject.id === showcaseId) ?? null}
          onChapter={setChapterIndex}
        />
      )}

      <header className={`site-header ${fromLoad ? "intro-item" : ""}`} style={at(introTimes.wordmark)}>
        {/* The logo returns home from anywhere. */}
        <Link to="home" className="logo" aria-label="Orbyt Earth, home">
          <svg className="logo-mark" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
            {/* The Earth with one orbit round it: the far half behind, the near half in front. */}
            <ellipse cx="12" cy="12" rx="10.5" ry="3.6" transform="rotate(-18 12 12)" />
            <circle className="logo-earth" cx="12" cy="12" r="5.2" />
            <path d="M1.5 12a10.5 3.6 0 0 0 21 0" transform="rotate(-18 12 12)" />
            <circle className="logo-satellite" cx="22" cy="8.8" r="1.3" />
          </svg>
          <span className="wordmark logo-word text-[18px] leading-6">Orbyt Earth</span>
        </Link>
        <nav className="site-nav" aria-label="Site" inert={inModule && !inStory}>
          {NAV.map((to) => (
            <Link
              key={to}
              to={to}
              className="text-button nav-link"
              aria-current={view === to ? "page" : undefined}
            >
              {NAV_TITLES[to]}
            </Link>
          ))}
        </nav>
      </header>

      <Legend
        visible={no2Visible && inModule && !inStory}
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
          <span className="intro-item voice-record block" style={at(introTimes.record)}>
            Reported on paper.
          </span>
          <span className="intro-item voice-instrument hero-glow block" style={at(introTimes.instrument)}>
            Measured from orbit.
          </span>
        </h1>
        <p className="intro-item mt-3 text-[14px] leading-5 text-text-2 md:text-[16px] md:leading-6" style={at(introTimes.tagline)}>
          Fact-checking the world from space.
        </p>
        {/* PLAN.md 9.7: a quiet button that flies to the first story facility. */}
        {showcaseId && (
          <button
            type="button"
            className={`intro-item glass quiet-button mt-4 ${heroHidden ? "" : "pointer-events-auto"}`}
            style={at(introTimes.button)}
            onClick={explore}
          >
            Explore the globe
          </button>
        )}
      </section>

      {inModule &&
        !inStory &&
        (findings.status === "error" ? (
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
            <p className="glass pointer-events-none absolute bottom-[calc(var(--time-rail-h)+max(48px,env(safe-area-inset-bottom)))] left-1/2 -translate-x-1/2 whitespace-nowrap px-4 py-2 text-[14px] leading-5 text-text-2 md:bottom-[max(48px,env(safe-area-inset-bottom))]">
              Pick a facility on the globe
            </p>
          )
        ))}

      <FacilityPanel
        finding={shown}
        lastYear={findings.status === "ready" ? Number(findings.data.period) : 0}
        onClose={close}
      />

      {/* The time rail (PLAN.md 9.6) takes the hero's place once the visitor has explored. */}
      <TimeRail layers={no2Layers} shown={inModule && !inStory && explored && no2Visible} />
    </main>
  );
}
