import { NO2_ATTRIBUTION, NO2_YEAR } from "../modules/pollution-hunter/no2";

// The words the site repeats on every page: the standing disclaimer (PLAN.md 7.2, rule 9), the
// contact address (rule 8) and the credits each data source asks for (PLAN.md 7.3). The full
// terms of every source are in DATA_LICENSES.md.

export const CONTACT_EMAIL = "badrwaqas07@gmail.com";

export const STANDING_LINE =
  "Orbyt Earth is an independent student research project. Estimates are uncertain and are not findings of non-compliance.";

export const ERA5_ATTRIBUTION = `Contains modified Copernicus Climate Change Service information ${NO2_YEAR}`;

export const LICENCES_URL = "https://github.com/BadrWaqas/orbyt/blob/main/DATA_LICENSES.md";

/** One credit per source in use, in the order a reader meets them. Plain text, no markup. */
export const CREDITS: readonly { label: string; text: string }[] = [
  { label: "Satellite NO2", text: NO2_ATTRIBUTION },
  {
    label: "Wind",
    text: `${ERA5_ATTRIBUTION}. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains`,
  },
  { label: "Reported emissions, Europe", text: "European Environment Agency, Industrial Reporting database" },
  {
    label: "Reported emissions, US",
    text: "US EPA Clean Air Markets Program Data and National Emissions Inventory, with the CAMPD series read from PUDL (Catalyst Cooperative, CC BY 4.0)",
  },
  { label: "Base map", text: "OpenStreetMap contributors, OpenFreeMap, OpenMapTiles" },
  {
    label: "Night lights",
    text: "NASA Black Marble (VIIRS), served through NASA Global Imagery Browse Services (GIBS)",
  },
];
