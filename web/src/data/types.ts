// The data contract the pipeline publishes under /data/v1 (PLAN.md 2.5 and Appendix B).
// Written by hand for now. Milestone M5.5 replaces this file with types generated from the
// pipeline's JSON Schema.

export type Basis = "measured" | "calculated" | "estimated" | "stated" | "unknown";
export type Verdict = "higher" | "consistent" | "lower" | "inconclusive" | "unpaired";

export interface Subject {
  id: string;
  kind: "facility" | "cluster";
  /** The facility's name exactly as the register has it. Often includes the operator. */
  name: string;
  /** A short name for titles, where one has been written by hand. */
  display_name: string | null;
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
  /** Days in the stack. */
  n_days?: number;
  /** Lifetime of NO2 in the plume from the fit, hours. */
  lifetime_h?: number;
  /** What `lo` and `hi` cover. "sampling" is the bootstrap over days only (PLAN.md 4.7). */
  interval_basis?: "sampling" | "total";
}

/** Whether the footprint is big enough for the method to measure reliably (METHODS.md 7). */
export interface Detection {
  /** NOx reported (or, for US plants, monitored plus inventory) within the footprint, tonnes. */
  footprint_t: number;
  footprint_km: number;
  min_reliable_t: number;
  /** False means "below reliable detection": few estimates this small pass the quality checks. */
  reliable: boolean;
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
  detection?: Detection;
  /** A US power plant from the validation against stack monitors (PLAN.md 1.7). */
  validation_site?: boolean;
}

export interface FindingsPayload {
  module: string;
  /** The target year. Some findings carry an earlier one, see `Period.note`. */
  period: string;
  source: string;
  count: number;
  latest_year_countries: Record<string, number>;
  /** The subject to open when a visitor asks to explore (PLAN.md 9.7). */
  showcase?: string;
  findings: Finding[];
}

export interface ReportedPoint {
  year: number;
  /** Tonnes of NOx, expressed as NO2. */
  value: number;
  basis: Basis;
}

/** The stacked curve F(t) and its EMG fit (PLAN.md 4.3). Null where the stack has no data. */
export interface PlumeProfileData {
  t_h: number[];
  flux_mol_s: (number | null)[];
  fit_mol_s: (number | null)[];
  fit: { q: number; tau: number; sigma: number; t0: number; b: number; r2: number };
}

/** One day in the stack. */
export interface DayRow {
  date: string;
  wind_ms: number;
  /** Compass direction the wind blows from, degrees clockwise from north. */
  wind_dir_deg: number;
  /** Position of the day's frame in the flipbook sheet, or null if the day was too cloudy. */
  frame: number | null;
}

export interface StackGeometry {
  width: number;
  height: number;
  /** First and last travel time across the image, hours. */
  t_h: [number, number];
  /** Bottom and top of the image across the wind, km. */
  crosswind_km: [number, number];
  full_scale_umol_m2: number;
  mean_wind_ms: number;
  /** Half-width of the band the estimate integrates, one value per profile time. */
  fan_half_width_km: number[];
  n_days: number;
}

export interface FlipbookSheet {
  frame_w: number;
  frame_h: number;
  columns: number;
  rows: number;
  n_frames: number;
  /** Each frame is a north-up square reaching this far from the source, km. */
  half_km: number;
  full_scale_umol_m2: number;
}

export interface Evidence {
  stack_image: string;
  flipbook: string;
  stack: StackGeometry;
  flipbook_sheet: FlipbookSheet;
}

/** One year of a US plant's satellite estimate against its stack monitors. */
export interface ValidationYear {
  year: number;
  estimate_t: number | null;
  lo: number | null;
  hi: number | null;
  /** True when the estimate passed every quality gate. */
  passed: boolean;
  gates_failed: string[];
  days: number | null;
  /** Monitor NOx over the 3 hours before each pass, as tonnes per year. */
  monitors_at_pass_t: number | null;
  /** Calendar-year monitor total. */
  monitors_t: number | null;
  /** Monitors plus NOx the monitors cannot see in the footprint (EPA NEI 2023). */
  footprint_t: number | null;
  ratio_at_pass: number | null;
  ratio_footprint: number | null;
}

export interface ValidationDetail {
  tier: number;
  unmonitored_t: number;
  unmonitored_largest: string;
  u_sys: number;
  years: ValidationYear[];
}

export interface FindingDetail {
  id: string;
  reported_series: ReportedPoint[];
  sources: string[];
  /** US validation plants only. */
  validation?: ValidationDetail;
  /** The satellite side. Present only where an estimate passed every gate. */
  observed?: Observed;
  profile?: PlumeProfileData;
  days?: DayRow[];
  evidence?: Evidence;
}
