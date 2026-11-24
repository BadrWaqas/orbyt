import { useSyncExternalStore } from "react";

import { isHidden, onVisibilityChange } from "../../app/visibility";
import type { DayRow } from "../../data/types";

// One clock for the daily plume frames of the open facility. The flipbook in the panel and the
// plume drawn on the globe both read it, so they always show the same day, and the flipbook's
// play, pause and scrub controls move both.

export const PLUME_FRAMES_PER_SECOND = 6;

interface PlumeClockState {
  /** Position in the list of frames, see `plumeFrames`. */
  index: number;
  playing: boolean;
}

// It plays by default, unless the visitor prefers stillness.
let state: PlumeClockState = {
  index: 0,
  playing: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
};
const listeners = new Set<() => void>();
let frameCount = 0;
let viewers = 0;
let timer = 0;

function emit() {
  for (const listener of listeners) listener();
}

/** The clock only ticks while something on screen shows the frames, and the tab is on screen. */
function syncTimer() {
  const run = viewers > 0 && state.playing && frameCount > 1 && !isHidden();
  if (run && !timer) {
    timer = window.setInterval(() => {
      state = { ...state, index: (state.index + 1) % frameCount };
      emit();
    }, 1000 / PLUME_FRAMES_PER_SECOND);
  } else if (!run && timer) {
    window.clearInterval(timer);
    timer = 0;
  }
}

// Hiding the tab stops the ticks and showing it starts them again, where they were.
onVisibilityChange(syncTimer);

function update(next: Partial<PlumeClockState>) {
  state = { ...state, ...next };
  syncTimer();
  emit();
}

export const plumeClock = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: (): PlumeClockState => state,
  /** Call while a view of `count` frames is on screen. Returns the function that ends it. */
  attach(count: number): () => void {
    viewers += 1;
    frameCount = count;
    if (state.index >= count) state = { ...state, index: 0 };
    syncTimer();
    return () => {
      viewers -= 1;
      syncTimer();
    };
  },
  /** Scrubbing to a day stops the playback there. */
  scrubTo(index: number) {
    update({ index, playing: false });
  },
  setPlaying(playing: boolean) {
    update({ playing });
  },
  /** Back to the first frame, for a newly opened facility. */
  rewind() {
    update({ index: 0 });
  },
};

export function usePlumeClock(): PlumeClockState {
  return useSyncExternalStore(plumeClock.subscribe, plumeClock.get);
}

/** The days that have a frame, in the order the frames sit in the sheet. */
export function plumeFrames(days: DayRow[]): DayRow[] {
  return days.filter((d) => d.frame !== null).sort((a, b) => (a.frame as number) - (b.frame as number));
}
