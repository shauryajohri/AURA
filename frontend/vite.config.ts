import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The brain's launch token (local_auth.py), for a plain browser on the dev
// server. Electron gets it over IPC instead, and the production build has no
// such route. Same-origin only: no CORS headers are sent, cross-site fetches
// are refused, and a non-localhost Host (DNS rebinding) is refused too.
const TOKEN_FILE = fileURLToPath(new URL("../memory/session.token", import.meta.url));
const LOCAL_HOST = /^(localhost|127\.0\.0\.1)(:\d+)?$/;

function auraToken(): Plugin {
  return {
    name: "aura-launch-token",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/__aura/token", (req, res) => {
        const site = req.headers["sec-fetch-site"];
        if (!LOCAL_HOST.test(req.headers.host ?? "") || (site && site !== "same-origin")) {
          res.statusCode = 403;
          res.end();
          return;
        }
        let token = "";
        try {
          token = readFileSync(TOKEN_FILE, "utf8").trim();
        } catch {
          /* brain not started yet */
        }
        res.statusCode = token ? 200 : 503;
        res.setHeader("Content-Type", "text/plain");
        res.setHeader("Cache-Control", "no-store");
        res.end(token);
      });
    },
  };
}

// base: "./" so the built assets load correctly from Electron's file:// origin.
// Two pages: the main face (index.html) and the desktop buddy (buddy.html),
// which Electron opens in its own transparent window.
export default defineConfig({
  plugins: [react(), auraToken()],
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
