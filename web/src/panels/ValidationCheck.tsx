import { formatOneDecimal, formatTonnes } from "../data/format";
import type { Detection, ValidationDetail } from "../data/types";

/** Plain words for the quality gates (METHODS.md 4). */
const GATE_LABEL: Record<string, string> = {
  too_few_days: "too few clear days",
  poor_fit: "the curve does not fit well",
  source_offset: "the plume does not start at the plant",
  lifetime_out_of_range: "the plume lifetime is not physical",
  low_signal_to_noise: "the signal is too noisy",
};

/** "Below reliable detection", for footprints smaller than the method measures reliably. */
export function DetectionNote({ detection }: { detection: Detection }) {
  if (detection.reliable) return null;
  return (
    <div className="mt-4 rounded-[2px] border border-dashed border-hairline px-3 py-2">
      <p className="label">Below reliable detection</p>
      <p className="mt-1 text-[12px] leading-4 text-text-3">
        About {formatTonnes(detection.footprint_t)} t of NO<sub>x</sub> a year within{" "}
        {detection.footprint_km} km. In our check against US stack monitors, almost no estimate under{" "}
        {formatTonnes(detection.min_reliable_t)} t passed the quality checks, so a satellite number here is
        unlikely and would be uncertain.
      </p>
    </div>
  );
}

/** A US plant's satellite estimates set against its stack monitors, year by year. */
export function ValidationCheck({ validation }: { validation: ValidationDetail }) {
  return (
    <section className="mt-5 border-t border-hairline pt-2">
      <h3 className="label">Check against the stack monitors</h3>
      <p className="mt-2 text-[14px] leading-5 text-text-2">
        This US power plant is one of the sites we use to test the method. Its stacks measure NO
        <sub>x</sub> every hour, so the satellite estimate can be compared with a measurement.
      </p>
      <table className="mt-2 w-full border-collapse">
        <caption className="sr-only">Satellite estimate against the stack monitors, by year</caption>
        <thead>
          <tr>
            <th scope="col" className="axis-text py-1.5 text-left">
              Year
            </th>
            <th scope="col" className="axis-text py-1.5 text-right">
              Satellite, t
            </th>
            <th scope="col" className="axis-text py-1.5 text-right">
              Monitors at pass, t
            </th>
            <th scope="col" className="axis-text py-1.5 text-right">
              Ratio
            </th>
          </tr>
        </thead>
        <tbody>
          {validation.years.map((y) => (
            <tr key={y.year} className="border-t border-hairline align-top">
              <td className="axis-text py-1.5">{y.year}</td>
              <td className="py-1.5 text-right">
                {y.passed && y.estimate_t !== null ? (
                  <>
                    <span className="instrument-note">{formatTonnes(y.estimate_t)}</span>
                    {y.lo !== null && y.hi !== null && (
                      <span className="axis-text block">
                        {formatTonnes(y.lo)} to {formatTonnes(y.hi)}
                      </span>
                    )}
                  </>
                ) : (
                  <span className="axis-text">Inconclusive</span>
                )}
              </td>
              <td className="record-source py-1.5 text-right">
                {y.monitors_at_pass_t !== null ? formatTonnes(y.monitors_at_pass_t) : ""}
              </td>
              <td className="axis-text py-1.5 text-right">
                {y.ratio_at_pass !== null ? `${formatOneDecimal(y.ratio_at_pass)}×` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {validation.years
        .filter((y) => !y.passed)
        .map((y) => (
          <p key={y.year} className="mt-2 text-[12px] leading-4 text-text-3">
            {y.year}: no number, because{" "}
            {y.gates_failed.map((g) => GATE_LABEL[g] ?? g).join(", ") || "no plume was found"}.
          </p>
        ))}
      <p className="mt-3 text-[12px] leading-4 text-text-3">
        Monitors at pass is the stack NO<sub>x</sub> in the three hours before each satellite pass, on the
        same days, as tonnes a year.
        {validation.unmonitored_t >= 100 &&
          ` Other sources within 20 km that the monitors do not cover add about ${formatTonnes(
            validation.unmonitored_t,
          )} t a year (EPA National Emissions Inventory 2023).`}{" "}
        Across the test sites that pass every check, the satellite estimates scatter around the monitors by
        about {Math.round(validation.u_sys * 100)}% beyond the interval shown.
      </p>
    </section>
  );
}
