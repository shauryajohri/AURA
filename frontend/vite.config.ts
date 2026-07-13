import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so the built assets load correctly from Electron's file:// origin.
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
  },
});
