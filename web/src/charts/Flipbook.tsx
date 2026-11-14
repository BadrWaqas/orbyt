import { useEffect, useMemo, useState } from "react";

import { compassWord, formatDay, formatOneDecimal } from "../data/format";
import type { DayRow, FlipbookSheet } from "../data/types";
import { plumeClock, plumeFrames, usePlumeClock } from "../modules/pollution-hunter/plumeClock";
import { RampKey } from "./RampKey";

// Flipbook (PLAN.md 9.6): clear-day frames from a sprite sheet with the date and a wind arrow.
// Play, pause, scrub. Frames are maps with north up, so the plume swings with the wind from day
// to day. The detected or not mark of 9.6 waits for the single-day test to be validated (M4).

const SCALE_BAR_KM = 50;

interface Props {
  src: string;
  sheet: FlipbookSheet;
  days: DayRow[];
  year: string;
}

type Load = "loading" | "ready" | "error";

export function Flipbook({ src, sheet, days, year }: Props) {
  const frames = useMemo(() => plumeFrames(days), [days]);
  // The day on show is shared with the plume drawn on the globe, so both move together.
  const { index, playing } = usePlumeClock();
  const [load, setLoad] = useState<Load>("loading");
  const [attempt, setAttempt] = useState(0);

  // The sheet is one image. Fetch it before the first frame is shown, so playback never blanks.
  useEffect(() => {
    setLoad("loading");
    const image = new Image();
    image.onload = () => setLoad("ready");
    image.onerror = () => setLoad("error");
    image.src = src;
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [src, attempt]);

  // The clock runs while the frames are on screen.
  useEffect(() => {
    if (load !== "ready" || frames.length === 0) return;
    return plumeClock.attach(frames.length);
  }, [load, frames.length]);

  if (frames.length === 0) return null;
  const day = frames[Math.min(index, frames.length - 1)];
  const position = day.frame as number;
  const col = position % sheet.columns;
  const row = Math.floor(position / sheet.columns);
  const percent = (i: number, n: number) => (n > 1 ? (i / (n - 1)) * 100 : 0);
  const blowsTo = (day.wind_dir_deg + 180) % 360;
  const widthKm = sheet.half_km * 2;

  return (
    <figure>
      <div
        className="relative aspect-square w-full overflow-hidden rounded-[2px] bg-raised"
        role="img"
        aria-label={`NO2 above background around the source on ${formatDay(day.date)}, north up. Wind ${formatOneDecimal(day.wind_ms)} metres per second from the ${compassWord(day.wind_dir_deg)}.`}
      >
        {load === "ready" && (
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `url(${src})`,
              backgroundSize: `${sheet.columns * 100}% ${sheet.rows * 100}%`,
              backgroundPosition: `${percent(col, sheet.columns)}% ${percent(row, sheet.rows)}%`,
            }}
          />
        )}
        {load === "loading" && (
          <div className="absolute inset-0 grid place-items-center" role="status" aria-label="Loading the frames">
            <div className="skeleton-line w-1/3 !bg-hairline" />
          </div>
        )}
        {load === "error" && (
          <p className="absolute inset-0 grid place-items-center px-6 text-center text-[14px] leading-5 text-text-2" role="alert">
            <span>
              Could not load the frames.{" "}
              <button
                type="button"
                className="cursor-pointer underline underline-offset-4"
                onClick={() => setAttempt((n) => n + 1)}
              >
                Try again
              </button>
            </span>
          </p>
        )}

        {load === "ready" && (
          <>
            {/* The source sits at the centre of every frame. */}
            <svg
              className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
              width="36"
              height="36"
              viewBox="-18 -18 36 36"
              aria-hidden="true"
            >
              <g className="stroke-text" strokeWidth={1.5} strokeLinecap="round" opacity={0.9}>
                <line x1={-15} x2={-9} y1={0} y2={0} />
                <line x1={9} x2={15} y1={0} y2={0} />
                <line x1={0} x2={0} y1={-15} y2={-9} />
                <line x1={0} x2={0} y1={9} y2={15} />
              </g>
            </svg>

            <div className="flip-chip absolute left-2 top-2" aria-hidden="true">
              <p className="text-[14px] leading-5 text-text">{formatDay(day.date)}</p>
              <p className="axis-text !text-text-2">
                Wind {formatOneDecimal(day.wind_ms)} m/s from the {compassWord(day.wind_dir_deg)}
              </p>
            </div>

            {/* Where the wind blows to, on a small compass. North is up, as in the frame. */}
            <svg className="absolute right-2 top-2" width="48" height="48" viewBox="-24 -24 48 48" aria-hidden="true">
              <circle r={22} className="fill-[rgba(4,7,11,0.6)] stroke-hairline" />
              <text y={-11} textAnchor="middle" className="chart-axis">
                N
              </text>
              <g transform={`rotate(${blowsTo})`} className="fill-none stroke-text" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
                <path d="M0,9V-7M-4.5,-2.5L0,-7.5L4.5,-2.5" />
              </g>
            </svg>

            {/* Scale bar. Its width is a share of the frame, which spans `widthKm`. */}
            <div
              className="absolute bottom-2 left-2"
              style={{ width: `${(SCALE_BAR_KM / widthKm) * 100}%` }}
              aria-hidden="true"
            >
              <div className="h-1.5 border-x border-b border-text-2" />
              <p className="axis-text flip-shadow mt-0.5 !text-text-2">{SCALE_BAR_KM} km</p>
            </div>
          </>
        )}
      </div>

      <div className="mt-1 flex items-center gap-1">
        <button
          type="button"
          className="icon-button -ml-2.5"
          aria-label={playing ? "Pause" : "Play"}
          disabled={load !== "ready"}
          onClick={() => plumeClock.setPlaying(!playing)}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="fill-current">
            {playing ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="M5 3l8 5l-8 5z" />}
          </svg>
        </button>
        <input
          type="range"
          className="flip-scrub min-w-0 flex-1"
          min={0}
          max={frames.length - 1}
          step={1}
          value={index}
          disabled={load !== "ready"}
          aria-label="Day"
          aria-valuetext={formatDay(day.date)}
          onChange={(e) => plumeClock.scrubTo(Number(e.target.value))}
        />
        <p className="axis-text w-[72px] text-right">
          {index + 1} of {frames.length}
        </p>
      </div>

      <RampKey fullScale={sheet.full_scale_umol_m2} clipped />
      <figcaption className="mt-2 text-[12px] leading-4 text-text-3">
        One frame for each clear day in {year}, north up, {widthKm} km across, with the source at the centre. The
        arrow shows where the wind was blowing.
      </figcaption>
    </figure>
  );
}
