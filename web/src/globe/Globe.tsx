import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

import { addNo2Layer } from "../modules/pollution-hunter/no2Layer";
import { FIRST_OVERLAY_LAYER_ID, nightStyle } from "./style";

const SPIN_DEG_PER_S = 2; // PLAN.md 9.6
const GLOBE_FILL = 0.72; // share of the shorter viewport side the globe should cover
const HERO_CLEARANCE_PX = 120;
const PHONE_MAX_WIDTH_PX = 768; // below Tailwind's md breakpoint
const START: [number, number] = [14, 28]; // Europe and Africa facing the viewer

/** Zoom at which the globe's diameter is about `fill` of the shorter side of the container. */
function fitZoom(el: HTMLElement, fill: number): number {
  const shorter = Math.min(el.clientWidth, el.clientHeight);
  // At zoom z the equator is 512 * 2^z px long, so the diameter is that divided by pi.
  return Math.log2((fill * shorter * Math.PI) / 512);
}

interface GlobeProps {
  /** Called once, when the NO2 layer starts to fade in. */
  onNo2Visible?: () => void;
}

export function Globe({ onNo2Visible }: GlobeProps) {
  const container = useRef<HTMLDivElement>(null);
  // Kept in a ref so a new callback from the parent never rebuilds the map.
  const onNo2VisibleRef = useRef(onNo2Visible);
  onNo2VisibleRef.current = onNo2Visible;

  useEffect(() => {
    const el = container.current;
    if (!el) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const map = new maplibregl.Map({
      container: el,
      style: nightStyle,
      center: START,
      zoom: fitZoom(el, GLOBE_FILL),
      minZoom: 0.5,
      maxPitch: 60,
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      attributionControl: { compact: true },
    });
    // Lift the globe's centre so it clears the hero text at the bottom of the screen.
    map.setPadding({ top: 0, right: 0, bottom: HERO_CLEARANCE_PX, left: 0 });

    // On a phone the open attribution would cover the hero text, so it starts folded behind its
    // info button. MapLibre opens it when the first source reports its credits. This handler is
    // registered after MapLibre's own, so it folds it again before anything is painted.
    const foldAttribution = () => {
      const attribution = el.querySelector(".maplibregl-ctrl-attrib");
      if (!attribution?.classList.contains("maplibregl-compact-show")) return;
      attribution.classList.remove("maplibregl-compact-show");
      map.off("sourcedata", foldAttribution);
    };
    if (el.clientWidth < PHONE_MAX_WIDTH_PX) map.on("sourcedata", foldAttribution);

    // Slow rotation until the first touch, click, scroll or key press.
    let spinning = !reducedMotion;

    const spin = () => {
      if (!spinning) return;
      const centre = map.getCenter();
      map.easeTo({
        center: [centre.lng - SPIN_DEG_PER_S, centre.lat],
        duration: 1000,
        easing: (t) => t,
      });
    };

    const stopSpin = () => {
      if (!spinning) return;
      spinning = false;
      map.stop();
    };

    let removeNo2Listeners = () => {};
    map.once("load", () => {
      removeNo2Listeners = addNo2Layer(map, {
        beforeId: FIRST_OVERLAY_LAYER_ID,
        reducedMotion,
        onVisible: () => onNo2VisibleRef.current?.(),
      });
    });

    map.on("moveend", spin);
    map.once("load", spin);
    el.addEventListener("pointerdown", stopSpin);
    el.addEventListener("wheel", stopSpin, { passive: true });
    el.addEventListener("keydown", stopSpin);

    return () => {
      removeNo2Listeners();
      el.removeEventListener("pointerdown", stopSpin);
      el.removeEventListener("wheel", stopSpin);
      el.removeEventListener("keydown", stopSpin);
      map.remove();
    };
  }, []);

  // MapLibre's stylesheet sets `position: relative` on its container, which would cancel
  // `absolute inset-0`. So the outer div does the positioning and the map fills it.
  return (
    <div className="absolute inset-0">
      <div
        ref={container}
        className="h-full w-full"
        role="application"
        aria-label="Interactive globe. Drag to rotate, scroll or pinch to zoom."
      />
    </div>
  );
}
