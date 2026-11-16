import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { NO2_ATTRIBUTION } from "../modules/pollution-hunter/no2";
import { Leaderboard } from "../panels/Leaderboard";
import { DataBody } from "./DataBody";
import { MethodBody } from "./MethodBody";
import { Link } from "./Link";
import type { PageView } from "./route";

// The pages behind the quiet links of the home screen. They are placeholders for now: each says
// what the page will hold and nothing more (AGENTS.md rule 6, no invented numbers). The full
// pages are milestones of their own in PLAN.md section 6: M6.4, M6.7 and M8.3.

export const PAGE_TITLES: Record<PageView, string> = {
  leaderboard: "Leaderboard",
  method: "Method",
  data: "Data",
  about: "About",
};

const BODIES: Record<PageView, ReactNode> = {
  leaderboard: <Leaderboard />,
  method: <MethodBody />,
  data: <DataBody />,
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
      <h2>Who built it</h2>
      <p>Built by Badr Waqas, Data Science student at National College of Ireland.</p>
      <ul className="page-links">
        <li>
          GitHub:{" "}
          <a className="page-link" href="https://github.com/BadrWaqas" target="_blank" rel="noopener noreferrer">
            github.com/BadrWaqas
          </a>
        </li>
        <li>
          LinkedIn:{" "}
          <a className="page-link" href="https://www.linkedin.com/in/badrw" target="_blank" rel="noopener noreferrer">
            linkedin.com/in/badrw
          </a>
        </li>
      </ul>
      <h2>Data</h2>
      <p>
        Satellite NO<sub>2</sub>: {NO2_ATTRIBUTION}. Reported emissions: EEA Industrial Reporting
        database. Base map: OpenStreetMap contributors, through OpenFreeMap. Night lights: NASA
        Black Marble, from the VIIRS instrument.
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
