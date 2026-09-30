// AURA's ghost cursor: a transparent, click-through layer over the whole
// primary screen, where her own cursor lives while AURA is running. It rests
// on her mini keyboard (electron/keyboard.cjs), and when she works the PC (core/hands.py) it
// glides to what she's about to click, so you can watch her do it.
//
// The brain sends physical screen pixels; they're turned into this window's
// units here. The layer can never take focus or catch a click: her typing
// has to land in Windows' search, and your clicks have to reach your apps.
const { BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");
const { createKeyboard } = require("./keyboard.cjs");

function createHands({ fromMain }) {
  let win = null;
  let busy = false;
  const alive = () => win && !win.isDestroyed();
  // Her mini keyboard. When it moves, her resting hand moves with it.
  const keyboard = createKeyboard({
    onMoved: () => { if (!busy) send({ kind: "home", ...home(), ms: 500 }); },
  });

  function bounds() {
    const d = screen.getPrimaryDisplay();
    // 1px short of the full display: a window exactly the size of the screen
    // can be taken for a fullscreen app (Windows then hides the taskbar and
    // holds notifications).
    return { ...d.bounds, height: d.bounds.height - 1 };
  }

  function home() {
    const b = bounds();
    const rest = keyboard.rest();    // on the keys, when the keyboard is out
    if (rest) return { x: rest.x - b.x, y: rest.y - b.y };
    const wa = screen.getPrimaryDisplay().workArea;
    // left of where the orb rests, just above the taskbar
    return { x: wa.x + wa.width - b.x - 150, y: wa.y + wa.height - b.y - 58 };
  }

  function build() {
    win = new BrowserWindow({
      ...bounds(),
      title: "AURA cursor",
      frame: false,
      transparent: true,
      backgroundColor: "#00000000",
      hasShadow: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      focusable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      show: false,
      webPreferences: {
        preload: path.join(__dirname, "hands-preload.cjs"),
        contextIsolation: true,
        nodeIntegration: false,
        // it has to move while every other window has focus
        backgroundThrottling: false,
      },
    });
    win.setAlwaysOnTop(true, "screen-saver");
    win.setIgnoreMouseEvents(true);
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    win.webContents.on("will-navigate", (e) => e.preventDefault());
    win.loadFile(path.join(__dirname, "hands.html"));
    win.webContents.once("did-finish-load", () => {
      win.showInactive();
      // Created windows are fitted into the work area, which stops at the
      // taskbar (and so did she, right before Start). Stretch it once shown.
      win.setBounds(bounds());
      send({ kind: "home", ...home(), ms: 0 });
    });
  }

  function send(ev) {
    if (alive()) win.webContents.send("hands:event", ev);
  }

  /** Brain coordinates (physical px) → this window's CSS px. */
  function local(x, y) {
    const p = process.platform === "win32" ? screen.screenToDipPoint({ x, y }) : { x, y };
    const b = win.getBounds();
    return { x: p.x - b.x, y: p.y - b.y };
  }

  ipcMain.on("hands:event", (e, ev) => {
    if (!fromMain(e) || !alive() || !ev || typeof ev.kind !== "string") return;
    if (ev.kind === "move" || ev.kind === "click") {
      // The taskbar puts itself above every always-on-top window whenever
      // it's touched, and she'd vanish right as she reached Start. Take the
      // top back before each step.
      win.setAlwaysOnTop(true, "screen-saver");
      win.moveTop();
      send({ ...ev, ...local(Number(ev.x) || 0, Number(ev.y) || 0) });
    } else if (ev.kind === "home") {
      send({ kind: "home", ...home(), ms: 700 });
    } else if (ev.kind === "type") {
      const t = { kind: "type", text: String(ev.text || "").slice(0, 80), ms: Number(ev.ms) || 75 };
      send(t);
      keyboard.send(t);
    } else if (ev.kind === "dodge") {
      keyboard.dodge();
    } else if (ev.kind === "press") {
      keyboard.send({ kind: "press", key: String(ev.key || "") });
    } else if (ev.kind === "busy") {
      busy = !!ev.on;
      const b = { kind: "busy", on: busy, label: String(ev.label || "").slice(0, 60) };
      send(b);
      keyboard.send(b);
    }
  });

  // A monitor plugged in or the scaling changed: cover the screen again.
  const refit = () => {
    if (!alive()) return;
    win.setBounds(bounds());
    send({ kind: "home", ...home(), ms: 0 });
  };
  screen.on("display-metrics-changed", refit);
  screen.on("display-added", refit);
  screen.on("display-removed", refit);

  build();

  return {
    destroy() {
      screen.off("display-metrics-changed", refit);
      screen.off("display-added", refit);
      screen.off("display-removed", refit);
      ipcMain.removeAllListeners("hands:event");
      keyboard.destroy();
      if (alive()) win.destroy();
      win = null;
    },
  };
}

module.exports = { createHands };
