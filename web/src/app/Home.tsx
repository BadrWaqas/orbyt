import type { CSSProperties, ReactNode } from "react";

import { modules, type HueName, type ModuleEntry } from "../modules/registry";
import type { HomeLayout } from "./layout";
import { Link } from "./Link";

// The home screen: the Earth turning in space, the name and the tagline, and the six modules as
// glowing cards around the globe, each in its own hue (PLAN.md 9.2). The live module opens with a
// dive toward the Earth. The others are dimmed and marked "soon".
//
// The pieces sit at different depths, so app/App.tsx places them: the halo and the far half of
// the orbit behind the map, the near half of the orbit and the cards in front of it.
// Styles are in design/index.css under "The home screen".

// The orbit drawn around the Earth, as shares of the globe's diameter.
const ORBIT_RX = 0.575;
const ORBIT_RY = 0.19;

const css = (vars: Record<string, string>) => vars as CSSProperties;

/**
 * The light around the Earth's limb, and a dark sphere that stands in for the Earth until the
 * live map has drawn its first frame. The light takes the hue of the module the pointer is on.
 */
export function EarthHalo({ hue }: { hue: HueName | null }) {
  return (
    <div
      className="earth-halo"
      aria-hidden="true"
      style={hue ? css({ "--halo": `var(--hue-${hue}-glow)` }) : undefined}
    >
      <div className="earth-poster" />
    </div>
  );
}

/**
 * One half of the orbit and of the satellite on it. The far half is drawn behind the globe and
 * the near half in front, so the satellite passes behind the Earth once each time round.
 */
export function OrbitRing({ half, diameter }: { half: "far" | "near"; diameter: number }) {
  const rx = Math.round(diameter * ORBIT_RX);
  const ry = Math.round(diameter * ORBIT_RY);
  // From the right-hand tip, round the near side first.
  const track = `path("M ${2 * rx} ${ry} A ${rx} ${ry} 0 1 1 0 ${ry} A ${rx} ${ry} 0 1 1 ${2 * rx} ${ry}")`;
  return (
    <div
      className="orbit-ring home-item"
      data-half={half}
      aria-hidden="true"
      style={{ width: 2 * rx, height: 2 * ry }}
    >
      <svg width={2 * rx} height={2 * ry} viewBox={`0 0 ${2 * rx} ${2 * ry}`}>
        <ellipse cx={rx} cy={ry} rx={rx - 0.5} ry={ry - 0.5} />
      </svg>
      <span className="orbit-satellite" style={{ offsetPath: track }} />
    </div>
  );
}

const ICONS: Record<HueName, ReactNode> = {
  // A stack and its plume.
  no2: (
    <>
      <path d="M3 21h18" />
      <path d="M6 21V9h3.5v12" />
      <path d="M9.5 15l4.5-3v3l4.5-3v9" />
      <path d="M7.5 6c.9-1.6 2.6-2 4-1.1 1.3.8 3 .6 4-.6" />
    </>
  ),
  // A building that is only an outline.
  ghost: (
    <>
      <path d="M3 21h18" />
      <path d="M5 21V5.5L13 3v18" strokeDasharray="2.2 2.2" />
      <path d="M13 9h6v12" />
      <path d="M8 8.5h2M8 12h2M8 15.5h2" />
    </>
  ),
  forest: (
    <>
      <path d="M12 3l5 7h-3l4 6H6l4-6H7z" />
      <path d="M12 16v5" />
      <path d="M8 21h8" />
    </>
  ),
  // One carbon, four hydrogens.
  methane: (
    <>
      <circle cx="12" cy="12" r="2.7" />
      <circle cx="5.2" cy="5.2" r="1.7" />
      <circle cx="18.8" cy="5.2" r="1.7" />
      <circle cx="5.2" cy="18.8" r="1.7" />
      <circle cx="18.8" cy="18.8" r="1.7" />
      <path d="M10 10L6.5 6.5M14 10l3.5-3.5M10 14l-3.5 3.5M14 14l3.5 3.5" />
    </>
  ),
  flaring: (
    <>
      <path d="M12 3c.5 3.2 4.5 5.2 4.5 9.8A4.6 4.6 0 0 1 12 17.5a4.6 4.6 0 0 1-4.5-4.7c0-1.8.9-3 1.9-4 .3 1.4 1 2.2 1.9 2.4C10.8 8.6 11 5.4 12 3z" />
      <path d="M12 17.5V21M8.5 21h7" />
    </>
  ),
  irrigation: (
    <>
      <path d="M12 3.5c3 3.6 5.5 6.6 5.5 9.9a5.5 5.5 0 0 1-11 0c0-3.3 2.5-6.3 5.5-9.9z" />
      <path d="M9.4 13.8a2.7 2.7 0 0 0 2.6 2.6" />
    </>
  ),
};

