import { useCallback, useEffect, useState } from "react";

// The URL is the state (PLAN.md 2.7): ?f=<subject id> names the open facility, so every view
// is a link that can be shared.
const PARAM = "f";

function readSelection(): string | null {
  return new URLSearchParams(window.location.search).get(PARAM);
}

export function useSelection(): [string | null, (subjectId: string | null) => void] {
  const [selectedId, setSelectedId] = useState<string | null>(readSelection);

  useEffect(() => {
    const onPopState = () => setSelectedId(readSelection());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const select = useCallback((subjectId: string | null) => {
    const url = new URL(window.location.href);
    if (subjectId) url.searchParams.set(PARAM, subjectId);
    else url.searchParams.delete(PARAM);
    // Opening the panel adds a history entry, so Back closes it. Moving between facilities
    // and closing replace the entry, so Back never has to walk through every facility visited.
    if (subjectId && !readSelection()) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    setSelectedId(subjectId);
  }, []);

  return [selectedId, select];
}
