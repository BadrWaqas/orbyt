import { GapBar } from "../charts/GapBar";
import { BASIS_LABEL, countryName, formatTonnes } from "../data/format";
import { toRow } from "../data/leaderboard";
import type { Evidence, Finding } from "../data/types";
import { VERDICT_LABEL, VerdictIcon, verdictColour } from "../panels/VerdictBlock";
import { Graticule } from "./Graticule";

// The ShareCard (PLAN.md 9.6): 1200 x 630, black, the plume on the right where there is one,
// the number pair on the left, the verdict and the wordmark. Playwright photographs it from the
// hidden /card/<finding id> route (scripts/make-share-cards.mjs), and LinkedIn shows the picture
// when a facility link is shared (scripts/make-share-pages.mjs).
//
// Same rules as the panel: the record in serif and paper tone, the instrument in the glowing
// wide sans, fixed verdict words, and no claim about conduct.

export const CARD_WIDTH = 1200;
export const CARD_HEIGHT = 630;

/** Large numerals shrink a little when they run to many digits, so the pair never overflows. */
function numeralSize(text: string): number {
  return text.length > 9 ? 44 : text.length > 7 ? 52 : 60;
}

function Brand({ label }: { label: string }) {
  return (
    <p className="sc-brand">
      <span className="wordmark">Orbyt Earth</span>
      <span className="sc-brand-sep" aria-hidden="true" />
      <span>{label}</span>
    </p>
  );
}

interface Props {
  finding: Finding;
  /** The stacked plume picture, when the finding has a satellite estimate. */
  evidence: Evidence | null;
}

export function ShareCard({ finding, evidence }: Props) {
  const { subject, period, claimed, observed, verdict, grade } = finding;
  const title = subject.display_name ?? subject.name;
  const place = [subject.city, countryName(subject.country)].filter(Boolean).join(", ");
  const meta = [subject.sector, place].filter(Boolean).join(" · ");
  const us = finding.validation_site === true;
  const row = toRow(finding);
  const compared = verdict !== null && observed !== null && verdict !== "inconclusive" && verdict !== "unpaired";

  const reportedText = claimed ? `${formatTonnes(claimed.value)} t` : "None";
  const observedText = observed ? `${formatTonnes(observed.value)} t` : null;
  const basis = claimed && claimed.basis !== "unknown" ? `, ${BASIS_LABEL[claimed.basis].toLowerCase()}` : "";
  const noEstimateNote =
    finding.detection && !finding.detection.reliable
      ? "Below the size where the method measures reliably."
      : "Reported figure only.";

  return (
    <div className="share-card" data-card-ready="false">
      <div className="sc-art" aria-hidden="true">
        {evidence ? (
          <>
            <img className="sc-plume" src={evidence.stack_image} alt="" />
            <p className="sc-art-note">
              NO<sub>2</sub> stacked on {evidence.stack.n_days} clear days, wind to the right
            </p>
          </>
        ) : (
          <Graticule lat={subject.lat} lon={subject.lon} />
        )}
      </div>

      <div className="sc-text">
        <Brand label="Pollution Hunter" />

        <div>
          <h1 className="sc-title">{title}</h1>
          <p className="sc-meta">{meta}</p>
        </div>

        <div>
          <div className="sc-pair">
            <div className="sc-col">
              <p className="sc-label">{us ? "Stack monitors" : "Reported"}, {period.label}</p>
              <p className="voice-record sc-num" style={{ fontSize: numeralSize(reportedText) }}>
                {reportedText}
              </p>
              <p className="sc-source">
                {claimed ? `${claimed.source}${basis}` : "Nothing reported"}
              </p>
            </div>
            <div className="sc-col">
              <p className="sc-label">Satellite estimate</p>
              {observed && observedText ? (
                <>
                  <p className="observed-number sc-num" style={{ fontSize: numeralSize(observedText) }}>
                    {observedText}
                  </p>
                  <p className="sc-source sc-source-instrument">
                    95% interval {formatTonnes(observed.lo)} to {formatTonnes(observed.hi)}
                    {observed.n_days ? `, ${observed.n_days} clear days` : ""}
                  </p>
                </>
              ) : (
                <>
                  <p className="sc-none">No estimate yet</p>
                  <p className="sc-source sc-source-instrument">{noEstimateNote}</p>
                </>
              )}
            </div>
          </div>

          {observed && (
            <div className="sc-verdict">
              {compared && finding.ratio && <GapBar ratio={finding.ratio} />}
              {us && row?.ratio && <GapBar ratio={row.ratio} neutral />}
              {verdict && !us && (
                <p className="sc-verdict-line" style={{ color: verdictColour(verdict) }}>
                  <VerdictIcon verdict={verdict} />
                  <span>{VERDICT_LABEL[verdict]}</span>
                  {grade && <span className="sc-grade">Grade {grade}</span>}
                </p>
              )}
              {us && <p className="sc-verdict-line sc-test">Test site for the method</p>}
            </div>
          )}
        </div>

        <p className="sc-foot">
          {observed
            ? "Satellite-based estimate, uncertain. Not a finding of non-compliance."
            : "An independent student research project."}
        </p>
      </div>
    </div>
  );
}

/** The card for the home link: the two voices and the globe over Europe. */
export function HomeShareCard() {
  return (
    <div className="share-card" data-card-ready="false">
      <div className="sc-art" aria-hidden="true">
        <Graticule lat={50} lon={14} marker={false} />
      </div>
      <div className="sc-text">
        <Brand label="Fact-checking the world from space" />
        <div>
          <p className="voice-record sc-hero">Reported on paper.</p>
          <p className="voice-instrument sc-hero sc-hero-instrument">Measured from orbit.</p>
        </div>
        <p className="sc-explainer">
          We compare what facilities report with what satellites measure, and show our working.
        </p>
        <p className="sc-foot">An independent student research project.</p>
      </div>
    </div>
  );
}
