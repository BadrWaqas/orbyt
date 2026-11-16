import { useEffect, useMemo, useState } from "react";

import { loadNo2Layers } from "../modules/pollution-hunter/no2";
import type { No2Layers } from "../modules/pollution-hunter/no2";
import { monthLabel, timeClock, useTimeClock } from "../modules/pollution-hunter/timeClock";

// TimeRail (PLAN.md 9.6): a month scrubber from July 2022 to the latest month, a tick for each
// month and a label for each year. The play button moves through the months at 2 a second, the
// arrow keys step one month, and a month without data is hatched and cannot be landed on.
//
// At rest the globe shows the annual mean. Touching the rail moves it into the months, and one
// button brings the annual mean back. Styles are in design/index.css under "The time rail".

/** Every month from the first to the last, whether the layer has it or not. */
function monthsBetween(first: string, last: string): string[] {
  const out: string[] = [];
  let [year, month] = first.split("-").map(Number);
  const [lastYear, lastMonth] = last.split("-").map(Number);
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    out.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

/** Whether the first year's label fits before the next January's: at least nine months of it. */
function firstHasRoom(all: string[]): boolean {
  const january = all.findIndex((m, i) => i > 0 && m.endsWith("-01"));
  return january < 0 || january >= 9;
}

/** The layer manifest, once it has arrived. Null before that, and for good if there is none. */
export function useNo2Layers(): No2Layers | null {
  const [layers, setLayers] = useState<No2Layers | null>(null);
  useEffect(() => {
    let gone = false;
    loadNo2Layers().then(
      (loaded) => {
        if (!gone) setLayers(loaded);
      },
      () => {}, // no manifest, no rail
    );
    return () => {
      gone = true;
    };
  }, []);
  return layers;
}

interface Props {
  layers: No2Layers | null;
  /** False while the rail is out of sight. It then cannot be reached either. */
  shown: boolean;
}

export function TimeRail({ layers, shown }: Props) {
  const { month, playing } = useTimeClock();
  const have = layers?.monthly?.periods;
  const all = useMemo(() => (have?.length ? monthsBetween(have[0], have[have.length - 1]) : []), [have]);
  const missing = useMemo(() => new Set(all.filter((m) => !have?.includes(m))), [all, have]);

  // A link can name a month the layer does not have. It falls back to the annual mean.
  useEffect(() => {
    if (have && month && !have.includes(month)) timeClock.reset();
  }, [have, month]);

  if (!have || all.length < 2) return null;
  const annual = layers?.annual?.period;
  const last = all.length - 1;
  const index = month ? all.indexOf(month) : -1;
  const now = month ? monthLabel(month) : annual ? `${annual} mean` : "";

  const scrub = (position: number) => {
    // A month without data cannot be shown: the nearest earlier month with data stands in.
    let i = position;
    while (i > 0 && missing.has(all[i])) i -= 1;
    if (!missing.has(all[i])) timeClock.scrubTo(all[i]);
  };

  return (
    <section className="time-rail glass" aria-label="Time" aria-hidden={!shown} inert={!shown} data-shown={shown}>
      <div className="time-rail-head">
        <p className="time-rail-now" aria-live="off">
          <span className="text-text-3">Mean NO<sub>2</sub>, </span>
          {now}
        </p>
        {month && annual && (
          <button type="button" className="text-button time-rail-reset" onClick={() => timeClock.reset()}>
            Back to the {annual} mean
          </button>
        )}
      </div>
      <div className="time-rail-row">
        <button
          type="button"
          className="icon-button"
          aria-label={playing ? "Pause" : "Play through the months"}
          aria-pressed={playing}
          onClick={() => timeClock.setPlaying(!playing)}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            {playing ? <path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z" /> : <path d="M4 2.2v11.6L13.5 8z" />}
          </svg>
        </button>
        <div className="time-rail-track">
          <input
            type="range"
            className="time-scrub"
            min={0}
            max={last}
            step={1}
            value={index < 0 ? last : index}
            data-rest={index < 0}
            aria-label="Month"
            aria-valuetext={now}
            onChange={(e) => scrub(Number(e.currentTarget.value))}
            // At rest the thumb waits at the latest month. Clicking it there changes nothing in
            // the control, so the click is what picks that month.
            onPointerUp={() => {
              if (timeClock.get().month === null) scrub(last);
            }}
          />
          <div className="time-rail-ticks" aria-hidden="true">
            {all.map((m) => (
              <span
                key={m}
                data-january={m.endsWith("-01") || undefined}
                data-missing={missing.has(m) || undefined}
                data-now={m === month || undefined}
              />
            ))}
          </div>
          <div className="time-rail-years axis-text" aria-hidden="true">
            {all.map((m, i) =>
              // The first year is named only where it has room before the next January.
              (i === 0 && firstHasRoom(all)) || (i > 0 && m.endsWith("-01")) ? (
                <span key={m} style={{ left: `${(i / last) * 100}%` }} data-first={i === 0 || undefined}>
                  {m.slice(0, 4)}
                </span>
              ) : null,
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
