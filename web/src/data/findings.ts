import { useCallback, useEffect, useState } from "react";

import type { FindingDetail, FindingsPayload, Manifest } from "./types";

const BASE = "/data/v1/pollution-hunter";

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return (await response.json()) as T;
}

export type Loadable<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error" };

/** Fetch a JSON file from the data contract. `path` null means there is nothing to load yet. */
function useJson<T>(path: string | null): Loadable<T> & { retry: () => void } {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState({ status: "loading" });
    getJson<T>(path, controller.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => controller.abort();
  }, [path, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}

/** The compact list for the map: one row per subject and period. */
export function useFindings() {
  return useJson<FindingsPayload>(`${BASE}/findings.json`);
}

/** Full detail for the panel. Small, and cached by the browser after the first visit. */
export function useFindingDetail(findingId: string | null) {
  return useJson<FindingDetail>(findingId ? `${BASE}/finding/${findingId}.json` : null);
}

export interface FieldDescription {
  name: string;
  description: string;
}

/** The columns of the CSV and Parquet downloads, written next to them by the publish step. */
export function useFields() {
  return useJson<FieldDescription[]>(`${BASE}/fields.json`);
}

/** Data version, method version and build time. */
export function useManifest() {
  return useJson<Manifest>("/data/v1/manifest.json");
}
