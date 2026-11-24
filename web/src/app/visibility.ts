// Whether the visitor can see the page (PLAN.md 9.10: pause rendering when the tab is hidden).
//
// A browser already stops requestAnimationFrame in a hidden tab. What it keeps running are the
// things the page started itself: timers, a camera turn that is waiting to be picked up again,
// CSS animations. Those ask here and stand still until the page is back.

export const isHidden = (): boolean => document.visibilityState === "hidden";

/** Call `listener` each time the page is hidden or shown again. Returns the function that stops it. */
export function onVisibilityChange(listener: (hidden: boolean) => void): () => void {
  const handler = () => listener(isHidden());
  document.addEventListener("visibilitychange", handler);
  return () => document.removeEventListener("visibilitychange", handler);
}

/**
 * Mark the page as hidden for CSS, which pauses every animation under `html[data-hidden]`
 * (design/index.css). Call once, as the app starts.
 */
export function markHiddenForCss(): void {
  const root = document.documentElement;
  const mark = () => root.toggleAttribute("data-hidden", isHidden());
  mark();
  onVisibilityChange(mark);
}
