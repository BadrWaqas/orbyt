import { GapBar } from "../charts/GapBar";
import type { Finding, Grade, Verdict } from "../data/types";

// PLAN.md 7.2: the verdict strings are fixed. The site describes, it does not accuse.
export const VERDICT_LABEL: Record<Verdict, string> = {
  higher: "Higher than reported",
  consistent: "Consistent with reported",
  lower: "Lower than reported",
  inconclusive: "Inconclusive",
  unpaired: "Nothing to compare",
};

const GRADE_TEXT: Record<Grade, string> = {
  A: "No flags and at least 80 clear days.",
  B: "One flag, or 40 to 79 clear days.",
  C: "A cluster, or two or more flags.",
};

const ICON: Record<Verdict, string> = {
  higher: "M8 13V3M3.5 7.5L8 3l4.5 4.5",
  lower: "M8 3v10M3.5 8.5L8 13l4.5-4.5",
  consistent: "M3 6h10M3 10h10",
  inconclusive: "M6 6.2a2 2 0 1 1 3 1.7c-.7.4-1 .8-1 1.6M8 12v.5",
  unpaired: "M4 8h8",
};

export function VerdictIcon({ verdict }: { verdict: Verdict }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d={ICON[verdict]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function verdictColour(verdict: Verdict): string {
  if (verdict === "higher") return "var(--gap-higher)";
  if (verdict === "lower") return "var(--gap-lower)";
  return "var(--text-2)";
}

/** Why a finding has no verdict, in plain words. */
function whyNone(finding: Finding): string {
  if (finding.detection && !finding.detection.reliable) {
    return "This footprint is below the size where the method measures reliably, so no gap is claimed.";
  }
  if (finding.verdict === "unpaired") return "There is no reported figure to set the estimate against.";
  return "At least one quality check failed for this period, so no gap is claimed.";
}

/** The gap bar, the verdict with its icon, and the grade. */
export function VerdictBlock({ finding }: { finding: Finding }) {
  const { verdict, ratio, grade } = finding;
  if (!verdict || !finding.observed) return null;
  const compared = ratio !== null && verdict !== "inconclusive" && verdict !== "unpaired";
  return (
    <section className="mt-5 border-t border-hairline pt-3" aria-label="Verdict">
      <p className="label">Gap</p>
      {ratio && compared && <GapBar ratio={ratio} />}
      <p className="verdict-line" style={{ color: verdictColour(verdict) }}>
        <VerdictIcon verdict={verdict} />
        <span>{VERDICT_LABEL[verdict]}</span>
        {grade && (
          <abbr className="grade-badge" title={`Grade ${grade}. ${GRADE_TEXT[grade]}`}>
            {grade}
          </abbr>
        )}
      </p>
      {!compared && <p className="mt-1 text-[12px] leading-4 text-text-3">{whyNone(finding)}</p>}
    </section>
  );
}
