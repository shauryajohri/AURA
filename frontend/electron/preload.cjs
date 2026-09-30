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
  // Links in chat. Without this an <a href> NAVIGATES THIS WINDOW — the whole
  // UI is replaced by the website and the socket to the brain dies with it.
  openExternal: (url) => ipcRenderer.send("shell:open-external", String(url)),
  // The Domain's Run — a website or saved PDF in its own app-like window.
  openWindow: (url, title) => ipcRenderer.send("domain:open-window", String(url), String(title || "")),
  // The Domain's Folder button: Windows' folder picker, resolves to paths.
  pickFolders: () => ipcRenderer.invoke("dialog:pick-folders"),
  // The floating orb (electron/orb.cjs) mirrors AURA's state while she's
  // minimized or covered, and holds anything she says while you're away.
  orbState: (state) => ipcRenderer.send("orb:state", String(state)),
  orbListening: (on) => ipcRenderer.send("orb:listening", !!on),
  orbVisible: (visible) => ipcRenderer.send("orb:visible", !!visible),
  orbNotify: (text) => ipcRenderer.send("orb:notify", String(text).slice(0, 300)),
});
