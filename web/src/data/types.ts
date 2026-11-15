/* The data contract of /data/v1 (PLAN.md 2.5 and Appendix B).

/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Verdict".
 */
export type Verdict = "higher" | "consistent" | "lower" | "inconclusive" | "unpaired";
/**
 * What ``lo`` and ``hi`` cover. ``sampling`` is the bootstrap over days only (PLAN.md 4.7).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "IntervalBasis".
 */
export type IntervalBasis = "sampling" | "total";
/**
 * How a reported number was obtained, as the register says.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Basis".
 */
export type Basis = "measured" | "calculated" | "estimated" | "stated" | "unknown";
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Grade".
 */
export type Grade = "A" | "B" | "C";
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SubjectKind".
 */
export type SubjectKind = "facility" | "cluster";

/**
 * Every public document, so one schema file holds every definition.
 */
export interface Contract {
  finding_detail: FindingDetail;
  findings: FindingsPayload;
  manifest: Manifest;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FindingDetail".
 */
export interface FindingDetail {
  comparison?: Comparison | null;
  days?: DayRow[] | null;
  evidence?: Evidence | null;
  id: string;
  observed?: Observed | null;
  profile?: PlumeProfileData | null;
  reported_series: ReportedPoint[];
  rolling?: RollingWindow[] | null;
  sources: string[];
  validation?: ValidationDetail | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Comparison".
 */
export interface Comparison {
  flags: string[];
  periods: PeriodComparison[];
  u_sys: number;
  verdict_reason: string | null;
}
/**
 * One register year against its calendar-year estimate. Numbers only when it passed.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PeriodComparison".
 */
export interface PeriodComparison {
  gates_failed: string[];
  members: FootprintMember[];
  observed: PeriodObserved | null;
  ratio: Ratio | null;
  reason: string | null;
  reported_t: number | null;
  status: Verdict;
  year: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FootprintMember".
 */
export interface FootprintMember {
  name: string;
  register_id: string;
  reported_t: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PeriodObserved".
 */
export interface PeriodObserved {
  hi: number;
  lifetime_h: number;
  lo: number;
  n_days: number | null;
  value: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Ratio".
 */
export interface Ratio {
  hi: number;
  lo: number;
  value: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "DayRow".
 */
export interface DayRow {
  date: string;
  frame: number | null;
  wind_dir_deg: number;
  wind_ms: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  flipbook: string;
  flipbook_sheet: FlipbookSheet;
  stack: StackGeometry;
  stack_image: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FlipbookSheet".
 */
export interface FlipbookSheet {
  columns: number;
  frame_h: number;
  frame_w: number;
  full_scale_umol_m2: number;
  half_km: number;
  n_frames: number;
  rows: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "StackGeometry".
 */
export interface StackGeometry {
  /**
   * @minItems 2
   * @maxItems 2
   */
  crosswind_km: [number, number];
  fan_half_width_km: number[];
  full_scale_umol_m2: number;
  height: number;
  mean_wind_ms: number;
  n_days: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  t_h: [number, number];
  width: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Observed".
 */
export interface Observed {
  hi: number;
  interval_basis?: IntervalBasis | null;
  lifetime_h?: number | null;
  lo: number;
  method: string;
  n_days?: number | null;
  unit: string;
  value: number;
}
/**
 * The stacked curve F(t) and its EMG fit (PLAN.md 4.3).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PlumeProfileData".
 */
export interface PlumeProfileData {
  fit: PlumeFit;
  fit_mol_s: (number | null)[];
  flux_mol_s: (number | null)[];
  t_h: number[];
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "PlumeFit".
 */
export interface PlumeFit {
  b: number;
  q: number;
  r2: number;
  sigma: number;
  t0: number;
  tau: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ReportedPoint".
 */
export interface ReportedPoint {
  basis: Basis;
  value: number;
  year: number;
}
/**
 * The estimate for one rolling 12-month window. Not paired with the register.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "RollingWindow".
 */
export interface RollingWindow {
  calendar_year: number | null;
  end: string;
  gates_failed: string[];
  hi: number | null;
  label: string;
  lo: number | null;
  n_days: number;
  passed: boolean;
  start: string;
  value: number | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ValidationDetail".
 */
export interface ValidationDetail {
  tier: number;
  u_sys: number;
  unmonitored_largest: string;
  unmonitored_t: number;
  years: ValidationYear[];
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ValidationYear".
 */
export interface ValidationYear {
  days: number | null;
  estimate_t: number | null;
  footprint_t: number | null;
  gates_failed: string[];
  hi: number | null;
  lo: number | null;
  monitors_at_pass_t: number | null;
  monitors_t: number | null;
  passed: boolean;
  ratio_at_pass: number | null;
  ratio_footprint: number | null;
  year: number;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "FindingsPayload".
 */
export interface FindingsPayload {
  count: number;
  findings: Finding[];
  latest_year_countries: {
    [k: string]: number;
  };
  module: string;
  period: string;
  showcase?: string | null;
  source: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  claimed: Claimed | null;
  cluster?: ClusterInfo | null;
  detection?: Detection | null;
  grade: Grade | null;
  id: string;
  module: string;
  observed: Observed | null;
  period: Period;
  ratio: Ratio | null;
  subject: Subject;
  validation_site?: boolean | null;
  verdict: Verdict | null;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Claimed".
 */
export interface Claimed {
  basis: Basis;
  n_facilities?: number | null;
  source: string;
  unit: string;
  value: number;
}
/**
 * Set on a finding whose subject is a cluster: the reported total sums several facilities,
 * or a source just outside the 20 km footprint was left out (PLAN.md 1.7 fallback).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ClusterInfo".
 */
export interface ClusterInfo {
  n_facilities: number;
  neighbour?: ClusterNeighbour | null;
}
/**
 * The largest register source 20 to 60 km away. It is not in the footprint total.
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ClusterNeighbour".
 */
export interface ClusterNeighbour {
  distance_km: number;
  name: string;
  reported_t: number;
}
/**
 * Whether the footprint is big enough for the method to measure reliably (METHODS.md 7).
 *
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Detection".
 */
export interface Detection {
  footprint_km: number;
  footprint_t: number;
  min_reliable_t: number;
  reliable: boolean;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Period".
 */
export interface Period {
  end: string;
  label: string;
  note?: string | null;
  start: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Subject".
 */
export interface Subject {
  city: string | null;
  country: string;
  display_name: string | null;
  id: string;
  kind: SubjectKind;
  lat: number;
  lon: number;
  name: string;
  operator: string | null;
  register: string;
  register_id: string;
  sector: string;
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Manifest".
 */
export interface Manifest {
  built_at: string;
  commit: string;
  data_version: string;
  modules: ModuleEntry[];
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "ModuleEntry".
 */
export interface ModuleEntry {
  base: string;
  hue: string;
  id: string;
  method_version: string;
  status: string;
  title: string;
}
