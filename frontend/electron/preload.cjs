// Preload — safe bridge between the renderer and Electron/Node.
// The WebSocket to the Python brain runs directly in the renderer.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aura", {
  version: "0.1.0",
  // Bridge server URL. Override in future via app config if needed.
  bridgeUrl: "ws://127.0.0.1:8760/ws",
  // Window controls for AURA's own chrome (frameless window).
  minimize: () => ipcRenderer.send("win:minimize"),
  close: () => ipcRenderer.send("win:close"),
});
