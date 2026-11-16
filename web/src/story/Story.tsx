import { useEffect, useRef, useState } from "react";

import { Link } from "../app/Link";
import { formatTonnes } from "../data/format";
import type { Finding } from "../data/types";
import { chapterBody, chapters, type ChapterFacts } from "./chapters";

// The scroll story's text column (M7.4, PLAN.md 9.5): one chapter per screen height, 440 px
// wide at the left over the globe, in the bottom third on a phone. The globe flies when a
// chapter crosses the middle of the screen: the driver here watches the chapters and reports
// the one in the middle, and app/App.tsx hands that to the globe.
//
// Styles are in design/index.css under "The scroll story".

interface Props {
  facts: ChapterFacts;
  /** The first story facility, whose two numbers the fourth chapter shows. Null until loaded. */
  showcase: Finding | null;
  /** Called with the index of the chapter in the middle of the screen when it changes. */
  onChapter: (index: number) => void;
}

/** The number pair of PLAN.md 9.6, in the two voices, for the chapter about the check. */
function NumberPair({ finding }: { finding: Finding }) {
  const { claimed, observed, subject, period } = finding;
  if (!claimed || !observed) return null;
  return (
    <div className="story-pair" aria-label={`${subject.display_name ?? subject.name}, ${period.label}`}>
      <p className="story-pair-name">
        {subject.display_name ?? subject.name}, {period.label}
      </p>
      <div className="story-pair-row">
        <div>
          <p className="label">Reported</p>
          <p className="voice-record story-pair-number">{formatTonnes(claimed.value)} t</p>
        </div>
        <div>
          <p className="label">Satellite estimate</p>
          <p className="observed-number story-pair-number">{formatTonnes(observed.value)} t</p>
          <p className="instrument-note">
            {formatTonnes(observed.lo)} to {formatTonnes(observed.hi)}
          </p>
        </div>
      </div>
    </div>
  );
}

export function Story({ facts, showcase, onChapter }: Props) {
  const column = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const report = useRef(onChapter);
  report.current = onChapter;

  // A chapter becomes the active one when it covers the middle of the screen.
  useEffect(() => {
    const root = column.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>("[data-chapter]"));
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = Number((entry.target as HTMLElement).dataset.chapter);
          setActive(index);
          report.current(index);
        }
      },
      // A band across the middle of the screen: the chapter crossing it is the one on show.
      { root, rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    );
    for (const item of items) observer.observe(item);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={column} className="story" data-active={active}>
      <ol className="story-column" aria-label="Story">
        {chapters.map((chapter, i) => (
          <li key={chapter.id} data-chapter={i} className="story-chapter" data-active={i === active}>
            <div className="story-card glass">
              <p className="axis-text story-count">
                {i + 1} of {chapters.length}
              </p>
              <h2 className="story-title">{chapter.title}</h2>
              <p className="story-body">{chapterBody(chapter, facts)}</p>
              {chapter.id === "check" && showcase && <NumberPair finding={showcase} />}
              {i === chapters.length - 1 && (
                <p className="story-actions">
                  <Link to="module" className="glass quiet-button">
                    Explore the globe
                  </Link>
                  <Link to="leaderboard" className="text-button nav-link">
                    See every check
                  </Link>
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="story-hint axis-text" aria-hidden="true" data-shown={active === 0}>
        Scroll
      </p>
    </div>
  );
}
