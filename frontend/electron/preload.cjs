// Preload — safe bridge between the renderer and Electron/Node.
// The WebSocket to the Python brain runs directly in the renderer.
const { contextBridge, ipcRenderer } = require("electron");

/** Subscribe to a main-process channel; returns the unsubscribe. */
function listen(channel, cb) {
  const handler = (_e, value) => cb(value);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

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
  // The desktop buddy (its own window). The main window uses relay/onChat;
  // the buddy window uses the rest. main.cjs checks which window sent what.
  buddy: {
    relay: (msg) => ipcRenderer.send("buddy:relay", msg),
    onChat: (cb) => listen("buddy:chat", cb),
    setEnabled: (on) => ipcRenderer.send("buddy:set-enabled", !!on),
    // Subscribing asks main to replay the current state, so nothing relayed
    // before the page was listening is lost.
    onUpdate: (cb) => {
      const off = listen("buddy:update", cb);
      ipcRenderer.send("buddy:ready");
      return off;
    },
    onCommand: (cb) => listen("buddy:cmd", cb),
    chat: (text) => ipcRenderer.send("buddy:chat", String(text)),
    move: (x, y) => ipcRenderer.send("buddy:move", Number(x), Number(y)),
    place: (x, y) => ipcRenderer.invoke("buddy:place", x, y),
    geom: () => ipcRenderer.invoke("buddy:geom"),
    setIgnoreMouse: (ignore) => ipcRenderer.send("buddy:ignore-mouse", !!ignore),
    focus: () => ipcRenderer.send("buddy:focus"),
    openMain: () => ipcRenderer.send("buddy:open-main"),
    menu: (opts) => ipcRenderer.send("buddy:menu", opts),
  },
});
