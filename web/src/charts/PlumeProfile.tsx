import { useMemo, useState } from "react";
import type { PointerEvent } from "react";

import { formatOneDecimal, formatTonnes } from "../data/format";
import type { Observed, PlumeProfileData } from "../data/types";
import { GUTTER_LEFT_PX, GUTTER_RIGHT_PX, useWidth } from "./useWidth";

// PlumeProfile (PLAN.md 9.6 and 9.8): the stacked curve F(t) as dots and the EMG fit as a line,
// a rule at t = 0 labelled "source", and the two things the fit yields: emission and lifetime.

const HEIGHT_PX = 216;
const MARGIN = { top: 26, bottom: 40 };
const DOT_RADIUS_PX = 4; // dots at least 8 px across
const DOT_OUTLINE = { stroke: "var(--panel-solid)", strokeWidth: 1.5 };
// The curve is sampled every 0.1 h, which would put 8 px dots on top of each other at panel
// width. Three samples are averaged into one dot. The fit line keeps every sample.
const SAMPLES_PER_DOT = 3;
const HOUR_TICKS = [-2, 0, 2, 4, 6];

interface Dot {
  t: number;
  flux: number;
  fit: number | null;
}

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function toDots(profile: PlumeProfileData): Dot[] {
  const dots: Dot[] = [];
  for (let i = 0; i < profile.t_h.length; i += SAMPLES_PER_DOT) {
    const at = [...Array(SAMPLES_PER_DOT).keys()]
      .map((k) => i + k)
      .filter((j) => j < profile.t_h.length && profile.flux_mol_s[j] !== null);
    if (at.length === 0) continue;
    const fits = at.map((j) => profile.fit_mol_s[j]).filter((v): v is number => v !== null);
    dots.push({
      t: mean(at.map((j) => profile.t_h[j])),
      flux: mean(at.map((j) => profile.flux_mol_s[j] as number)),
      fit: fits.length ? mean(fits) : null,
    });
  }
  return dots;
}

/** A step from 1, 2, 2.5, 5 (times a power of ten) that gives three or four intervals. */
function niceStep(max: number): number {
  const raw = max / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const nice = fraction > 5 ? 10 : fraction > 2.5 ? 5 : fraction > 2 ? 2.5 : fraction > 1 ? 2 : 1;
  return nice * power;
}

interface Props {
  profile: PlumeProfileData;
  observed: Observed;
  nDays: number;
}

