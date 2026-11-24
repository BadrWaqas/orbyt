import { isHidden, onVisibilityChange } from "../../app/visibility";
import type { No2Layer } from "./no2Layer";
import { timeClock } from "./timeClock";

// Makes the globe follow the time clock (PLAN.md 9.6, TimeRail, and M6.3).
//
// A change of month cross-fades the NO2 layer to that month. While the clock is playing, the
// next month's tiles are loaded unseen during each cross-fade, and the clock moves on once the
// month on show has settled: 2 months a second where the network keeps up, slower where it
// does not, and never a month that pops in half loaded.

const CROSS_FADE_MS = 400; // PLAN.md 9.7: a change of time is a 400 ms cross-fade
const STEP_MS = 500; // PLAN.md 9.6: the play button advances 2 months a second
const SCRUB_FADE_MS = 180; // dragging the scrubber changes months faster than that, so it is brisker

/** Start following the clock. `months` are the months the layer has, oldest first. */
export function followTimeClock(no2: No2Layer, months: string[], reducedMotion: boolean): () => void {
  let stopped = false;
  let timer = 0;
  let shown: string | null = null; // the month last asked of the layer, null for the annual mean
  let wasPlaying = false;

  /** The month after `month`, round again from the last one. From the annual mean, the first. */
  const after = (month: string | null) => months[(month ? months.indexOf(month) + 1 : 0) % months.length];

  /** Move on from `month` once `waitMs` have passed, if the clock is still playing it. */
  const stepFrom = (month: string | null, waitMs: number) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      const now = timeClock.get();
      // A hidden tab does not move on. The watcher below picks the player up again.
      if (!stopped && !isHidden() && now.playing && now.month === month) timeClock.advanceTo(after(month));
    }, waitMs);
  };

  const stopWatching = onVisibilityChange((hidden) => {
    if (hidden) {
      window.clearTimeout(timer);
      return;
    }
    const { month, playing } = timeClock.get();
    if (!stopped && playing && month === shown) stepFrom(month, STEP_MS);
  });

  const follow = () => {
    const { month, playing } = timeClock.get();
    const started = !wasPlaying && playing;
    wasPlaying = playing;
    if (!playing) {
      window.clearTimeout(timer);
      no2.preload(null);
    }

    if (month !== shown) {
      shown = month;
      const asked = performance.now();
      const fadeMs = reducedMotion ? 0 : playing ? CROSS_FADE_MS : SCRUB_FADE_MS;
      const taken = no2.showPeriod(month, fadeMs);
      if (playing) {
        no2.preload(after(month));
        void taken.then((done) => {
          if (done) stepFrom(month, Math.max(0, STEP_MS - (performance.now() - asked)));
        });
      }
    } else if (started) {
      // Play was pressed on a month that is already on show. From the annual mean, the first
      // month follows at once.
      no2.preload(after(month));
      stepFrom(month, month === null ? 0 : STEP_MS);
    }
  };

  const unsubscribe = timeClock.subscribe(follow);
  follow(); // a shared link can open on a month

  return () => {
    stopped = true;
    window.clearTimeout(timer);
    stopWatching();
    unsubscribe();
  };
}
