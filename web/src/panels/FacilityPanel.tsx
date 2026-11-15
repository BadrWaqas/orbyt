import { useEffect, useRef, useState } from "react";

import { ReportedSeriesChart, ReportedSeriesTable } from "../charts/ReportedSeries";
import { useFindingDetail } from "../data/findings";
import { BASIS_LABEL, countryName, formatTonnes } from "../data/format";
import type { Finding } from "../data/types";
import { NO2_ATTRIBUTION } from "../modules/pollution-hunter/no2";
import { Evidence } from "./Evidence";
import { ClusterNote, DetectionNote, ValidationCheck } from "./ValidationCheck";
import { VerdictBlock } from "./VerdictBlock";

const EXIT_MS = 240; // PLAN.md 9.7: the panel slides and fades in 240 ms
const REGISTER_FIRST_YEAR = 2007; // the EEA register covers reporting years from 2007 on
const MONITORS_FIRST_YEAR = 2023; // the US validation covers 2023 and 2024
const REGISTER_URL =
  "https://www.eea.europa.eu/en/datahub/datahubitem-view/9405f714-8015-4b5b-a63c-280b82861b3d";
const CAMPD_URL = "https://campd.epa.gov/";

interface Props {
  /** The facility to show. Null closes the panel. */
  finding: Finding | null;
  /** The latest reporting year in the dataset, the right end of the time axis. */
  lastYear: number;
  onClose: () => void;
}

/**
 * The VerdictPanel (PLAN.md 9.6): the number pair, the gap bar with the verdict and grade, the
 * evidence tabs where a satellite estimate exists, the reported series and the sources.
 */
