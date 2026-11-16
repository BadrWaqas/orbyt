// The address of a facility's share page: /f/<slug>/ (PLAN.md 2.7).
//
// Plain JavaScript so the build scripts and the app use the very same function. The slug is
// the facility's name, folded to ASCII, followed by its subject id. The id keeps it unique and
// stable when two facilities share a name.

const FOLD = { "ł": "l", "ø": "o", "ß": "ss", "đ": "d", "æ": "ae", "œ": "oe", "ð": "d", "þ": "th" };
const MAX_WORDS_LENGTH = 44;

/**
 * @param {{ id: string, name: string, display_name: string | null }} subject
 * @returns {string}
 */
export function shareSlug(subject) {
  const title = subject.display_name ?? subject.name;
  const folded = title
    .toLowerCase()
    .replace(/[łøßđæœðþ]/g, (c) => FOLD[c])
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "");
  let words = folded.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (words.length > MAX_WORDS_LENGTH) {
    // Cut at a word boundary, so a long register name does not end mid-word.
    const cut = words.slice(0, MAX_WORDS_LENGTH);
    words = cut.slice(0, Math.max(cut.lastIndexOf("-"), 1));
  }
  return words ? `${words}-${subject.id}` : subject.id;
}

/** The path of a share page, with the trailing slash the static host expects. */
export function sharePath(subject) {
  return `/f/${shareSlug(subject)}/`;
}
