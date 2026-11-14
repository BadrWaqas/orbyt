import maplibregl from "maplibre-gl";
import type { PaddingOptions } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import {
  heroHeightPx,
  OUTER_MARGIN_PX,
  PANEL_WIDTH_PX,
  SHEET_HEIGHT_FRACTION,
  SIDE_PANEL_MIN_WIDTH_PX,
  STORY_FLIGHT_MS,
} from "../app/layout";
import type { Finding } from "../data/types";
import {
  addFacilityMarkers,
  type FacilityMarkers,
} from "../modules/pollution-hunter/facilityMarkers";
import { NO2_ATTRIBUTION } from "../modules/pollution-hunter/no2";
import { addNo2Layer, type No2Layer } from "../modules/pollution-hunter/no2Layer";
import type { SitePlumeSpec } from "../modules/pollution-hunter/sitePlume";
import { FIRST_LABEL_LAYER_ID, FIRST_OVERLAY_LAYER_ID, nightStyle } from "./style";

const SPIN_DEG_PER_S = 2; // PLAN.md 9.6
const GLOBE_FILL = 0.72; // share of the shorter viewport side the globe should cover
const GLOBE_TOP_MARGIN_PX = 24; // on a short window the globe shrinks to keep this much above it
const PHONE_MAX_WIDTH_PX = 768; // below Tailwind's md breakpoint
const START: [number, number] = [14, 28]; // Europe and Africa facing the viewer

// The intro (PLAN.md 9.7) opens a little further out and a little to the east, and drifts in
// while the globe turns, so Europe arrives at the centre as the hero lines do.
const INTRO_PULL_BACK_ZOOM = 0.3;
const INTRO_PUSH_IN_MS = 7000;
const INTRO_START_EAST_DEG = 10;

// Fly-to on select (PLAN.md 9.7): 1.8 to 3.5 s depending on distance, ease-out, pitch 45.
const ARRIVAL_ZOOM = 6; // close enough to single out a site, wide enough to keep the glow sharp
const ARRIVAL_PITCH_DEG = 45;
const FLY_MIN_MS = 1800;
const FLY_MAX_MS = 3500;
const FLY_FAR_KM = 4000; // from here on a flight takes the full 3.5 s
// The flight to the first story facility (PLAN.md 9.7): 4.5 s, zoom 7.5, pitch 50.
const STORY_ZOOM = 7.5;
const STORY_PITCH_DEG = 50;
const SETTLE_MS = 600; // easing the camera back when the panel closes
const EXPLORE_ZOOM_STEPS = 0.4; // zooming in this far counts as leaving the opening view

const NO_PADDING: PaddingOptions = { top: 0, right: 0, bottom: 0, left: 0 };
const easeOut = (t: number) => 1 - (1 - t) ** 3;
const easeInOut = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);

/** Zoom at which the globe's diameter is about `diameterPx`. */
function zoomForDiameter(diameterPx: number): number {
  // At zoom z the equator is 512 * 2^z px long, so the diameter is that divided by pi.
  return Math.log2((diameterPx * Math.PI) / 512);
}

/** The opening view: the globe above the hero lines, as large as the window allows. */
function openingView(el: HTMLElement): { zoom: number; padding: PaddingOptions } {
  const w = el.clientWidth;
  const h = el.clientHeight;
  const hero = heroHeightPx(w, h);
  const diameter = Math.min(GLOBE_FILL * Math.min(w, h), h - hero - GLOBE_TOP_MARGIN_PX);
  // Bottom padding lifts the globe's centre, so it clears the hero text.
  return { zoom: zoomForDiameter(diameter), padding: { ...NO_PADDING, bottom: hero } };
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
  /** The facility the intro's long flight is heading for, while that flight is under way. */
  storyId?: string | null;
  /** Whether the intro plays. Read once, when the map is made. */
  intro?: boolean;
  onSelect: (subjectId: string) => void;
  /** Called once, when the map has drawn its first complete frame. */
  onReady?: () => void;
  /** Called once, when the NO2 layer starts to fade in. */
  onNo2Visible?: () => void;
  /** Called once, when the visitor zooms in from the opening view. */
  onExplore?: () => void;
  /** The selected facility's daily plume frames, to be drawn around it. Null for none. */
  sitePlume?: SitePlumeSpec | null;
  /** Called when that plume appears on the map and when it goes. */
  onSitePlume?: (shown: boolean) => void;
}

