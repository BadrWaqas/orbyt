import type { Finding, Ratio } from "./types";

// The leaderboard lists the sources that were checked: the European subjects with a verdict or
// an inconclusive one, and the US test sites. The other reported-only facilities are on the globe.

export type RowKind = "verdict" | "test" | "inconclusive";

export interface Row {
  finding: Finding;
  kind: RowKind;
  /** The ratio of estimate to reported, with its interval. Null when there is no estimate to compare. */
  ratio: Ratio | null;
}

/** A US plant has no verdict, but its estimate can still be read against the stack monitors. */
function testRatio(f: Finding): Ratio | null {
  if (!f.observed || !f.claimed || f.claimed.value <= 0) return null;
  const c = f.claimed.value;
  return { value: f.observed.value / c, lo: f.observed.lo / c, hi: f.observed.hi / c };
}

export function toRow(f: Finding): Row | null {
  if (f.validation_site) return { finding: f, kind: "test", ratio: testRatio(f) };
  if (f.verdict === "inconclusive") return { finding: f, kind: "inconclusive", ratio: null };
  if (f.verdict) return { finding: f, kind: "verdict", ratio: f.ratio };
  return null;
}

/** Most cautious reading first: the lower bound of the ratio (PLAN.md 9.6). */
export function sortRows(rows: Row[]): Row[] {
  const reported = (r: Row) => r.finding.claimed?.value ?? 0;
  return [...rows].sort((a, b) => {
    if (a.ratio && b.ratio) return b.ratio.lo - a.ratio.lo;
    if (a.ratio) return -1;
    if (b.ratio) return 1;
    return reported(b) - reported(a);
  });
}

export function leaderboardRows(findings: Finding[]): Row[] {
  const rows: Row[] = [];
  for (const f of findings) {
    const row = toRow(f);
    if (row) rows.push(row);
  }
  return sortRows(rows);
}