export function PlumeProfileChart({ profile, observed, nDays }: Props) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const dots = useMemo(() => toDots(profile), [profile]);

  const tFirst = profile.t_h[0];
  const tLast = profile.t_h[profile.t_h.length - 1];
  const fitValues = profile.fit_mol_s.filter((v): v is number => v !== null);
  const high = Math.max(...dots.map((d) => d.flux), ...fitValues, 0);
  const low = Math.min(...dots.map((d) => d.flux), ...fitValues, 0);
  const step = niceStep(high);
  const top = Math.ceil(high / step) * step;
  const bottom = low < 0 ? low * 1.4 : 0; // just enough room for the dots below zero

  const plotLeft = GUTTER_LEFT_PX;
  const plotRight = Math.max(width - GUTTER_RIGHT_PX, plotLeft + 1);
  const plotBottom = HEIGHT_PX - MARGIN.bottom;
  const x = (t: number) => plotLeft + ((t - tFirst) / (tLast - tFirst)) * (plotRight - plotLeft);
  const y = (v: number) => plotBottom - ((v - bottom) / (top - bottom)) * (plotBottom - MARGIN.top);

  let fitPath = "";
  let pen = false;
  profile.t_h.forEach((t, i) => {
    const v = profile.fit_mol_s[i];
    if (v === null) {
      pen = false;
      return;
    }
    fitPath += `${pen ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });

  const yTicks: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) yTicks.push(v);
  const decimals = step < 1 ? 1 : 0;

  const onPointer = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = tFirst + ((e.clientX - box.left) / box.width) * (tLast - tFirst);
    let best = 0;
    dots.forEach((d, i) => {
      if (Math.abs(d.t - t) < Math.abs(dots[best].t - t)) best = i;
    });
    setHover(best);
  };
  const hovered = hover === null ? null : dots[hover];

  const summary =
    `NO2 carried downwind against hours of travel, average of ${nDays} days. ` +
    `It jumps at the source and fades with a lifetime of ${formatOneDecimal(profile.fit.tau)} hours. ` +
    `The fitted emission is ${formatTonnes(observed.value)} tonnes of NOx a year.`;

  return (
    <div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] leading-4 text-text-2" aria-hidden="true">
        <li className="flex items-center gap-1.5">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <circle cx="5" cy="5" r="4" className="fill-no2-mark" />
          </svg>
          Average of {nDays} days
        </li>
        <li className="flex items-center gap-1.5">
          <svg width="16" height="10" viewBox="0 0 16 10">
            <line x1="0" x2="16" y1="5" y2="5" className="stroke-no2" strokeWidth="2" />
          </svg>
          Fitted curve
        </li>
      </ul>

      <div ref={ref} className="relative mt-1" style={{ height: HEIGHT_PX }}>
        {width > 0 && (
          <svg width={width} height={HEIGHT_PX} role="img" aria-label={summary} className="block">
            {yTicks.map((v) => (
              <g key={v}>
                <line x1={plotLeft} x2={plotRight} y1={y(v)} y2={y(v)} className="stroke-hairline" />
                <text x={plotLeft - 8} y={y(v)} dy="0.32em" textAnchor="end" className="chart-axis">
                  {v.toFixed(decimals)}
                </text>
              </g>
            ))}
            {HOUR_TICKS.filter((t) => t >= tFirst && t <= tLast).map((t) => (
              <text key={t} x={x(t)} y={plotBottom + 16} textAnchor="middle" className="chart-axis">
                {t}
              </text>
            ))}
            <text x={(plotLeft + plotRight) / 2} y={HEIGHT_PX - 4} textAnchor="middle" className="chart-axis">
              Hours of travel downwind
            </text>

            <line x1={x(0)} x2={x(0)} y1={MARGIN.top - 4} y2={plotBottom} className="stroke-text-3" />
            {!hovered && (
              <text x={x(0)} y={MARGIN.top - 10} textAnchor="middle" className="chart-axis">
                source
              </text>
            )}

            <path d={fitPath} className="fill-none stroke-no2" strokeWidth={2} strokeLinejoin="round" />
            {dots.map((d, i) => (
              <circle
                key={d.t}
                cx={x(d.t)}
                cy={y(d.flux)}
                r={hover === i ? DOT_RADIUS_PX + 1.5 : DOT_RADIUS_PX}
                className="fill-no2-mark"
                style={DOT_OUTLINE}
              />
            ))}

            {/* What the fit yields. The upper right of the plot is clear once the plume has faded. */}
            {!hovered && (
              <g>
                <text x={plotRight} y={MARGIN.top + 12} textAnchor="end" className="chart-axis">
                  Height at the source: emission
                </text>
                <text x={plotRight} y={MARGIN.top + 30} textAnchor="end" className="chart-note">
                  {formatTonnes(observed.value)} t NOx a year
                </text>
                <text x={plotRight} y={MARGIN.top + 52} textAnchor="end" className="chart-axis">
                  How fast it fades: lifetime
                </text>
                <text x={plotRight} y={MARGIN.top + 70} textAnchor="end" className="chart-note">
                  {formatOneDecimal(profile.fit.tau)} hours
                </text>
              </g>
            )}

            {hovered && (
              <line
                x1={x(hovered.t)}
                x2={x(hovered.t)}
                y1={MARGIN.top - 4}
                y2={plotBottom}
                className="stroke-text-3"
                strokeDasharray="2 3"
              />
            )}

            <rect
              x={plotLeft}
              y={0}
              width={plotRight - plotLeft}
              height={plotBottom}
              fill="transparent"
              style={{ touchAction: "pan-y" }}
              onPointerMove={onPointer}
              onPointerDown={onPointer}
              onPointerLeave={() => setHover(null)}
            />
          </svg>
        )}

        {hovered && (
          <p
            className="pointer-events-none absolute top-0 whitespace-nowrap text-[14px] leading-5"
            style={{
              left: Math.min(Math.max(x(hovered.t), plotLeft + 96), plotRight - 96),
              transform: "translateX(-50%)",
            }}
          >
            <span className="axis-text">{formatOneDecimal(hovered.t)} h</span>{" "}
            <span className="text-text">{hovered.flux.toFixed(2)} mol/s</span>
            {hovered.fit !== null && <span className="axis-text"> fit {hovered.fit.toFixed(2)}</span>}
          </p>
        )}
      </div>
    </div>
  );
}

export function PlumeProfileTable({ profile }: { profile: PlumeProfileData }) {
  const dots = useMemo(() => toDots(profile), [profile]);
  return (
    <table className="w-full border-collapse">
      <caption className="sr-only">NO2 carried downwind by hours of travel, measured and fitted</caption>
      <thead>
        <tr>
          <th scope="col" className="axis-text py-1.5 text-left">
            Hours downwind
          </th>
          <th scope="col" className="axis-text py-1.5 text-right">
            Measured, mol/s
          </th>
          <th scope="col" className="axis-text w-[30%] py-1.5 text-right">
            Fit, mol/s
          </th>
        </tr>
      </thead>
      <tbody>
        {dots.map((d) => (
          <tr key={d.t} className="border-t border-hairline">
            <td className="axis-text py-1.5">{formatOneDecimal(d.t)}</td>
            <td className="py-1.5 text-right text-[14px] leading-5 tabular-nums text-text">{d.flux.toFixed(2)}</td>
            <td className="axis-text py-1.5 text-right">{d.fit === null ? "" : d.fit.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