/** Chemical formulas with their subscripts. */
function chem(text: string): ReactNode {
  return text.split(/(NOx|NO2)/).map((part, i) =>
    part === "NOx" || part === "NO2" ? (
      <span key={i}>
        NO<sub>{part.slice(2)}</sub>
      </span>
    ) : (
      part
    ),
  );
}

interface CardProps {
  module: ModuleEntry;
  onEnter: () => void;
  onHue: (hue: HueName | null) => void;
}

function ModuleCard({ module, onEnter, onHue }: CardProps) {
  const live = module.status === "live";
  const style = css({
    "--mark": `var(--hue-${module.hue}-mark)`,
    "--glow": `var(--hue-${module.hue}-glow)`,
  });
  const light = {
    onPointerEnter: () => onHue(module.hue),
    onPointerLeave: () => onHue(null),
    onFocus: () => onHue(module.hue),
    onBlur: () => onHue(null),
  };
  // A module chip always shows an icon and a name next to its colour (PLAN.md 9.2).
  const body = (
    <>
      <svg className="module-icon" width="28" height="28" viewBox="0 0 24 24" aria-hidden="true">
        {ICONS[module.hue]}
      </svg>
      <span className="module-name">{module.title}</span>
      <span className="module-status">
        {live && <span className="live-dot" aria-hidden="true" />}
        {live ? "Live" : "Soon"}
      </span>
      <span className="module-line">{chem(module.line)}</span>
      {live && (
        <svg className="module-arrow" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M3 8h9.5M8.5 4l4 4-4 4" />
        </svg>
      )}
    </>
  );
  if (!live) {
    return (
      <div className="module-card" data-status="soon" style={style} {...light}>
        {body}
      </div>
    );
  }
  return (
    <Link to="module" onNavigate={onEnter} className="module-card" data-status="live" style={style} {...light}>
      {body}
    </Link>
  );
}

interface Props {
  /** False while another view is on screen. The pieces then fall away and cannot be reached. */
  shown: boolean;
  layout: HomeLayout;
  /** The visitor opened the live module. */
  onEnter: () => void;
  /** The module the pointer or the keyboard focus is on, for the light around the Earth. */
  onHue: (hue: HueName | null) => void;
}

export function Home({ shown, layout, onEnter, onHue }: Props) {
  const orbit = layout.kind === "orbit";
  return (
    <section
      className="home"
      data-kind={layout.kind}
      aria-label="Home"
      aria-hidden={!shown}
      inert={!shown}
      style={css({ "--home-title-top": `${Math.round(layout.titleTop)}px` })}
    >
      <div className="home-flow">
        <div className="home-title home-item" style={css({ "--away": "translateY(18px)" })}>
          <h1 className="home-name">Orbyt Earth</h1>
          <p className="home-tagline">Fact-checking the world from space.</p>
        </div>
        <ul className="home-modules" aria-label="Modules">
          {modules.map((module, i) => {
            const slot = orbit ? layout.cards[i] : null;
            // On the way out the cards move away from the Earth, as if the camera passed them.
            const away = slot ? `translateX(${slot.side === "left" ? -40 : 40}px)` : "translateY(16px)";
            const order = slot ? i % 3 : i;
            return (
              <li
                key={module.id}
                className="module-slot"
                style={slot ? { left: slot.left, top: slot.middle, width: layout.cardWidth } : undefined}
              >
                <div
                  className="home-item"
                  style={css({ "--away": away, "--stagger": `${160 + order * 80}ms` })}
                >
                  <ModuleCard module={module} onEnter={onEnter} onHue={onHue} />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