export function FacilityPanel({ finding, lastYear, onClose }: Props) {
  // Keep the last facility on screen while the panel slides out.
  const [shown, setShown] = useState<Finding | null>(finding);
  if (finding && finding !== shown) setShown(finding);
  const closing = !finding && shown !== null;

  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(() => setShown(null), EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [closing]);

  useEffect(() => {
    if (!finding) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [finding, onClose]);

  // Move keyboard focus into the panel when it opens, and start each facility at the top.
  const panel = useRef<HTMLElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const shownId = shown?.id;
  useEffect(() => {
    if (!shownId) return;
    panel.current?.focus({ preventScroll: true });
    scroller.current?.scrollTo({ top: 0 });
  }, [shownId]);

  // The panel is often taller than the window. While there is more below, its lower edge fades
  // out, so a line is never left looking cut off.
  const [more, setMore] = useState(false);
  useEffect(() => {
    const el = scroller.current;
    if (!el || !shownId) return;
    const update = () => setMore(el.scrollTop + el.clientHeight < el.scrollHeight - 8);
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [shownId]);

  if (!shown) return null;
  return (
    <aside
      ref={panel}
      tabIndex={-1}
      aria-label={`Facility: ${shown.subject.display_name ?? shown.subject.name}`}
      data-state={closing ? "closing" : "open"}
      className="glass facility-panel"
    >
      <div ref={scroller} className="facility-panel-scroll" data-more={more}>
        <div>
          <PanelBody key={shown.id} finding={shown} lastYear={lastYear} onClose={onClose} />
        </div>
      </div>
    </aside>
  );
}

function PanelBody({ finding, lastYear, onClose }: Props & { finding: Finding }) {
  const { subject, period, claimed, observed } = finding;
  const detail = useFindingDetail(finding.id);
  const [view, setView] = useState<"chart" | "table">("chart");

  const place = [subject.city, countryName(subject.country)].filter(Boolean).join(", ");
  const meta = [subject.operator, subject.sector, place].filter(Boolean).join(" · ");
  const title = subject.display_name ?? subject.name;
  const basis = claimed ? BASIS_LABEL[claimed.basis].toLowerCase() : "";
  const us = finding.validation_site === true;

  return (
    <>
      <header className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-[21px] font-semibold leading-[26px] [overflow-wrap:anywhere]">{title}</h2>
          {/* The register's own name, in full, wherever the title is a short one. */}
          {subject.display_name && (
            <p className="mt-1 text-[12px] leading-4 text-text-3 [overflow-wrap:anywhere]">{subject.name}</p>
          )}
          <p className="label mt-1.5">{meta}</p>
          {us && <p className="label mt-1">Test site for the method</p>}
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="icon-button -mr-2.5 -mt-2.5">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      <div className="mt-6 grid grid-cols-2 gap-x-6">
        <div className="min-w-0">
          <p className="label">{us ? "Stack monitors" : "Reported"}</p>
          {claimed ? (
            <>
              <p className="voice-record mt-1 whitespace-nowrap text-[48px] leading-[48px]">
                {formatTonnes(claimed.value)} t
              </p>
              <p className="record-source mt-2">
                NO<sub>x</sub> to air, {period.label}
              </p>
              <p className="record-source">{claimed.source}</p>
              <p className="record-source">Basis: {basis}</p>
            </>
          ) : (
            <p className="mt-1 flex h-12 items-center text-text-3">Nothing reported</p>
          )}
        </div>
        <div className="min-w-0">
          <p className="label">Satellite estimate</p>
          {observed ? (
            <>
              <p className="observed-number mt-1 whitespace-nowrap">{formatTonnes(observed.value)} t</p>
              <p className="instrument-note mt-2">
                {formatTonnes(observed.lo)} to {formatTonnes(observed.hi)}
              </p>
              <p className="instrument-note">
                95% interval{observed.interval_basis === "sampling" ? ", sampling noise only" : ""}
              </p>
              {observed.n_days !== undefined && (
                <p className="instrument-note">
                  {observed.n_days} clear days, {period.label}
                </p>
              )}
            </>
          ) : (
            <p className="mt-1 flex h-12 items-center text-text-3">No estimate yet</p>
          )}
        </div>
      </div>
      {period.note && <p className="record-source mt-2">{period.note}</p>}
      {observed && (
        <p className="mt-3 text-[12px] leading-4 text-text-3">
          Satellite-based estimate. The interval covers sampling noise only. Checked against US stack
          monitors, estimates that pass every quality check scatter by about 35% more than that.
        </p>
      )}
      <VerdictBlock finding={finding} />
      {finding.cluster && <ClusterNote cluster={finding.cluster} />}
      {finding.detection && <DetectionNote detection={finding.detection} />}

      {us && detail.status === "ready" && detail.data.id === finding.id && detail.data.validation && (
        <ValidationCheck validation={detail.data.validation} />
      )}

      {observed &&
        detail.status === "ready" &&
        detail.data.id === finding.id &&
        detail.data.evidence &&
        detail.data.profile &&
        detail.data.days && (
          <Evidence
            evidence={detail.data.evidence}
            profile={detail.data.profile}
            days={detail.data.days}
            observed={observed}
            year={period.label}
          />
        )}

      <section className="mt-5 border-t border-hairline pt-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="label">
            {us ? "Monitored" : "Reported"} NO<sub>x</sub> by year, tonnes
          </h3>
          <div role="group" aria-label="Show as" className="-mr-2 flex">
            <button
              type="button"
              className="text-button"
              aria-pressed={view === "chart"}
              onClick={() => setView("chart")}
            >
              Chart
            </button>
            <button
              type="button"
              className="text-button"
              aria-pressed={view === "table"}
              onClick={() => setView("table")}
            >
              Table
            </button>
          </div>
        </div>

        {detail.status === "loading" && (
          <div className="space-y-3 py-4" aria-label="Loading the reported series" role="status">
            <div className="skeleton-line w-full" />
            <div className="skeleton-line w-full" />
            <div className="skeleton-line w-3/5" />
          </div>
        )}
        {detail.status === "error" && (
          <p className="py-3 text-[14px] leading-5 text-text-2" role="alert">
            Could not load the reported series. Check your connection, then{" "}
            <button type="button" className="cursor-pointer underline underline-offset-4" onClick={detail.retry}>
              try again
            </button>
            .
          </p>
        )}
        {detail.status === "ready" && detail.data.id === finding.id && (
          <>
            {view === "chart" ? (
              <ReportedSeriesChart
                series={detail.data.reported_series}
                firstYear={us ? MONITORS_FIRST_YEAR : REGISTER_FIRST_YEAR}
                lastYear={lastYear}
                highlightYear={Number(period.label)}
              />
            ) : (
              <ReportedSeriesTable series={detail.data.reported_series} />
            )}
          </>
        )}
        <p className="mt-3 text-[12px] leading-4 text-text-3">
          {us
            ? "Hourly stack measurements summed over the calendar year, for every monitored power plant within 20 km."
            : "The register flags each value as measured, calculated or estimated. The public data files for this release leave that flag out."}
        </p>
      </section>

      <section className="mt-5 border-t border-hairline pt-4">
        <h3 className="label">Sources</h3>
        <ul className="mt-2 space-y-1 text-[14px] leading-5 text-text-2">
          <li>
            {us ? "Stack monitors" : "Reported emissions"}:{" "}
            <a
              href={us ? CAMPD_URL : REGISTER_URL}
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-4 hover:text-text"
            >
              {claimed?.source ?? "EEA Industrial Reporting database"}
            </a>
          </li>
          {us && <li>Other sources in the footprint: EPA National Emissions Inventory 2023</li>}
          <li>
            NO<sub>2</sub> layer{observed ? " and plume images" : ""}: {NO2_ATTRIBUTION}
          </li>
          {observed && <li>Wind: ERA5, Copernicus Climate Change Service</li>}
        </ul>
        <p className="axis-text mt-3 [overflow-wrap:anywhere]">
          {us ? subject.register_id : `Register ID ${subject.register_id}`}
        </p>
      </section>
    </>
  );
}
