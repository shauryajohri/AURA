// AURA's mini keyboard: a small always-on-top plate in a corner of the
// screen whose keys light up as she types, with the word she's typing on its
// horizon line. Drag it anywhere; it settles into the nearest corner and
// remembers it. Right-click to tuck it away until she next types.
//
// It never takes focus (her keystrokes must land in the app she's typing
// into), so dragging is done by hand over IPC, like the orb.
const { BrowserWindow, Menu, app, ipcMain, screen } = require("electron");
const path = require("path");
const fs = require("fs");

const W = 332;          // window, including room for the plate's shadow
const H = 196;
const MARGIN = 10;      // gap between the window and the screen corner

function createKeyboard({ onMoved }) {
  const file = path.join(app.getPath("userData"), "keyboard.json");
  let cfg = { corner: "bottom-left", hidden: false };
  try {
    cfg = { ...cfg, ...JSON.parse(fs.readFileSync(file, "utf8")) };
  } catch { /* first run */ }
  const save = () => {
    try { fs.writeFileSync(file, JSON.stringify(cfg)); } catch { /* read-only profile */ }
  };

  let win = null;
  let dragFrom = null;
  const alive = () => win && !win.isDestroyed();

  function cornerPos(corner, wa = screen.getPrimaryDisplay().workArea) {
    const left = corner.endsWith("left");
    const top = corner.startsWith("top");
    return {
      x: left ? wa.x + MARGIN : wa.x + wa.width - W - MARGIN,
      y: top ? wa.y + MARGIN : wa.y + wa.height - H - MARGIN,
    };
  }

  // Fixed-size setBounds only: a bare setPosition makes the window swell at
  // 125% scaling (seen with the orb).
  function place(x, y) {
    if (alive()) win.setBounds({ x: Math.round(x), y: Math.round(y), width: W, height: H });
  }

  function glide(to) {
    const from = win.getBounds();
    const t0 = Date.now();
    const step = () => {
      if (!alive()) return;
      const t = Math.min(1, (Date.now() - t0) / 240);
      const e = 1 - Math.pow(1 - t, 3);
      place(from.x + (to.x - from.x) * e, from.y + (to.y - from.y) * e);
      if (t < 1) setTimeout(step, 16);
      else onMoved?.();
    };
    step();
  }

  function snap() {
    const b = win.getBounds();
    const wa = screen.getDisplayMatching(b).workArea;
    const left = b.x + W / 2 < wa.x + wa.width / 2;
    const top = b.y + H / 2 < wa.y + wa.height / 2;
    cfg.corner = `${top ? "top" : "bottom"}-${left ? "left" : "right"}`;
    save();
    glide(cornerPos(cfg.corner, wa));
  }

  function show() {
    if (!alive()) return;
    win.showInactive();
    win.setAlwaysOnTop(true, "floating");
  }

  function build() {
    const at = cornerPos(cfg.corner);
    win = new BrowserWindow({
      width: W,
      height: H,
      x: at.x,
      y: at.y,
      title: "AURA keyboard",
      frame: false,
      transparent: true,
      backgroundColor: "#00000000",
      hasShadow: false,
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      focusable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      show: false,
      webPreferences: {
        preload: path.join(__dirname, "keyboard-preload.cjs"),
        contextIsolation: true,
        nodeIntegration: false,
        backgroundThrottling: false,
      },
    });
    win.setAlwaysOnTop(true, "floating");
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    win.webContents.on("will-navigate", (e) => e.preventDefault());
    win.loadFile(path.join(__dirname, "keyboard.html"));
    win.webContents.once("did-finish-load", () => {
      if (!cfg.hidden) show();
      onMoved?.();
    });
  }

  const fromKb = (e) => alive() && e.sender === win.webContents;
  ipcMain.on("kb:drag-start", (e) => {
    if (fromKb(e)) dragFrom = win.getBounds();
  });
  ipcMain.on("kb:drag-move", (e, dx, dy) => {
    if (fromKb(e) && dragFrom) place(dragFrom.x + Number(dx), dragFrom.y + Number(dy));
  });
  ipcMain.on("kb:drag-end", (e) => {
    if (!fromKb(e) || !dragFrom) return;
    dragFrom = null;
    snap();
  });
  ipcMain.on("kb:menu", (e) => {
    if (!fromKb(e)) return;
    Menu.buildFromTemplate([
      {
        label: "Hide until she types",
        click: () => {
          cfg.hidden = true;
          save();
          win.hide();
          onMoved?.();
        },
      },
    ]).popup({ window: win });
  });

  const refit = () => {
    if (!alive()) return;
    const p = cornerPos(cfg.corner);
    place(p.x, p.y);
    onMoved?.();
  };
  screen.on("display-metrics-changed", refit);
  screen.on("display-added", refit);
  screen.on("display-removed", refit);

  build();

  return {
    send(ev) {
      if (!alive()) return;
      // Tucked away? Her typing brings it back.
      if (ev.kind === "type" && !win.isVisible()) {
        cfg.hidden = false;
        save();
        show();
        onMoved?.();
      }
      win.webContents.send("kb:event", ev);
    },
    /** She's about to click something under the keyboard: out of the way
     *  for a moment, then back. */
    dodge() {
      if (!alive() || !win.isVisible()) return;
      win.hide();
      setTimeout(() => { if (!cfg.hidden) show(); }, 1600);
    },
    /** Where her cursor rests, in screen DIPs: on the plate's top-right
     *  corner, like a hand on the keys. Null while the keyboard is hidden. */
    rest() {
      if (!alive() || !win.isVisible()) return null;
      const b = win.getBounds();
      return { x: b.x + W - 40, y: b.y + 30 };
    },
    destroy() {
      screen.off("display-metrics-changed", refit);
      screen.off("display-added", refit);
      screen.off("display-removed", refit);
      for (const ch of ["kb:drag-start", "kb:drag-move", "kb:drag-end", "kb:menu"]) ipcMain.removeAllListeners(ch);
      if (alive()) win.destroy();
      win = null;
    },
  };
}

module.exports = { createKeyboard };
