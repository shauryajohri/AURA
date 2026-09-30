// The floating AURA orb — a small always-on-top window that stands in for
// AURA whenever she's out of sight: minimized, or covered by another window.
// Click it and AURA comes back; drag it and it glides to the nearest screen
// edge; right-click for size and options. It glows with her live state
// (thinking / speaking / listening) and flags anything she said while hidden.
//
// This replaces the PySide orb (ui/orb.py) that went away with the Qt app.
const { BrowserWindow, Menu, app, ipcMain, screen } = require("electron");
const path = require("path");
const fs = require("fs");

const SIZES = { small: 72, medium: 96, large: 128 };
const MARGIN = 16;        // resting gap between the orb and a screen edge
const BLUR_DELAY = 350;   // ms — ignore focus hopping between AURA's own windows

function createOrb({ getMain, summon, quit }) {
  const file = path.join(app.getPath("userData"), "orb.json");
  let cfg = { size: "medium", x: null, y: null, always: false };
  try {
    cfg = { ...cfg, ...JSON.parse(fs.readFileSync(file, "utf8")) };
  } catch { /* first run — defaults */ }
  const save = () => {
    try { fs.writeFileSync(file, JSON.stringify(cfg)); } catch { /* read-only profile */ }
  };

  let win = null;
  let blurTimer = null;
  let settleTimer = null;
  let dragFrom = null;
  // Whether AURA's page can actually be seen. Chromium tracks real window
  // occlusion on Windows, so a window covering AURA makes this false even
  // when the focus events say otherwise.
  let mainVisible = true;
  let snoozed = false;   // "Hide until AURA is minimized again"
  const status = { state: "idle", listening: false, unread: false, text: "" };

  const px = () => SIZES[cfg.size] || SIZES.medium;
  const alive = (w) => w && !w.isDestroyed();

  function defaultPos() {
    const wa = screen.getPrimaryDisplay().workArea;
    return { x: wa.x + wa.width - px() - MARGIN, y: wa.y + wa.height - px() - MARGIN };
  }

  // A saved spot on a monitor that's since been unplugged would strand the orb.
  function onScreen(x, y) {
    return screen.getAllDisplays().some(({ workArea: w }) =>
      x >= w.x - 4 && y >= w.y - 4 && x + px() <= w.x + w.width + 4 && y + px() <= w.y + w.height + 4);
  }

  function build() {
    const at = cfg.x != null && cfg.y != null && onScreen(cfg.x, cfg.y) ? { x: cfg.x, y: cfg.y } : defaultPos();
    win = new BrowserWindow({
      width: px(),
      height: px(),
      x: at.x,
      y: at.y,
      title: "AURA orb",
      frame: false,
      transparent: true,
      backgroundColor: "#00000000",
      hasShadow: false,
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      show: false,
      webPreferences: {
        preload: path.join(__dirname, "orb-preload.cjs"),
        contextIsolation: true,
        nodeIntegration: false,
        // it has to keep glowing while every other window has focus
        backgroundThrottling: false,
      },
    });
    win.setAlwaysOnTop(true, "floating");
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    win.webContents.on("will-navigate", (e) => e.preventDefault());
    win.webContents.on("did-finish-load", push);
    win.on("closed", () => { win = null; });
    win.loadFile(path.join(__dirname, "orb.html"));
  }

  function push() {
    if (alive(win)) win.webContents.send("orb:update", { ...status, size: px() });
  }

  function reveal() {
    if (snoozed) return;
    if (!alive(win)) build();
    const show = () => {
      if (!alive(win)) return;
      if (!win.isVisible()) win.showInactive();   // never steal focus from what you're doing
      win.setAlwaysOnTop(true, "floating");      // Windows drops topmost now and then
      push();
    };
    if (win.webContents.isLoading()) win.webContents.once("did-finish-load", show);
    else show();
  }

  function conceal() {
    if (cfg.always) return;
    if (alive(win) && win.isVisible()) win.hide();
  }

  // ── what the main window is doing ───────────────────────────────────────
  // Only step aside once AURA is really back: focused AND visible. Windows
  // can refuse to bring a window forward, and Electron may still report it
  // focused — hiding the orb then would leave AURA covered with no way back.
  function settle() {
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      const main = getMain();
      if (!alive(main) || main.isMinimized() || !main.isFocused() || !mainVisible) return;
      status.unread = false;
      push();
      conceal();
    }, 400);
  }

  function onMainShown() {
    clearTimeout(blurTimer);
    snoozed = false;
    settle();
  }

  function onMainHidden() {
    clearTimeout(blurTimer);
    clearTimeout(settleTimer);
    reveal();
  }

  function onMainBlurred() {
    clearTimeout(blurTimer);
    blurTimer = setTimeout(() => {
      const main = getMain();
      if (!alive(main)) return;
      if (main.isFocused() || main.webContents.isDevToolsFocused()) return;
      reveal();
    }, BLUR_DELAY);
  }

  // ── moving it ───────────────────────────────────────────────────────────
  // Always position AND size together: on Windows at fractional display
  // scaling (125%, 150%) a bare setPosition() rounds the size up a little
  // every call, and a dragged orb visibly swells.
  function place(x, y) {
    if (!alive(win)) return;
    win.setBounds({ x: Math.round(x), y: Math.round(y), width: px(), height: px() });
  }

  function glide(x0, y0, x1, y1) {
    const t0 = Date.now();
    const step = () => {
      if (!alive(win)) return;
      const t = Math.min(1, (Date.now() - t0) / 220);
      const e = 1 - Math.pow(1 - t, 3);
      place(x0 + (x1 - x0) * e, y0 + (y1 - y0) * e);
      if (t < 1) setTimeout(step, 16);
    };
    step();
  }

  function snap() {
    if (!alive(win)) return;
    const b = win.getBounds();
    const s = px();
    const wa = screen.getDisplayMatching(b).workArea;
    const toLeft = b.x + s / 2 < wa.x + wa.width / 2;
    const x = toLeft ? wa.x + MARGIN : wa.x + wa.width - s - MARGIN;
    const y = Math.min(Math.max(b.y, wa.y + MARGIN), wa.y + wa.height - s - MARGIN);
    glide(b.x, b.y, x, y);
    cfg.x = x;
    cfg.y = y;
    save();
  }

  function resize(size) {
    cfg.size = size;
    save();
    if (!alive(win)) return;
    const b = win.getBounds();
    const s = px();
    // grow/shrink around the centre, then settle against the edge again
    win.setBounds({ x: Math.round(b.x + (b.width - s) / 2), y: Math.round(b.y + (b.height - s) / 2), width: s, height: s });
    push();
    snap();
  }

  function open() {
    status.unread = false;
    push();
    summon();
  }

  function menu() {
    return Menu.buildFromTemplate([
      { label: "Open AURA", click: open },
      { type: "separator" },
      {
        label: "Size",
        submenu: Object.keys(SIZES).map((k) => ({
          label: k[0].toUpperCase() + k.slice(1),
          type: "radio",
          checked: cfg.size === k,
          click: () => resize(k),
        })),
      },
      {
        label: "Keep the orb on screen",
        type: "checkbox",
        checked: cfg.always,
        click: (item) => {
          cfg.always = item.checked;
          save();
          if (cfg.always) reveal();
          else if (alive(getMain()) && getMain().isFocused()) conceal();
        },
      },
      {
        label: "Hide until AURA is minimized again",
        enabled: !cfg.always,
        click: () => {
          snoozed = true;
          if (alive(win)) win.hide();
        },
      },
      { type: "separator" },
      { label: "Quit AURA", click: quit },
    ]);
  }

  // ── messages from the orb page ─────────────────────────────────────────
  const fromOrb = (e) => alive(win) && e.sender === win.webContents;
  const fromMain = (e) => alive(getMain()) && e.sender === getMain().webContents;

  ipcMain.on("orb:open", (e) => { if (fromOrb(e)) open(); });
  ipcMain.on("orb:drag-start", (e) => {
    if (!fromOrb(e)) return;
    const [x, y] = win.getPosition();
    dragFrom = { x, y };
  });
  ipcMain.on("orb:drag-move", (e, dx, dy) => {
    if (!fromOrb(e) || !dragFrom) return;
    place(dragFrom.x + Number(dx || 0), dragFrom.y + Number(dy || 0));
  });
  ipcMain.on("orb:drag-end", (e) => {
    if (!fromOrb(e)) return;
    dragFrom = null;
    snap();
  });
  ipcMain.on("orb:menu", (e) => { if (fromOrb(e)) menu().popup({ window: win }); });

  // ── AURA's live state, from the main window's renderer ──────────────────
  ipcMain.on("orb:state", (e, state) => {
    if (!fromMain(e)) return;
    status.state = ["idle", "thinking", "speaking"].includes(state) ? state : "idle";
    push();
  });
  ipcMain.on("orb:listening", (e, on) => {
    if (!fromMain(e)) return;
    status.listening = !!on;
    push();
  });
  // AURA's page became hidden (covered, minimized) or visible again.
  ipcMain.on("orb:visible", (e, visible) => {
    if (!fromMain(e)) return;
    mainVisible = !!visible;
    if (!mainVisible) {
      clearTimeout(settleTimer);
      reveal();
    } else {
      settle();
    }
  });
  // Something AURA said while you were elsewhere — the orb holds it for you.
  ipcMain.on("orb:notify", (e, text) => {
    if (!fromMain(e)) return;
    const main = getMain();
    if (main.isFocused() && !main.isMinimized()) return;
    status.unread = true;
    status.text = String(text || "").replace(/\s+/g, " ").slice(0, 160);
    push();
  });

  return {
    onMainShown,
    onMainHidden,
    onMainBlurred,
    /** Show it now if AURA opened behind something and never got focus. */
    checkInitialFocus() {
      const main = getMain();
      if (cfg.always) reveal();
      else if (alive(main) && !main.isFocused()) reveal();
    },
    destroy() {
      clearTimeout(blurTimer);
      clearTimeout(settleTimer);
      if (alive(win)) win.destroy();
      win = null;
    },
  };
}

module.exports = { createOrb };
