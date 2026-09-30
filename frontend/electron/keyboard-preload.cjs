// Bridge for the mini keyboard (keyboard.html): it hears her keystrokes and
// can move itself or open its menu. Nothing else.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kb", {
  onEvent: (cb) => ipcRenderer.on("kb:event", (_e, ev) => cb(ev)),
  dragStart: () => ipcRenderer.send("kb:drag-start"),
  dragMove: (dx, dy) => ipcRenderer.send("kb:drag-move", dx, dy),
  dragEnd: () => ipcRenderer.send("kb:drag-end"),
  menu: () => ipcRenderer.send("kb:menu"),
});
