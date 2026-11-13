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
