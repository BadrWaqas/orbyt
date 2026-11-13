// The data contract the pipeline publishes under /data/v1 (PLAN.md 2.5 and Appendix B).
// Written by hand for now. Milestone M5.5 replaces this file with types generated from the
// pipeline's JSON Schema.

export type Basis = "measured" | "calculated" | "estimated" | "stated" | "unknown";
export type Verdict = "higher" | "consistent" | "lower" | "inconclusive" | "unpaired";

export interface Subject {
  id: string;
  kind: "facility" | "cluster";
  name: string;
  operator: string | null;
  sector: string;
  /** ISO 3166-1 alpha-2. */
  country: string;
  city: string | null;
  lat: number;
  lon: number;
  register: string;
  register_id: string;
}

export interface Period {
  label: string;
  start: string;
  end: string;
  /** Set when the year differs from the dataset's target year. */
  note?: string;
}

export interface Claimed {
  value: number;
  unit: string;
  basis: Basis;
  source: string;
}

export interface Observed {
  value: number;
  lo: number;
  hi: number;
  unit: string;
  method: string;
}

export interface Finding {
  id: string;
  module: string;
  subject: Subject;
  period: Period;
  claimed: Claimed | null;
  observed: Observed | null;
  ratio: { value: number; lo: number; hi: number } | null;
  verdict: Verdict | null;
  grade: "A" | "B" | "C" | null;
}

export interface FindingsPayload {
  module: string;
  /** The target year. Some findings carry an earlier one, see `Period.note`. */
  period: string;
  source: string;
  count: number;
  latest_year_countries: Record<string, number>;
  findings: Finding[];
}

export interface ReportedPoint {
  year: number;
  /** Tonnes of NOx, expressed as NO2. */
  value: number;
  basis: Basis;
}

export interface FindingDetail {
  id: string;
  reported_series: ReportedPoint[];
  sources: string[];
}
