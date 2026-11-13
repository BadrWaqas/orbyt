import { useState } from "react";
import type { PointerEvent } from "react";

import { BASIS_LABEL, formatTonnes } from "../data/format";
import type { ReportedPoint } from "../data/types";
import { GUTTER_LEFT_PX, useWidth } from "./useWidth";

// Reported annual values as steps in the ledger colour (PLAN.md 9.6, EstimateSeries, and 9.8).
// One y axis that starts at zero, 2 px line, hover values, and a table view of the same data.

const HEIGHT_PX = 176;
const MARGIN = { top: 26, right: 8, bottom: 24 };
const DOT_RADIUS_PX = 4; // dots at least 8 px across
const DOT_OUTLINE = { stroke: "var(--panel-solid)", strokeWidth: 2 }; // lifts the dot off the line

/** The largest step from 1, 2, 2.5, 5 (times a power of ten) that still gives three intervals. */
function niceStep(max: number): number {
  const raw = max / 3;
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const nice = fraction >= 5 ? 5 : fraction >= 2.5 ? 2.5 : fraction >= 2 ? 2 : 1;
  return nice * power;
}

/** Years to label: every fifth year, plus both ends when they are not crowded by a neighbour. */
function yearTicks(first: number, last: number): number[] {
  const ticks: number[] = [];
  for (let y = Math.ceil(first / 5) * 5; y <= last; y += 5) ticks.push(y);
  if (ticks.every((y) => Math.abs(y - first) >= 2)) ticks.unshift(first);
  if (ticks.every((y) => Math.abs(y - last) >= 2)) ticks.push(last);
  return ticks;
}

interface ChartProps {
  series: ReportedPoint[];
  /** The register's first and last reporting year, so every facility shares one time axis. */
  firstYear: number;
  lastYear: number;
  /** The year the panel's large number refers to. */
  highlightYear: number;
}

export function ReportedSeriesChart({ series, firstYear, lastYear, highlightYear }: ChartProps) {
  const [ref, width] = useWidth();
  const [hoverYear, setHoverYear] = useState<number | null>(null);

  const first = Math.min(firstYear, series[0]?.year ?? firstYear);
  const last = Math.max(lastYear, series[series.length - 1]?.year ?? lastYear);
  const max = Math.max(...series.map((p) => p.value), 1);
  const step = niceStep(max);
  const top = Math.ceil(max / step) * step;

  const plotLeft = GUTTER_LEFT_PX;
  const plotRight = Math.max(width - MARGIN.right, plotLeft + 1);
  const plotBottom = HEIGHT_PX - MARGIN.bottom;
  const yearWidth = (plotRight - plotLeft) / (last - first + 1);
  const x = (year: number) => plotLeft + (year - first + 0.5) * yearWidth;
  const y = (value: number) => plotBottom - (value / top) * (plotBottom - MARGIN.top);

  // One flat step per year. Consecutive years join with a riser, a missing year breaks the line.
  let path = "";
  series.forEach((p, i) => {
    const joined = i > 0 && series[i - 1].year === p.year - 1;
    const left = (x(p.year) - yearWidth / 2).toFixed(1);
    const right = (x(p.year) + yearWidth / 2).toFixed(1);
    path += joined ? `V${y(p.value).toFixed(1)}H${right}` : `M${left},${y(p.value).toFixed(1)}H${right}`;
  });

  const highlight = series.find((p) => p.year === highlightYear) ?? series[series.length - 1];
  const hovered = hoverYear === null ? null : (series.find((p) => p.year === hoverYear) ?? null);

  const onPointer = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const year = first + Math.floor((e.clientX - box.left) / yearWidth);
    // Snap to the nearest year that has a value, so the readout never lands on a gap.
    let nearest: ReportedPoint | null = null;
    for (const p of series) {
      if (!nearest || Math.abs(p.year - year) < Math.abs(nearest.year - year)) nearest = p;
    }
    setHoverYear(nearest ? nearest.year : null);
  };

  const yTicks: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) yTicks.push(v);
  const summary = highlight
    ? `Reported NOx by year, ${series[0].year} to ${series[series.length - 1].year}. ${formatTonnes(highlight.value)} tonnes in ${highlight.year}.`
    : "Reported NOx by year.";

  return (
    <div ref={ref} className="relative" style={{ height: HEIGHT_PX }}>
      {width > 0 && (
        <svg width={width} height={HEIGHT_PX} role="img" aria-label={summary} className="block">
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={plotLeft} x2={plotRight} y1={y(v)} y2={y(v)} className="stroke-hairline" />
              <text x={plotLeft - 8} y={y(v)} dy="0.32em" textAnchor="end" className="chart-axis">
                {formatTonnes(v)}
              </text>
            </g>
          ))}
          {yearTicks(first, last).map((year) => (
            <text key={year} x={x(year)} y={HEIGHT_PX - 6} textAnchor="middle" className="chart-axis">
              {year}
            </text>
          ))}

          <path
            d={path}
            className="fill-none stroke-ledger"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {hovered ? (
            <g>
              <line
                x1={x(hovered.year)}
                x2={x(hovered.year)}
                y1={MARGIN.top - 4}
                y2={plotBottom}
                className="stroke-text-3"
                strokeDasharray="2 3"
              />
              <circle
                cx={x(hovered.year)}
                cy={y(hovered.value)}
                r={DOT_RADIUS_PX}
                className="fill-ledger"
                style={DOT_OUTLINE}
              />
            </g>
          ) : (
            highlight && (
              <g>
                <circle
                  cx={x(highlight.year)}
                  cy={y(highlight.value)}
                  r={DOT_RADIUS_PX}
                  className="fill-ledger"
                  style={DOT_OUTLINE}
                />
                <text
                  x={Math.min(x(highlight.year) + yearWidth / 2, plotRight)}
                  y={y(highlight.value) - 10}
                  textAnchor="end"
                  className="chart-value"
                >
                  {formatTonnes(highlight.value)} t
                </text>
              </g>
            )
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
            onPointerLeave={() => setHoverYear(null)}
          />
        </svg>
      )}

      {hovered && (
        <p
          className="pointer-events-none absolute top-0 whitespace-nowrap"
          style={{
            left: Math.min(Math.max(x(hovered.year), plotLeft + 48), plotRight - 48),
            transform: "translateX(-50%)",
          }}
        >
          <span className="axis-text">{hovered.year}</span>{" "}
          <span className="record-source">{formatTonnes(hovered.value)} t</span>
        </p>
      )}
    </div>
  );
}

export function ReportedSeriesTable({ series }: { series: ReportedPoint[] }) {
  return (
    <table className="w-full border-collapse">
      <caption className="sr-only">Reported NOx by year, newest first</caption>
      <thead>
        <tr>
          <th scope="col" className="axis-text py-1.5 text-left">
            Year
          </th>
          <th scope="col" className="axis-text py-1.5 text-right">
            Reported, tonnes
          </th>
          <th scope="col" className="axis-text w-[38%] py-1.5 text-right">
            Basis
          </th>
        </tr>
      </thead>
      <tbody>
        {[...series].reverse().map((p) => (
          <tr key={p.year} className="border-t border-hairline">
            <td className="axis-text py-1.5">{p.year}</td>
            <td className="record-source py-1.5 text-right">{formatTonnes(p.value)}</td>
            <td className="axis-text py-1.5 text-right">{BASIS_LABEL[p.basis]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