export function Globe({
  findings,
  selected,
  storyId = null,
  intro = false,
  sitePlume = null,
  onSelect,
  onReady,
  onNo2Visible,
  onExplore,
  onSitePlume,
}: GlobeProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const stopSpinRef = useRef(() => {});
  const hasFlownRef = useRef(false);
  const [ready, setReady] = useState(false);
  const [markers, setMarkers] = useState<FacilityMarkers | null>(null);

  // Callbacks are kept in a ref so a new function from the parent never rebuilds the map.
  const callbacks = useRef({ onSelect, onReady, onNo2Visible, onExplore, onSitePlume });
  callbacks.current = { onSelect, onReady, onNo2Visible, onExplore, onSitePlume };
  const no2Ref = useRef<No2Layer | null>(null);
  const introRef = useRef(intro);
  const storyIdRef = useRef(storyId);
  storyIdRef.current = storyId;

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

  // So does its own plume, where the facility has daily frames.
  useEffect(() => {
    if (!ready) return;
    no2Ref.current?.setSitePlume(sitePlume, (shown) => callbacks.current.onSitePlume?.(shown));
  }, [ready, sitePlume]);

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
    const story = storyIdRef.current === selected.subject.id;
    const centre = new maplibregl.LngLat(selected.subject.lon, selected.subject.lat);
    // A facility with a satellite estimate has its own plume to show, so the camera goes closer.
    const zoom = Math.max(map.getZoom(), story || selected.observed ? STORY_ZOOM : ARRIVAL_ZOOM);
    const pitch = story ? STORY_PITCH_DEG : ARRIVAL_PITCH_DEG;
    const camera = { center: centre, zoom, pitch, padding: panelPadding(el) };
    if (reducedMotion) {
      map.jumpTo(camera);
      return;
    }
    if (story) {
      // One long, even move: slow away, glide, slow in.
      map.flyTo({ ...camera, duration: STORY_FLIGHT_MS, easing: easeInOut });
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
    const opening = openingView(el);
    const startZoom = opening.zoom;
    const playIntro = introRef.current && !reducedMotion;

    const map = new maplibregl.Map({
      container: el,
      style: nightStyle,
      center: playIntro ? [START[0] + INTRO_START_EAST_DEG, START[1]] : START,
      zoom: playIntro ? startZoom - INTRO_PULL_BACK_ZOOM : startZoom,
      minZoom: 0.5,
      maxPitch: 60,
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      // The NO2 layer is drawn by deck.gl, which has no map source to carry its credit.
      attributionControl: { compact: true, customAttribution: NO2_ATTRIBUTION },
    });
    mapRef.current = map;
    // Dev server only: a handle on the map for the browser console. Not in production builds.
    if (import.meta.env.DEV) (window as unknown as { __orbytMap?: maplibregl.Map }).__orbytMap = map;
    map.setPadding(opening.padding);

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

    // Slow rotation until the first touch, click, scroll or key press. During the intro the
    // camera also drifts in: each one-second step of the spin ends at the zoom the push-in has
    // reached by then.
    let spinning = !reducedMotion;
    let pushInStarted = 0;

    const zoomAt = (now: number): number => {
      if (!playIntro) return startZoom;
      const t = Math.min(1, (now - pushInStarted) / INTRO_PUSH_IN_MS);
      return startZoom - INTRO_PULL_BACK_ZOOM * (1 - easeOut(t));
    };

    const spin = () => {
      if (!spinning || !pushInStarted) return; // not before the first complete frame
      const centre = map.getCenter();
      map.easeTo({
        center: [centre.lng - SPIN_DEG_PER_S, centre.lat],
        zoom: zoomAt(performance.now() + 1000),
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

    map.once("load", () => {
      no2Ref.current = addNo2Layer(map, {
        beforeId: FIRST_OVERLAY_LAYER_ID,
        reducedMotion,
        onVisible: () => callbacks.current.onNo2Visible?.(),
      });
      setReady(true);
      callbacks.current.onReady?.();
      pushInStarted = performance.now();
      spin();
    });

    map.on("moveend", spin);
    el.addEventListener("pointerdown", stopSpin);
    el.addEventListener("wheel", stopSpin, { passive: true });
    el.addEventListener("keydown", stopSpin);

    return () => {
      no2Ref.current?.remove();
      no2Ref.current = null;
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
    <div className="globe-layer absolute inset-0">
      <div
        ref={container}
        className="h-full w-full"
        role="application"
        aria-label="Interactive globe. Drag to rotate, scroll or pinch to zoom."
      />
    </div>
  );
}
