import { CONTACT_EMAIL, CREDITS, LICENCES_URL, STANDING_LINE } from "./credits";
import { Link } from "./Link";

/**
 * The footer of every page (PLAN.md 7.2 and 7.3): the standing line, the contact address, the
 * corrections log and the credit each data source asks for.
 */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p className="site-footer-line">{STANDING_LINE}</p>
      <p>
        Contact:{" "}
        <a className="page-link" href={`mailto:${CONTACT_EMAIL}`}>
          {CONTACT_EMAIL}
        </a>
        . Mistakes and replies are logged on the{" "}
        <Link to="corrections" className="page-link">
          corrections page
        </Link>
        .
      </p>
      <ul className="site-footer-credits">
        {CREDITS.map((c) => (
          <li key={c.label}>
            <span>{c.label}:</span> {c.text}.
          </li>
        ))}
      </ul>
      <p>
        Each source keeps its own terms.{" "}
        <a className="page-link" href={LICENCES_URL} target="_blank" rel="noopener noreferrer">
          Data licences
        </a>
        .
      </p>
    </footer>
  );
}
