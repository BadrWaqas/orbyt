
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import type { Plugin } from "vite";

/**
 * Tells index.html the file name of the map's chunk (PLAN.md 9.10). The app loads the map after
 * it has started, which puts one more round trip between the first paint and the live globe. The
 * page's own script asks for the chunk as soon as it knows the route needs it, so it downloads
 * beside the app. In the dev server there is no chunk and the placeholder becomes empty.
 */
function nameGlobeChunk(): Plugin {
  return {
    name: "orbyt-name-globe-chunk",
    transformIndexHtml: {
      order: "post",
      handler(html, context) {
        const chunk = Object.values(context.bundle ?? {}).find(
          (file) => file.type === "chunk" && file.name === "Globe",
        );
        return html.replace("__GLOBE_CHUNK__", chunk ? `/${chunk.fileName}` : "");
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), nameGlobeChunk()],
});
