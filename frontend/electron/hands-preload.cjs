// Bridge for the ghost-cursor layer (hands.html): it only listens.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hands", {
  onEvent: (cb) => ipcRenderer.on("hands:event", (_e, ev) => cb(ev)),
});
