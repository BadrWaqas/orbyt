import type { Basis } from "./types";

// PLAN.md 9.9: tonnes with thousands separators and no decimals.
const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

export function formatTonnes(tonnes: number): string {
  return whole.format(tonnes);
}

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

/** "PL" to "Poland". Falls back to the code if the browser does not know it. */
export function countryName(iso2: string): string {
  try {
    return regionNames.of(iso2) ?? iso2;
  } catch {
    return iso2;
  }
}

/** How a reported value was obtained, as the register flags it. */
export const BASIS_LABEL: Record<Basis, string> = {
  measured: "Measured",
  calculated: "Calculated",
  estimated: "Estimated",
  stated: "Stated",
  unknown: "Not published",
};

/** One decimal, for hours, metres per second and mol per second. */
const oneDecimal = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formatOneDecimal(value: number): string {
  return oneDecimal.format(value);
}

const dayMonthYear = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "2024-05-14" to "14 May 2024". */
export function formatDay(isoDate: string): string {
  return dayMonthYear.format(new Date(`${isoDate}T00:00:00Z`));
}

const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];

/** Compass direction in words for a bearing in degrees clockwise from north. */
export function compassWord(deg: number): string {
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}

/** A ratio with one decimal and a multiplication sign: "1.1x" in the plan's wording (PLAN.md 9.9). */
export function formatRatio(value: number): string {
  return `${oneDecimal.format(value)}\u00d7`;
}

/** "1.1x reported (0.6 to 2.3)", the text beside the gap bar. */
export function ratioText(r: { value: number; lo: number; hi: number }): string {
  return `${formatRatio(r.value)} reported (${oneDecimal.format(r.lo)} to ${oneDecimal.format(r.hi)})`;
}
