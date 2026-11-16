import { useSyncExternalStore } from "react";

// One clock for the NO2 layer's time (PLAN.md 9.6, TimeRail). The rail's controls set it, the
// globe draws the month it names, and the legend prints that month.
//
// At rest the globe shows the annual mean, the layer the verdicts are about. Scrubbing or
// playing the rail moves it through the months, from July 2022 to the latest one.

interface TimeState {
  /** The month on show as "2024-06", or null for the annual mean. */
  month: string | null;
  playing: boolean;
}

let state: TimeState = { month: null, playing: false };
const listeners = new Set<() => void>();

function update(next: Partial<TimeState>) {
  const merged = { ...state, ...next };
  if (merged.month === state.month && merged.playing === state.playing) return;
  state = merged;
  for (const listener of listeners) listener();
}

export const timeClock = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: (): TimeState => state,
  /** Show a month and stop there. The rail's scrubber, the arrow keys and a shared link. */
  scrubTo(month: string) {
    update({ month, playing: false });
  },
  /** Move on to a month while playing. */
  advanceTo(month: string) {
    update({ month });
  },
  setPlaying(playing: boolean) {
    update({ playing });
  },
  /** Back to the annual mean. */
  reset() {
    update({ month: null, playing: false });
  },
};

export function useTimeClock(): TimeState {
  return useSyncExternalStore(timeClock.subscribe, timeClock.get);
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "2024-06" as "June 2024". */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-");
  return `${MONTH_NAMES[Number(number) - 1]} ${year}`;
}
