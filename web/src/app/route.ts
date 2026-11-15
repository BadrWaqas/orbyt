import { useSyncExternalStore } from "react";

// The URL is the state (PLAN.md 2.7), so every view is a link that can be shared.
//
//   /                                    the home screen
//   /explore?m=pollution-hunter          a module
//   /explore?m=pollution-hunter&f=<id>   a module with one facility open
//   /leaderboard, /method, /data, /about  pages
//
// A link that names a facility always opens Pollution Hunter, whatever its path. Links shared
// before the home screen existed look like /?f=<id>, and they keep working.

export type PageView = "leaderboard" | "method" | "data" | "about";
export type View = "home" | "module" | PageView;

export interface Route {
  view: View;
  /** The open facility's subject id. Only ever set in the module view. */
  selectedId: string | null;
}

const MODULE_PATH = "/explore";
const MODULE_PARAM = "m";
const MODULE_ID = "pollution-hunter"; // the one live module, see modules/registry.ts
const FACILITY_PARAM = "f";
const PAGE_PATHS: Record<PageView, string> = {
  leaderboard: "/leaderboard",
  method: "/method",
  data: "/data",
  about: "/about",
};
const PAGE_VIEWS = Object.keys(PAGE_PATHS) as PageView[];

/** The address of a view. */
export function hrefFor(view: View, facilityId: string | null = null): string {
  if (view === "home") return "/";
  if (view !== "module") return PAGE_PATHS[view];
  const query = new URLSearchParams({ [MODULE_PARAM]: MODULE_ID });
  if (facilityId) query.set(FACILITY_PARAM, facilityId);
  return `${MODULE_PATH}?${query}`;
}

function readRoute(): Route {
  const facilityId = new URLSearchParams(window.location.search).get(FACILITY_PARAM);
  if (facilityId) return { view: "module", selectedId: facilityId };
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === MODULE_PATH) return { view: "module", selectedId: null };
  const page = PAGE_VIEWS.find((view) => PAGE_PATHS[view] === path);
  return { view: page ?? "home", selectedId: null };
}

const here = () => window.location.pathname + window.location.search;

let current = readRoute();
// An old facility link, or /explore without its module: show the address the view goes by now,
// so closing the panel later leaves the visitor in the module and not on the home screen.
if (current.view === "module" && here() !== hrefFor("module", current.selectedId)) {
  window.history.replaceState(null, "", hrefFor("module", current.selectedId));
}

const listeners = new Set<() => void>();
function set(route: Route) {
  current = route;
  for (const listener of listeners) listener();
}
window.addEventListener("popstate", () => set(readRoute()));

/** Go to a view. Adds a history entry, so Back returns to where the visitor was. */
export function navigate(view: View) {
  const href = hrefFor(view);
  if (href !== here()) window.history.pushState(null, "", href);
  set({ view, selectedId: null });
}

/** Open a facility in the module, or close the open one with null. */
export function selectFacility(subjectId: string | null) {
  const href = hrefFor("module", subjectId);
  // Opening the panel adds a history entry, so Back closes it. Moving between facilities
  // and closing replace the entry, so Back never has to walk through every facility visited.
  const opening = subjectId !== null && current.selectedId === null;
  if (opening) window.history.pushState(null, "", href);
  else window.history.replaceState(null, "", href);
  set({ view: "module", selectedId: subjectId });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => current);
}
