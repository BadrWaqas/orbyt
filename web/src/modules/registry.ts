// Module registry (PLAN.md 2.6). Each module adds its entry here, in the fixed order of the six
// module hues (PLAN.md 9.2). The home screen shows them all: the live ones can be opened, the
// others are announced as "soon".
//
// Pollution Hunter is wired into the app directly for now. The full descriptor (layers, Panel,
// Legend) arrives when a second module needs the shared shell.

/** The six module hues, by the names their tokens carry in design/tokens.css. */
export type HueName = "no2" | "ghost" | "forest" | "methane" | "flaring" | "irrigation";

export interface ModuleEntry {
  id: string;
  title: string;
  hue: HueName;
  status: "live" | "soon";
  /** One line saying what record is checked against what instrument. */
  line: string;
}

export const modules: readonly ModuleEntry[] = [
  {
    id: "pollution-hunter",
    title: "Pollution Hunter",
    hue: "no2",
    status: "live",
    line: "Reported NOx, checked against satellite NO2.",
  },
  {
    id: "ghost-developments",
    title: "Ghost developments",
    hue: "ghost",
    status: "soon",
    line: "Occupancy claims, checked against night lights.",
  },
  {
    id: "deforestation",
    title: "Deforestation",
    hue: "forest",
    status: "soon",
    line: "Forest pledges, checked against tree cover loss.",
  },
  {
    id: "methane",
    title: "Methane",
    hue: "methane",
    status: "soon",
    line: "Methane plumes detected from orbit.",
  },
  {
    id: "flaring",
    title: "Flaring",
    hue: "flaring",
    status: "soon",
    line: "Reported flaring, checked against night-time heat.",
  },
  {
    id: "irrigation-ban-watch",
    title: "Irrigation ban watch",
    hue: "irrigation",
    status: "soon",
    line: "Irrigation bans, checked against field greenness.",
  },
];
