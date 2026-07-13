// Preload — safe bridge between the renderer and Electron/Node.
// Nothing sensitive is exposed yet; the WebSocket to the Python brain runs
// directly in the renderer. Kept here so we have a seam for native calls later.
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("aura", {
  version: "0.1.0",
  // Bridge server URL. Override in future via app config if needed.
  bridgeUrl: "ws://127.0.0.1:8760/ws",
});
