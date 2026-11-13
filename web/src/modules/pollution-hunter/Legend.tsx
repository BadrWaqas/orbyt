import { NO2_HI_UMOL, NO2_LO_UMOL, NO2_YEAR, no2RampGradient, no2RampPosition } from "./no2";

// Three labelled values (PLAN.md 9.6). The scale is square-root, so 100 sits near the middle.
const TICKS_UMOL = [NO2_LO_UMOL, 100, NO2_HI_UMOL];

/** Colour ramp for the NO2 layer with its units and one line saying what it shows. */
export function Legend({ visible }: { visible: boolean }) {
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
    </aside>
  );
}
