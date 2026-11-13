import { lazy, Suspense, useCallback, useState } from "react";

import { Stars } from "../globe/Stars";
import { Legend } from "../modules/pollution-hunter/Legend";

// MapLibre is the heaviest dependency. Loading it as its own chunk lets the text paint first.
const Globe = lazy(() => import("../globe/Globe").then((m) => ({ default: m.Globe })));

export function App() {
  const [no2Visible, setNo2Visible] = useState(false);
  const showLegend = useCallback(() => setNo2Visible(true), []);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-void text-text">
      <Stars />
      <Suspense fallback={null}>
        <Globe onNo2Visible={showLegend} />
      </Suspense>

      <header
        className="pointer-events-none absolute left-[var(--margin-outer)] top-[max(var(--margin-outer),env(safe-area-inset-top))]"
      >
        <span className="wordmark text-[18px] leading-6">Orbyt Earth</span>
      </header>

      <Legend visible={no2Visible} />

      <section
        className="pointer-events-none absolute inset-x-0 bottom-[max(48px,env(safe-area-inset-bottom))] px-[var(--margin-outer)] text-center"
      >
        <h1 className="text-[24px] leading-[30px] md:text-[36px] md:leading-[42px]">
          <span className="voice-record block">Reported on paper.</span>
          <span className="voice-instrument block">Measured from orbit.</span>
        </h1>
        <p className="mt-3 text-[14px] leading-5 text-text-2">
          Fact-checking the world from space.
        </p>
      </section>
    </main>
  );
}
