import { useMemo, useState } from "react";

import { GapBar } from "../charts/GapBar";
import { Link } from "../app/Link";
import { hrefFor, selectFacility } from "../app/route";
import { useFindings } from "../data/findings";
import { countryName, formatRatio, formatTonnes } from "../data/format";
import { leaderboardRows, type Row } from "../data/leaderboard";
import { VERDICT_LABEL, VerdictIcon, verdictColour } from "./VerdictBlock";

type VerdictFilter = "all" | "higher" | "consistent" | "lower" | "inconclusive" | "test";

const VERDICT_FILTERS: [VerdictFilter, string][] = [
  ["all", "All"],
  ["higher", VERDICT_LABEL.higher],
  ["consistent", VERDICT_LABEL.consistent],
  ["lower", VERDICT_LABEL.lower],
  ["inconclusive", VERDICT_LABEL.inconclusive],
  ["test", "US test sites"],
];

const rowVerdict = (r: Row): VerdictFilter => (r.kind === "test" ? "test" : (r.finding.verdict as VerdictFilter));

function Cells({ row, rank }: { row: Row; rank: number | null }) {
  const { finding: f, ratio, kind } = row;
  const title = f.subject.display_name ?? f.subject.name;
  const open = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    selectFacility(f.subject.id);
  };
  return (
    <tr>
      <td className="num">{rank ?? ""}</td>
      <th scope="row">
        <a href={hrefFor("module", f.subject.id)} onClick={open} className="nav-link">
          {title}
        </a>
        {f.subject.kind === "cluster" && <span className="row-tag">cluster</span>}
        <span className="row-sub">
          {[f.subject.city, countryName(f.subject.country)].filter(Boolean).join(", ")}
        </span>
      </th>
      <td className="num">{f.claimed ? `${formatTonnes(f.claimed.value)} t` : "None"}</td>
      <td className="num">{f.observed ? `${formatTonnes(f.observed.value)} t` : "No estimate"}</td>
      <td>
        {ratio ? (
          <div className="ratio-cell">
            <GapBar ratio={ratio} mini neutral={kind === "test"} />
            <span>
              {formatRatio(ratio.value)} <span className="text-text-3">({formatRatio(ratio.lo)} to {formatRatio(ratio.hi)})</span>
            </span>
          </div>
        ) : (
          <span className="text-text-3">Not compared</span>
        )}
      </td>
      <td>
        {f.verdict ? (
          <span className="verdict-inline" style={{ color: verdictColour(f.verdict) }}>
            <VerdictIcon verdict={f.verdict} />
            {VERDICT_LABEL[f.verdict]}
          </span>
        ) : (
          <span className="text-text-2">Test site</span>
        )}
      </td>
      <td>{f.grade ?? ""}</td>
    </tr>
  );
}

export function Leaderboard() {
  const findings = useFindings();
  const rows = useMemo(
    () => (findings.status === "ready" ? leaderboardRows(findings.data.findings) : []),
    [findings],
  );
  const [country, setCountry] = useState("all");
  const [sector, setSector] = useState("all");
  const [verdict, setVerdict] = useState<VerdictFilter>("all");

  if (findings.status === "loading") return <p className="text-text-3">Loading the checked sources.</p>;
  if (findings.status === "error") {
    return (
      <p>
        Could not load the data.{" "}
        <button type="button" className="text-button underline underline-offset-4" onClick={findings.retry}>
          Try again
        </button>
      </p>
    );
  }

  const countries = [...new Set(rows.map((r) => r.finding.subject.country))].sort();
  const sectors = [...new Set(rows.map((r) => r.finding.subject.sector))].sort();
  const shown = rows.filter(
    (r) =>
      (country === "all" || r.finding.subject.country === country) &&
      (sector === "all" || r.finding.subject.sector === sector) &&
      (verdict === "all" || rowVerdict(r) === verdict),
  );
  // Rank counts only rows that have a ratio, in the order of the full list.
  const rank = new Map<Row, number>();
  rows.filter((r) => r.ratio).forEach((r, i) => rank.set(r, i + 1));

  return (
    <>
      <p>
        Every source with a satellite verdict, plus the US power plants we use to test the method.
        Sorted by the lower end of the gap&apos;s interval, the most cautious reading. A source whose
        quality checks failed is listed as inconclusive, at the bottom, with no gap claimed.
      </p>
      <div className="filters">
        <label>
          Country
          <select value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="all">All</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {countryName(c)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sector
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="all">All</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Verdict
          <select value={verdict} onChange={(e) => setVerdict(e.target.value as VerdictFilter)}>
            {VERDICT_FILTERS.map(([v, text]) => (
              <option key={v} value={v}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table className="leaderboard">
          <caption className="sr-only">Checked sources, most cautious gap first</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Source</th>
              <th scope="col">Reported</th>
              <th scope="col">Satellite estimate</th>
              <th scope="col">Ratio, 95% interval</th>
              <th scope="col">Verdict</th>
              <th scope="col">Grade</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <Cells key={r.finding.id} row={r} rank={rank.get(r) ?? null} />
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && <p className="text-text-3">Nothing matches these filters.</p>}
      <p className="text-[12px] leading-4 text-text-3">
        US test sites are compared with their stack monitors and have no verdict. Their interval
        covers sampling noise only. The other {findings.data.count - rows.length} facilities are on the
        globe with their reported figures. <Link to="module" className="nav-link">Open the globe</Link>.
      </p>
    </>
  );
}
