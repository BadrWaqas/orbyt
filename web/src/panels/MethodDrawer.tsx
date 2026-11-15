import { Link } from "../app/Link";
import { METHOD_STEPS } from "../app/MethodBody";
import { formatOneDecimal, formatTonnes } from "../data/format";
import type { Finding } from "../data/types";

// PLAN.md 9.6, MethodDrawer: five steps, numbered because it is a sequence. Each step carries
// this facility's own number where there is one.

function stepFacts(finding: Finding): (string | null)[] {
  const o = finding.observed;
  if (!o) return [null, null, null, null, null];
  return [
    o.n_days ? `${o.n_days} usable days for ${finding.period.label}.` : null,
    null,
    null,
    o.lifetime_h ? `Fitted lifetime of NO2 in the plume: ${formatOneDecimal(o.lifetime_h)} hours.` : null,
    `Estimate ${formatTonnes(o.value)} t, 95% interval ${formatTonnes(o.lo)} to ${formatTonnes(o.hi)} t (sampling only).`,
  ];
}

export function MethodDrawer({ finding }: { finding: Finding }) {
  if (!finding.observed) return null;
  const facts = stepFacts(finding);
  return (
    <details className="method-drawer">
      <summary>How we know</summary>
      <ol>
        {METHOD_STEPS.map((s, i) => (
          <li key={s.title}>
            <strong>{s.title}.</strong> {s.text}
            {facts[i] && <span className="method-fact">{facts[i]}</span>}
          </li>
        ))}
      </ol>
      <p className="mt-2">
        <Link to="method" className="nav-link">
          Read the full method
        </Link>
      </p>
    </details>
  );
}
