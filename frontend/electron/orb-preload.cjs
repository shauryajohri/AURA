// Bridge for the floating orb window (orb.html) — the only things it can do
// are ask to open AURA, move itself, and open its menu.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("orb", {
  onUpdate: (cb) => ipcRenderer.on("orb:update", (_e, status) => cb(status)),
  open: () => ipcRenderer.send("orb:open"),
  dragStart: () => ipcRenderer.send("orb:drag-start"),
  dragMove: (dx, dy) => ipcRenderer.send("orb:drag-move", dx, dy),
  dragEnd: () => ipcRenderer.send("orb:drag-end"),
  menu: () => ipcRenderer.send("orb:menu"),
});
