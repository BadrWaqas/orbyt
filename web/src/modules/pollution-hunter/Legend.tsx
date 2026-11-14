import { formatDay } from "../../data/format";
import type { DayRow } from "../../data/types";
import { NO2_HI_UMOL, NO2_LO_UMOL, NO2_YEAR, no2RampGradient, no2RampPosition } from "./no2";
import { usePlumeClock } from "./plumeClock";

// Three labelled values (PLAN.md 9.6). The scale is square-root, so 100 sits near the middle.
const TICKS_UMOL = [NO2_LO_UMOL, 100, NO2_HI_UMOL];

interface SiteDays {
  /** The days with a frame, in playing order. */
  frames: DayRow[];
  /** The value the brightest colour of a frame stands for, micromol/m2 above background. */
  fullScale: number;
}

interface Props {
  visible: boolean;
  /** Set while the open facility's daily plume is drawn on the globe. */
  site?: SiteDays | null;
}

/** Colour ramp for the NO2 layer with its units and one line saying what it shows. */
export function Legend({ visible, site = null }: Props) {
  return (
    <aside
      aria-label="Map legend"
      aria-hidden={!visible}
      className={`glass pointer-events-none absolute right-[var(--margin-outer)] top-[max(var(--margin-outer),env(safe-area-inset-top))] w-[188px] p-3 motion-safe:transition-opacity motion-safe:duration-700 lg:bottom-[var(--margin-outer)] lg:left-[var(--margin-outer)] lg:right-auto lg:top-auto lg:w-[272px] lg:p-4 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <p className="text-[14px] leading-5 text-text">
        Mean NO<sub>2</sub> in the lower atmosphere, {NO2_YEAR}
      </p>
      <p className="axis-text mt-2" aria-hidden="true">
        µmol/m²
      </p>
      <div
        role="img"
        aria-label={`Colour scale from ${NO2_LO_UMOL} to ${NO2_HI_UMOL} micromoles of NO2 per square metre. Brighter means more.`}
        className="legend-ramp mt-1"
        style={{ backgroundImage: no2RampGradient() }}
      />
      <div className="axis-text relative mt-1 h-5" aria-hidden="true">
        {TICKS_UMOL.map((umol, i) => {
          const last = i === TICKS_UMOL.length - 1;
          const left = `${no2RampPosition(umol) * 100}%`;
          const shift = i === 0 ? "" : last ? "-translate-x-full" : "-translate-x-1/2";
          return (
            <span key={umol} className={`absolute top-0 whitespace-nowrap ${shift}`} style={{ left }}>
              <span
                className={`block h-1 w-px bg-text-3 ${i === 0 ? "" : last ? "ml-auto" : "mx-auto"}`}
              />
              {umol}
            </span>
          );
        })}
      </div>
      {site && <SiteDay site={site} />}
    </aside>
  );
}

/** Names the day whose plume is on the globe. It changes with the plume clock. */
function SiteDay({ site }: { site: SiteDays }) {
  const { index } = usePlumeClock();
  const day = site.frames[Math.min(index, site.frames.length - 1)];
  return (
    // The date changes several times a second, so it is kept from screen readers. The flipbook
    // in the panel says the same thing in a form they can step through.
    <div className="mt-3 border-t border-hairline pt-3" aria-hidden="true">
      <p className="text-[12px] leading-4 text-text-2">Around the open facility, one clear day at a time</p>
      <p className="mt-1 text-[14px] leading-5 text-no2 [font-variant-numeric:tabular-nums]">{formatDay(day.date)}</p>
      <p className="mt-1 hidden text-[12px] leading-4 text-text-3 lg:block">
        NO<sub>2</sub> above background. Brightest at {site.fullScale} µmol/m² or more.
      </p>
    </div>
  );
}
