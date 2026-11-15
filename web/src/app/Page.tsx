import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { NO2_ATTRIBUTION } from "../modules/pollution-hunter/no2";
import { Leaderboard } from "../panels/Leaderboard";
import { Link } from "./Link";
import type { PageView } from "./route";

// The pages behind the quiet links of the home screen. They are placeholders for now: each says
// what the page will hold and nothing more (AGENTS.md rule 6, no invented numbers). The full
// pages are milestones of their own in PLAN.md section 6: M6.4, M6.7 and M8.3.

export const PAGE_TITLES: Record<PageView, string> = {
  leaderboard: "Leaderboard",
  method: "Method",
  about: "About",
};

const BODIES: Record<PageView, ReactNode> = {
  leaderboard: <Leaderboard />,
  method: (
    <>
      <p>Every satellite estimate on Orbyt Earth comes from the same five steps.</p>
      <ol>
        <li>
          Collect every clear, windy day in a year of Sentinel-5P NO<sub>2</sub> images around the
          source.
        </li>
        <li>
          Rotate each day so the wind points the same way, and turn distance from the source into
          travel time.
        </li>
        <li>
          Average the days. The noise cancels and one curve is left: it jumps at the source and
          fades downwind.
        </li>
        <li>
          Fit that curve. Its height gives the emission rate, and its decay gives the lifetime of
          NO<sub>2</sub> in the plume.
        </li>
        <li>
          Convert NO<sub>2</sub> to NO<sub>x</sub>, correct for the satellite reading low near
          point sources, and resample the days to get an interval. Only then is the estimate set
          next to the reported figure.
        </li>
      </ol>
      <p>The full method page, with every constant and its source, is on its way.</p>
    </>
  ),
  about: (
    <>
      <p>
        Orbyt Earth fact-checks the world from space. We compare what facilities report with what
        satellites measure, and show our working.
      </p>
      <p>
        Each module puts an official record next to a satellite measurement and shows the gap on
        the globe. Pollution Hunter is the first: reported NO<sub>x</sub> emissions next to the
        NO<sub>2</sub> that Sentinel-5P sees. Five more modules are planned.
      </p>
      <p>
        Orbyt Earth is an independent student research project. Estimates are uncertain and are
        not findings of non-compliance.
      </p>
      <h2>Data</h2>
      <p>
        Satellite NO<sub>2</sub>: {NO2_ATTRIBUTION}. Reported emissions: EEA Industrial Reporting
        database. Base map: OpenStreetMap contributors, through OpenFreeMap.
      </p>
    </>
  ),
};

export function Page({ view }: { view: PageView }) {
  // Keyboard and screen reader users land on the new page's title.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus({ preventScroll: true }), [view]);

  return (
    <article className="page" key={view}>
      <div className={view === "leaderboard" ? "page-column page-column-wide" : "page-column"}>
        <h1 ref={title} tabIndex={-1} className="page-title">
          {PAGE_TITLES[view]}
        </h1>
        <div className="page-body">{BODIES[view]}</div>
        <p className="mt-8 flex flex-wrap items-center gap-2">
          <Link to="module" className="glass quiet-button">
            Open Pollution Hunter
          </Link>
          <Link to="home" className="text-button nav-link">
            Back to the globe
          </Link>
        </p>
      </div>
    </article>
  );
}
