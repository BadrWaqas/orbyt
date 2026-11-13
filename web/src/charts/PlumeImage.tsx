import { useId } from "react";

import type { PlumeProfileData, StackGeometry } from "../data/types";
import { RampKey } from "./RampKey";
import { GUTTER_LEFT_PX, GUTTER_RIGHT_PX, useWidth } from "./useWidth";

// The wind-aligned plume image (PLAN.md 9.6): every clear day turned so the wind blows to the
// right, then averaged. It shares its time axis and gutters with the curve on the next tab.

const AXIS_PX = 40; // tick labels and the axis title under the image
const HOUR_TICKS = [-2, 0, 2, 4, 6];
const CROSSWIND_TICKS_KM = [-50, 0, 50];

interface Props {
  src: string;
  stack: StackGeometry;
  /** Travel times the fan half-widths refer to. */
  times: PlumeProfileData["t_h"];
  year: string;
}

export function PlumeImage({ src, stack, times, year }: Props) {
  const [ref, width] = useWidth();
  const clipId = useId();

  const plotLeft = GUTTER_LEFT_PX;
  const plotRight = Math.max(width - GUTTER_RIGHT_PX, plotLeft + 1);
  const plotWidth = plotRight - plotLeft;
  const plotHeight = Math.round((plotWidth * stack.height) / stack.width);
  const [tFirst, tLast] = stack.t_h;
  const [yLow, yHigh] = stack.crosswind_km;
  const x = (t: number) => plotLeft + ((t - tFirst) / (tLast - tFirst)) * plotWidth;
  const y = (km: number) => ((yHigh - km) / (yHigh - yLow)) * plotHeight;

  const edge = (side: 1 | -1) =>
    times
      .map((t, i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(side * stack.fan_half_width_km[i]).toFixed(1)}`)
      .join("");

  const alt =
    `Average NO2 above background on ${stack.n_days} clear days in ${year}, with the wind blowing to the right. ` +
    "A bright core at the source fades downwind over a few hours.";

  return (
    <figure>
      <div ref={ref} style={{ height: width > 0 ? plotHeight + AXIS_PX : undefined }}>
        {width > 0 && (
          <svg width={width} height={plotHeight + AXIS_PX} role="img" aria-label={alt} className="block">
            <defs>
              <clipPath id={clipId}>
                <rect x={plotLeft} y={0} width={plotWidth} height={plotHeight} rx={2} />
              </clipPath>
            </defs>
            <rect x={plotLeft} y={0} width={plotWidth} height={plotHeight} rx={2} className="fill-raised" />
            <image
              href={src}
              x={plotLeft}
              y={0}
              width={plotWidth}
              height={plotHeight}
              preserveAspectRatio="none"
              clipPath={`url(#${clipId})`}
            />

            {/* The band the estimate adds up. */}
            <g clipPath={`url(#${clipId})`} className="fill-none stroke-text-2" strokeDasharray="3 4" opacity={0.55}>
              <path d={edge(1)} />
              <path d={edge(-1)} />
            </g>

            {/* The source: four ticks around it, so the bright core stays visible. */}
            <g className="stroke-text" strokeWidth={1.5} strokeLinecap="round">
              <line x1={x(0) - 14} x2={x(0) - 8} y1={y(0)} y2={y(0)} />
              <line x1={x(0)} x2={x(0)} y1={y(0) - 14} y2={y(0) - 8} />
              <line x1={x(0)} x2={x(0)} y1={y(0) + 8} y2={y(0) + 14} />
            </g>
            <text x={x(0)} y={y(0) - 22} textAnchor="middle" className="chart-axis">
              source
            </text>

            {/* Wind direction, top left of the image. */}
            <g transform={`translate(${plotLeft + 10}, 16)`}>
              <text x={0} y={0} dy="0.32em" className="chart-axis">
                wind
              </text>
              <path
                d="M30,0H52M47,-4l5,4l-5,4"
                className="fill-none stroke-text-2"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>

            {CROSSWIND_TICKS_KM.map((km) => (
              <text key={km} x={plotLeft - 8} y={y(km)} dy="0.32em" textAnchor="end" className="chart-axis">
                {km === 0 ? "0" : `${Math.abs(km)} km`}
              </text>
            ))}
            {HOUR_TICKS.filter((t) => t >= tFirst && t <= tLast).map((t) => (
              <text key={t} x={x(t)} y={plotHeight + 16} textAnchor="middle" className="chart-axis">
                {t}
              </text>
            ))}
            <text x={(plotLeft + plotRight) / 2} y={plotHeight + AXIS_PX - 4} textAnchor="middle" className="chart-axis">
              Hours of travel downwind
            </text>
          </svg>
        )}
      </div>
      <div className="mt-2" style={{ paddingLeft: GUTTER_LEFT_PX }}>
        <RampKey fullScale={stack.full_scale_umol_m2} clipped />
      </div>
      <figcaption className="mt-2 text-[12px] leading-4 text-text-3">
        Average of {stack.n_days} clear days in {year}. Each day is turned so the wind blows to the right, and
        distance is counted as hours of travel. The estimate adds up what lies between the dashed lines.
      </figcaption>
    </figure>
  );
}
