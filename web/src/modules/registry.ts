// Module registry (PLAN.md 2.6). Each module adds its descriptor here.
// Pollution Hunter is wired into the app directly for now. The full descriptor (layers, Panel,
// Legend) arrives when a second module needs the shared shell.

export const modules: readonly { id: string; title: string }[] = [
  { id: "pollution-hunter", title: "Pollution Hunter" },
];
