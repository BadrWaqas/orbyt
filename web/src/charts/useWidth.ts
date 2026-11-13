import { useEffect, useRef, useState } from "react";

/** The live width of an element, so an SVG chart can be laid out in real pixels. */
export function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Layout shared by the evidence charts, so their time axes line up from tab to tab. */
export const GUTTER_LEFT_PX = 44; // room for the y axis labels
export const GUTTER_RIGHT_PX = 8;
