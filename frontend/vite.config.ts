import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// base: "./" so the built assets load correctly from Electron's file:// origin.
// Two pages: the main face (index.html) and the desktop buddy (buddy.html),
// which Electron opens in its own transparent window.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        buddy: fileURLToPath(new URL("./buddy.html", import.meta.url)),
      },
    },
  },
});
