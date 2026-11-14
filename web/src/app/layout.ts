// Layout numbers shared by the panel (CSS) and the camera (padding), PLAN.md 9.4 and 9.5.
// The matching CSS lives in design/index.css under ".facility-panel".

/** From this width up the panel sits at the right edge. Below it, it is a bottom sheet. */
export const SIDE_PANEL_MIN_WIDTH_PX = 768;
export const PANEL_WIDTH_PX = 420;
export const OUTER_MARGIN_PX = 24;
/** Share of the viewport height the bottom sheet covers on a phone. */
export const SHEET_HEIGHT_FRACTION = 0.56;

// The hero lines grow with the window (PLAN.md 9.3: 72 px on a desktop, 40 px on a phone, here
// held a little smaller so each line stays on one line). The CSS twin is ".hero-title" in
// design/index.css: clamp(24px, min(6.4vw, 8vh), 64px).
const HERO_FONT_MIN_PX = 24;
const HERO_FONT_MAX_PX = 64;
const HERO_LINES_PER_FONT = 2.12; // two lines at a line height of 1.06
const HERO_REST_PX = 140; // the tagline, the button and the space under them

/** Height of the hero block at the bottom of the opening view, which the globe has to clear. */
export function heroHeightPx(viewportWidth: number, viewportHeight: number): number {
  const font = Math.min(
    HERO_FONT_MAX_PX,
    Math.max(HERO_FONT_MIN_PX, Math.min(viewportWidth * 0.064, viewportHeight * 0.08)),
  );
  return Math.round(font * HERO_LINES_PER_FONT + HERO_REST_PX);
}

// The flight from the opening view to the first story facility (PLAN.md 9.7): 4.5 s, and the
// panel slides in 300 ms before arrival.
export const STORY_FLIGHT_MS = 4500;
export const STORY_PANEL_LEAD_MS = 300;
