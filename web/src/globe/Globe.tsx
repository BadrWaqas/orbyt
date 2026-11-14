import maplibregl from "maplibre-gl";
import type { PaddingOptions } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import {
  OUTER_MARGIN_PX,
  PANEL_WIDTH_PX,
  SHEET_HEIGHT_FRACTION,
  SIDE_PANEL_MIN_WIDTH_PX,
} from "../app/layout";
import type { Finding } from "../data/types";
import {
  addFacilityMarkers,
  type FacilityMarkers,
} from "../modules/pollution-hunter/facilityMarkers";
import { addNo2Layer } from "../modules/pollution-hunter/no2Layer";
import { FIRST_LABEL_LAYER_ID, FIRST_OVERLAY_LAYER_ID, nightStyle } from "./style";

const SPIN_DEG_PER_S = 2; // PLAN.md 9.6
const GLOBE_FILL = 0.72; // share of the shorter viewport side the globe should cover
const HERO_CLEARANCE_PX = 176; // the hero lines and the button under them
const PHONE_MAX_WIDTH_PX = 768; // below Tailwind's md breakpoint
const START: [number, number] = [14, 28]; // Europe and Africa facing the viewer

// Fly-to on select (PLAN.md 9.7): 1.8 to 3.5 s depending on distance, ease-out, pitch 45.
const ARRIVAL_ZOOM = 6; // close enough to single out a site, wide enough to keep the glow sharp
const ARRIVAL_PITCH_DEG = 45;
const FLY_MIN_MS = 1800;
const FLY_MAX_MS = 3500;
const FLY_FAR_KM = 4000; // from here on a flight takes the full 3.5 s
const SETTLE_MS = 600; // easing the camera back when the panel closes
const EXPLORE_ZOOM_STEPS = 0.4; // zooming in this far counts as leaving the opening view

const NO_PADDING: PaddingOptions = { top: 0, right: 0, bottom: 0, left: 0 };
const easeOut = (t: number) => 1 - (1 - t) ** 3;

/** Zoom at which the globe's diameter is about `fill` of the shorter side of the container. */
function fitZoom(el: HTMLElement, fill: number): number {
  const shorter = Math.min(el.clientWidth, el.clientHeight);
  // At zoom z the equator is 512 * 2^z px long, so the diameter is that divided by pi.
  return Math.log2((fill * shorter * Math.PI) / 512);
}

/** The part of the map the open panel covers, so a selected site lands in the part that is free. */
function panelPadding(el: HTMLElement): PaddingOptions {
  if (el.clientWidth >= SIDE_PANEL_MIN_WIDTH_PX) {
    return { ...NO_PADDING, right: PANEL_WIDTH_PX + OUTER_MARGIN_PX };
  }
  return { ...NO_PADDING, bottom: Math.round(el.clientHeight * SHEET_HEIGHT_FRACTION) };
}

interface GlobeProps {
  /** Facilities to draw as markers. Null until they have loaded. */
  findings: Finding[] | null;
  /** The facility whose panel is open. The camera flies to it. */
  selected: Finding | null;
  onSelect: (subjectId: string) => void;
  /** Called once, when the NO2 layer starts to fade in. */
  onNo2Visible?: () => void;
  /** Called once, when the visitor zooms in from the opening view. */
  onExplore?: () => void;
}

export function Globe({ findings, selected, onSelect, onNo2Visible, onExplore }: GlobeProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const stopSpinRef = useRef(() => {});
  const hasFlownRef = useRef(false);
  const [ready, setReady] = useState(false);
  const [markers, setMarkers] = useState<FacilityMarkers | null>(null);

  // Callbacks are kept in a ref so a new function from the parent never rebuilds the map.
  const callbacks = useRef({ onSelect, onNo2Visible, onExplore });
  callbacks.current = { onSelect, onNo2Visible, onExplore };

  // Facility markers, once both the map and the findings are there.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !findings) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const added = addFacilityMarkers(map, findings, {
      beforeId: FIRST_LABEL_LAYER_ID,
      reducedMotion,
      onSelect: (subjectId) => callbacks.current.onSelect(subjectId),
    });
    setMarkers(added);
    return () => {
      setMarkers(null);
      if (mapRef.current === map) added.remove(); // otherwise the map is already gone
    };
  }, [ready, findings]);

  // The selection ring follows the selected facility.
  useEffect(() => {
    markers?.setSelected(selected);
  }, [markers, selected]);

  // The camera follows it too.
  useEffect(() => {
    const map = mapRef.current;
    const el = container.current;
    if (!map || !el || !ready) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!selected) {
      // The panel closed: hand its share of the screen back to the map.
      if (!hasFlownRef.current) return;
      if (reducedMotion) map.setPadding(NO_PADDING);
      else map.easeTo({ padding: NO_PADDING, duration: SETTLE_MS, easing: easeOut });
      return;
    }

    stopSpinRef.current();
    hasFlownRef.current = true;
    const centre = new maplibregl.LngLat(selected.subject.lon, selected.subject.lat);
    const zoom = Math.max(map.getZoom(), ARRIVAL_ZOOM);
    const camera = { center: centre, zoom, pitch: ARRIVAL_PITCH_DEG, padding: panelPadding(el) };
    if (reducedMotion) {
      map.jumpTo(camera);
      return;
    }
    const km = map.getCenter().distanceTo(centre) / 1000;
    const share = Math.min(1, km / FLY_FAR_KM + Math.abs(zoom - map.getZoom()) / 12);
    map.flyTo({
      ...camera,
      duration: FLY_MIN_MS + (FLY_MAX_MS - FLY_MIN_MS) * share,
      easing: easeOut,
    });
  }, [ready, selected]);

  // The map itself. Declared last, so on unmount the effects above clean up while it still exists.
  useEffect(() => {
    const el = container.current;
    if (!el) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startZoom = fitZoom(el, GLOBE_FILL);

    const map = new maplibregl.Map({
      container: el,
      style: nightStyle,
      center: START,
      zoom: startZoom,
      minZoom: 0.5,
      maxPitch: 60,
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    // Lift the globe's centre so it clears the hero text at the bottom of the screen.
    map.setPadding({ ...NO_PADDING, bottom: HERO_CLEARANCE_PX });

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
    stopSpinRef.current = stopSpin;

    const noteExplore = () => {
      if (map.getZoom() < startZoom + EXPLORE_ZOOM_STEPS) return;
      map.off("zoom", noteExplore);
      callbacks.current.onExplore?.();
    };
    map.on("zoom", noteExplore);

    let removeNo2Listeners = () => {};
    map.once("load", () => {
      removeNo2Listeners = addNo2Layer(map, {
        beforeId: FIRST_OVERLAY_LAYER_ID,
        reducedMotion,
        onVisible: () => callbacks.current.onNo2Visible?.(),
      });
      setReady(true);
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
      stopSpinRef.current = () => {};
      mapRef.current = null;
      setReady(false);
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
