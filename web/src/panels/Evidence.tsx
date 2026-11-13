import { useState } from "react";

import { Flipbook } from "../charts/Flipbook";
import { PlumeImage } from "../charts/PlumeImage";
import { PlumeProfileChart, PlumeProfileTable } from "../charts/PlumeProfile";
import type { DayRow, Evidence as EvidenceData, Observed, PlumeProfileData } from "../data/types";

// The evidence tabs of the VerdictPanel (PLAN.md 9.6): plume image, curve, flipbook.
const TABS = [
  { id: "plume", label: "Plume" },
  { id: "curve", label: "Curve" },
  { id: "flipbook", label: "Flipbook" },
] as const;
type TabId = (typeof TABS)[number]["id"];

interface Props {
  evidence: EvidenceData;
  profile: PlumeProfileData;
  days: DayRow[];
  observed: Observed;
  year: string;
}

export function Evidence({ evidence, profile, days, observed, year }: Props) {
  const [tab, setTab] = useState<TabId>("plume");
  const [curveView, setCurveView] = useState<"chart" | "table">("chart");

  return (
    <section className="mt-5 border-t border-hairline pt-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="label">What the satellite saw</h3>
        <div role="group" aria-label="Evidence" className="-mr-2 flex">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className="text-button"
              aria-pressed={tab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2">
        {tab === "plume" && (
          <PlumeImage src={evidence.stack_image} stack={evidence.stack} times={profile.t_h} year={year} />
        )}
        {tab === "curve" && (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="text-[12px] leading-4 text-text-2">
                NO<sub>2</sub> carried downwind, mol/s
              </p>
              <div role="group" aria-label="Show as" className="-mr-2 -mt-2 flex">
                <button
                  type="button"
                  className="text-button"
                  aria-pressed={curveView === "chart"}
                  onClick={() => setCurveView("chart")}
                >
                  Chart
                </button>
                <button
                  type="button"
                  className="text-button"
                  aria-pressed={curveView === "table"}
                  onClick={() => setCurveView("table")}
                >
                  Table
                </button>
              </div>
            </div>
            {curveView === "chart" ? (
              <PlumeProfileChart profile={profile} observed={observed} nDays={evidence.stack.n_days} />
            ) : (
              <PlumeProfileTable profile={profile} />
            )}
            <p className="mt-2 text-[12px] leading-4 text-text-3">
              The plume image, added up across the wind. The curve jumps at the source and fades as the gas
              breaks down. A fitted curve reads off both: how high it jumps and how fast it fades.
            </p>
          </>
        )}
        {tab === "flipbook" && (
          <Flipbook src={evidence.flipbook} sheet={evidence.flipbook_sheet} days={days} year={year} />
        )}
      </div>
    </section>
  );
}
