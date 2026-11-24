import { CONTACT_EMAIL } from "./credits";

/** One entry of the log. Add new entries at the top, and mirror them in CORRECTIONS.md. */
export interface Correction {
  /** ISO date the correction was published. */
  date: string;
  /** What was wrong, in plain words, and where it appeared. */
  what: string;
  /** What it said before and what it says now. */
  change: string;
  /** The data and method versions the correction applies to. */
  versions: string;
}

// Nothing has been published yet, so there is nothing to correct (AGENTS.md rule 6).
const CORRECTIONS: readonly Correction[] = [];

/** The /corrections page: the public log, and how to report a mistake. */
export function CorrectionsBody() {
  return (
    <>
      <p>
        This is the public log of corrections to figures, verdicts and wording on Orbyt Earth. Each
        entry gives the date, what was wrong, what it said before, what it says now, and the data
        and method version it applies to. Newest first. Entries are not removed.
      </p>

      <h2>Log</h2>
      {CORRECTIONS.length === 0 ? (
        <p>No corrections have been published yet.</p>
      ) : (
        <ol className="correction-log">
          {CORRECTIONS.map((c) => (
            <li key={`${c.date}-${c.what}`}>
              <time dateTime={c.date}>{c.date}</time>
              <p>{c.what}</p>
              <p className="text-text-3">{c.change}</p>
              <p className="text-text-3">{c.versions}</p>
            </li>
          ))}
        </ol>
      )}

      <h2>Report a mistake or send a reply</h2>
      <p>
        If you find an error, or you run a site we show and want to respond, write to{" "}
        <a className="page-link" href={`mailto:${CONTACT_EMAIL}`}>
          {CONTACT_EMAIL}
        </a>
        . Name the facility and send a link to the page. Errors are fixed as soon as they are
        confirmed, and the fix is logged here. Replies from operators are published next to the
        finding they answer.
      </p>
      <p>
        The estimates are uncertain and are not findings of non-compliance. How they are made is on
        the{" "}
        <a className="page-link" href="/method">
          method page
        </a>
        .
      </p>
    </>
  );
}
