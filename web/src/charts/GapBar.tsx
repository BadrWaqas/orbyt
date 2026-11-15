import { formatRatio, ratioText } from "../data/format";
import type { Ratio } from "../data/types";

// PLAN.md 9.6: a log axis from 0.25x to 4x, ticks at 0.5, 1 and 2, a neutral band from 0.8 to
// 1.25, a dot at the ratio and a whisker for the 95% interval. Colour only when the whole
// whisker clears the band, and then always with the verdict's icon and words beside it.
const AXIS_MIN = 0.25;
const AXIS_MAX = 4;
const BAND_LO = 0.8;
const BAND_HI = 1.25;
const TICKS = [0.5, 1, 2];

const span = Math.log(AXIS_MAX / AXIS_MIN);
/** 0 to 100, the place of a ratio on the axis. Values past the ends sit on the ends. */
const at = (r: number) =>
  (Math.log(Math.min(Math.max(r, AXIS_MIN), AXIS_MAX) / AXIS_MIN) / span) * 100;

export function gapColour(r: Ratio): string {
  if (r.lo > BAND_HI) return "var(--gap-higher)";
  if (r.hi < BAND_LO) return "var(--gap-lower)";
  return "var(--gap-consistent)";
}

interface Props {
  ratio: Ratio;
  /** Compact for the leaderboard rows: no ticks, no text. */
  mini?: boolean;
  /** A test site: the gap is shown in grey, since it carries no verdict. */
  neutral?: boolean;
}

export function GapBar({ ratio, mini = false, neutral = false }: Props) {
  const colour = neutral ? "var(--gap-consistent)" : gapColour(ratio);
  const lo = at(ratio.lo);
  const hi = at(ratio.hi);
  const clipped = ratio.lo < AXIS_MIN || ratio.hi > AXIS_MAX;
  const label = `${ratioText(ratio)}. Reported is 1.0x.`;
  return (
    <figure className={mini ? "gap-bar gap-bar-mini" : "gap-bar"} aria-label={label}>
      <div className="gap-track" role="img" aria-label={label}>
        <span
          className="gap-band"
          style={{ left: `${at(BAND_LO)}%`, width: `${at(BAND_HI) - at(BAND_LO)}%` }}
        />
        <span className="gap-whisker" style={{ left: `${lo}%`, width: `${hi - lo}%`, background: colour }} />
        <span className="gap-dot" style={{ left: `${at(ratio.value)}%`, background: colour }} />
        {TICKS.map((t) => (
          <span key={t} className="gap-tick" style={{ left: `${at(t)}%` }} />
        ))}
      </div>
      {!mini && (
        <>
          <div className="gap-ticks" aria-hidden="true">
            {TICKS.map((t) => (
              <span key={t} style={{ left: `${at(t)}%` }}>
                {formatRatio(t)}
              </span>
            ))}
          </div>
          <figcaption className="gap-caption">
            {ratioText(ratio)}
            {clipped && <span className="text-text-3"> The interval runs past the ends of the bar.</span>}
          </figcaption>
        </>
      )}
    </figure>
  );
}
