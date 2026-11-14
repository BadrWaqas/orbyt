import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { useFindings } from "../data/findings";
import { Stars } from "../globe/Stars";
import { Legend } from "../modules/pollution-hunter/Legend";
import { FacilityPanel } from "../panels/FacilityPanel";
import { useSelection } from "./useSelection";

// MapLibre is the heaviest dependency. Loading it as its own chunk lets the text paint first.
const Globe = lazy(() => import("../globe/Globe").then((m) => ({ default: m.Globe })));

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
  const close = useCallback(() => select(null), [select]);
  const showcaseId = findings.status === "ready" ? (findings.data.showcase ?? null) : null;

  // A link can name a facility that is no longer in the data. Drop it from the address.
  useEffect(() => {
    if (list && selectedId && !selected) select(null);
  }, [list, selectedId, selected, select]);

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
      data-panel={selected ? "open" : "closed"}
    >
      <Stars />
      <Suspense fallback={null}>
        <Globe
          findings={list}
          selected={selected}
          onSelect={select}
          onNo2Visible={showLegend}
          onExplore={noteZoom}
        />
      </Suspense>

      <header
        className="pointer-events-none absolute left-[var(--margin-outer)] top-[max(var(--margin-outer),env(safe-area-inset-top))]"
      >
        <span className="wordmark text-[18px] leading-6">Orbyt Earth</span>
      </header>

      <Legend visible={no2Visible} />

      <section
        aria-hidden={heroHidden}
        inert={heroHidden}
        className={`pointer-events-none absolute inset-x-0 bottom-[max(48px,env(safe-area-inset-bottom))] px-[var(--margin-outer)] text-center motion-safe:transition-opacity motion-safe:duration-[240ms] ${
          heroHidden ? "opacity-0" : "opacity-100"
        }`}
      >
        <h1 className="text-[24px] leading-[30px] md:text-[36px] md:leading-[42px]">
          <span className="voice-record block">Reported on paper.</span>
          <span className="voice-instrument block">Measured from orbit.</span>
        </h1>
        <p className="mt-3 text-[14px] leading-5 text-text-2">
          Fact-checking the world from space.
        </p>
        {/* PLAN.md 9.7: a quiet button that flies to the first story facility. */}
        {showcaseId && (
          <button
            type="button"
            className={`glass quiet-button mt-4 ${heroHidden ? "" : "pointer-events-auto"}`}
            onClick={() => select(showcaseId)}
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
        finding={selected}
        lastYear={findings.status === "ready" ? Number(findings.data.period) : 0}
        onClose={close}
      />
    </main>
  );
}
