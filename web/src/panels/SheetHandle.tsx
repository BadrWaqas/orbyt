import { useRef } from "react";
import type { KeyboardEvent, PointerEvent, RefObject } from "react";

// PLAN.md 9.6, MobileSheet: three snap points, a drag handle, and the globe stays interactive
// above the sheet. The snap heights are repeated in design/index.css under ".facility-panel".

export type Snap = "peek" | "half" | "full";
const ORDER: Snap[] = ["peek", "half", "full"];

const PEEK_PX = 112; // the handle and the facility's name
const HALF_FRACTION = 0.56; // the same number as SHEET_HEIGHT_FRACTION in app/layout.ts
const FULL_FRACTION = 0.9;
const TAP_PX = 6; // a touch that moves less than this is a tap, not a drag

const heights = () => ({
  peek: PEEK_PX,
  half: Math.round(window.innerHeight * HALF_FRACTION),
  full: Math.round(window.innerHeight * FULL_FRACTION),
});

/** The sheet height for the globe's attribution to ride on, as a CSS length. */
export const SNAP_CSS: Record<Snap, string> = {
  peek: `${PEEK_PX}px`,
  half: `${HALF_FRACTION * 100}dvh`,
  full: `${FULL_FRACTION * 100}dvh`,
};

function nearest(height: number): Snap {
  const h = heights();
  return ORDER.reduce((best, s) => (Math.abs(h[s] - height) < Math.abs(h[best] - height) ? s : best));
}

interface Props {
  sheet: RefObject<HTMLElement | null>;
  snap: Snap;
  onSnap: (snap: Snap) => void;
}

/** The handle at the top of the bottom sheet. Hidden from 768 px up, where the panel is a column. */
export function SheetHandle({ sheet, snap, onSnap }: Props) {
  const drag = useRef<{ y: number; height: number; moved: boolean } | null>(null);

  const down = (e: PointerEvent<HTMLButtonElement>) => {
    const el = sheet.current;
    if (!el) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { y: e.clientY, height: el.offsetHeight, moved: false };
    el.dataset.drag = "true";
  };

  const move = (e: PointerEvent<HTMLButtonElement>) => {
    const el = sheet.current;
    const d = drag.current;
    if (!el || !d) return;
    const dy = d.y - e.clientY;
    if (Math.abs(dy) > TAP_PX) d.moved = true;
    const h = heights();
    el.style.height = `${Math.min(h.full, Math.max(h.peek, d.height + dy))}px`;
  };

  const up = (e: PointerEvent<HTMLButtonElement>) => {
    const el = sheet.current;
    const d = drag.current;
    drag.current = null;
    if (!el || !d) return;
    const released = el.offsetHeight;
    el.style.height = "";
    delete el.dataset.drag;
    if (d.moved) onSnap(nearest(released + (d.y - e.clientY) * 0.15));
    else onSnap(snap === "half" ? "full" : "half"); // a tap
  };

  const key = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = ORDER.indexOf(snap);
    if (e.key === "ArrowUp" && i < 2) onSnap(ORDER[i + 1]);
    else if (e.key === "ArrowDown" && i > 0) onSnap(ORDER[i - 1]);
    else return;
    e.preventDefault();
  };

  return (
    <button
      type="button"
      className="sheet-handle"
      aria-label="Resize the panel. Arrow up and down change its height."
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onKeyDown={key}
      // A keyboard press arrives as a click with no pointer. A touch or mouse press is a tap above.
      onClick={(e) => {
        if (e.detail === 0) onSnap(snap === "half" ? "full" : "half");
      }}
    >
      <span aria-hidden="true" />
    </button>
  );
}
