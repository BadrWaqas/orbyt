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

// The home screen. The Earth sits in the middle with the six module cards around it. On a wide
// window the cards stand either side of the globe on a shallow arc ("orbit"). Where there is no
// room for that, they form a grid under it ("stack"). The camera (globe/Globe.tsx) and the page
// (app/Home.tsx and design/index.css) both read these numbers, so the globe, its halo and the
// cards always agree on where the Earth is. index.html repeats the globe's three numbers in a
// few lines of script, to place the poster of the Earth before the app has loaded.

const HOME_ORBIT_MIN_WIDTH_PX = 900;
const HOME_ORBIT_TOP_PX = 72; // the header
const HOME_ORBIT_TITLE_PX = 150; // the name and the tagline under the globe
const HOME_ORBIT_BOTTOM_PX = 32;
const HOME_CARD_MAX_WIDTH_PX = 280;
const HOME_CARD_MIN_WIDTH_PX = 220;
const HOME_CARD_ROW_PX = 132; // from one card's middle to the next
const HOME_CARD_EDGE_PX = 24; // kept clear between a card and the window edge
const HOME_STACK_TOP_PX = 56;
const HOME_STACK_GLOBE_MAX_PX = 300;

export interface HomeCardSlot {
  /** Left edge of the card and the height of its middle, px from the window's top left. */
  left: number;
  middle: number;
  side: "left" | "right";
}

export interface HomeLayout {
  kind: "orbit" | "stack";
  /** Centre and diameter of the globe, px from the window's top left. */
  cx: number;
  cy: number;
  diameter: number;
  /** Where the name starts, px from the top. */
  titleTop: number;
  /** Orbit only: the cards' width and places, in module order. Empty for the stack. */
  cardWidth: number;
  cards: HomeCardSlot[];
}

export function homeLayout(viewportWidth: number, viewportHeight: number): HomeLayout {
  const w = viewportWidth;
  const h = viewportHeight;
  const cx = w / 2;

  // Orbit: the globe takes the space between the header and the name.
  const room = h - HOME_ORBIT_TOP_PX - HOME_ORBIT_TITLE_PX - HOME_ORBIT_BOTTOM_PX;
  const diameter = Math.min(0.5 * h, 0.36 * w, room - 16);
  // The cards' inner edges lie on a circle this far from the globe's centre.
  const reach = diameter / 2 + Math.max(56, 0.17 * diameter);
  const cardWidth = Math.min(HOME_CARD_MAX_WIDTH_PX, Math.floor(cx - reach - HOME_CARD_EDGE_PX));
  const fits =
    w >= HOME_ORBIT_MIN_WIDTH_PX &&
    room >= 3 * HOME_CARD_ROW_PX &&
    cardWidth >= HOME_CARD_MIN_WIDTH_PX;

  if (fits) {
    const cy = HOME_ORBIT_TOP_PX + room / 2;
    const cards: HomeCardSlot[] = [];
    for (const side of ["left", "right"] as const) {
      for (const row of [-1, 0, 1]) {
        const dy = row * HOME_CARD_ROW_PX;
        const dx = Math.sqrt(reach * reach - dy * dy);
        cards.push({ left: side === "left" ? cx - dx - cardWidth : cx + dx, middle: cy + dy, side });
      }
    }
    return { kind: "orbit", cx, cy, diameter, titleTop: HOME_ORBIT_TOP_PX + room, cardWidth, cards };
  }

  // Stack: a smaller globe at the top, then the name, then the cards two abreast.
  const small = Math.max(96, Math.min(0.68 * w, 0.34 * h, HOME_STACK_GLOBE_MAX_PX));
  const top = HOME_STACK_TOP_PX + 8;
  return {
    kind: "stack",
    cx,
    cy: top + small / 2,
    diameter: small,
    titleTop: top + small + 12,
    cardWidth: 0,
    cards: [],
  };
}

// From the home screen into a module (PLAN.md 9.7 and 9.11): the camera dives toward the Earth,
// the cards fall away and the module's own light comes up. The hero lines arrive as it settles.
export const DIVE_MS = 2400;
/** Added in full when the globe has to turn half way round to bring Europe to the front. */
export const DIVE_TURN_MS = 1000;
export const HOME_RETURN_MS = 1600;
