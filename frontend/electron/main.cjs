// Electron main process — the "body" that hosts the React "face".
// In dev it loads the Vite server; in prod (AURA_PROD=1 or packaged) it loads
// the built dist/index.html AND boots the Python brain itself, so a single
// double-click brings the whole of AURA to life — and closing the window
// puts her back to sleep (the brain is killed with the app).
const { app, BrowserWindow, ipcMain, Menu, screen, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");
const fs = require("fs");

const isDev = !app.isPackaged && process.env.AURA_PROD !== "1";

// Background videos must start on their own — never wait for a user gesture.
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

const REPO_ROOT = path.join(__dirname, "..", "..");
const BRAIN_PORT = 8760;

// ---------------------------------------------------------------------------
// The brain: spawn python server.py unless one is already listening.
// ---------------------------------------------------------------------------
let brainProc = null;

function pythonExe() {
  const venv = path.join(REPO_ROOT, "venv", "Scripts", "python.exe"); // Windows
  if (fs.existsSync(venv)) return venv;
  const venvNix = path.join(REPO_ROOT, "venv", "bin", "python");
  if (fs.existsSync(venvNix)) return venvNix;
  return "python"; // hope it's on PATH
}

function startBrainIfNeeded() {
  const probe = net.connect({ port: BRAIN_PORT, host: "127.0.0.1" });
  probe.once("connect", () => probe.destroy()); // already awake (dev server running)
  probe.once("error", () => {
    try {
      const logDir = path.join(REPO_ROOT, "logs");
      fs.mkdirSync(logDir, { recursive: true });
      const log = fs.openSync(path.join(logDir, "brain.log"), "a");
      brainProc = spawn(pythonExe(), ["server.py"], {
        cwd: REPO_ROOT,
        stdio: ["ignore", log, log],
        windowsHide: true,
      });
      brainProc.on("exit", () => { brainProc = null; });
    } catch (err) {
      console.error("[AURA] could not start the brain:", err);
    }
  });
}

function stopBrain() {
  if (!brainProc) return;
  try {
    if (process.platform === "win32") {
      // kill the whole tree — uvicorn spawns children
      spawn("taskkill", ["/pid", String(brainProc.pid), "/T", "/F"], { windowsHide: true });
    } else {
      brainProc.kill("SIGTERM");
    }
  } catch { /* already gone */ }
  brainProc = null;
}

// ---------------------------------------------------------------------------
// The face
// ---------------------------------------------------------------------------
Menu.setApplicationMenu(null); // AURA owns its chrome: no OS titlebar, no menu bar.

let mainWin = null;
let buddyWin = null;

const alive = (w) => !!w && !w.isDestroyed();

function createWindow() {
  const iconPath = path.join(__dirname, "aura.ico");
  const win = (mainWin = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    frame: false, // frameless — AURA renders its own minimize/close controls
    backgroundColor: "#05060f",
    show: false,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  }));

  // Always full: open maximized, and if anything un-maximizes it,
  // snap straight back. Minimize (to taskbar) still works.
  win.once("ready-to-show", () => {
    win.maximize();
    win.show();
  });
  win.on("unmaximize", () => win.maximize());

  // The desktop buddy stays on screen the whole time AURA runs — in front of
  // this window, other apps, and through a minimize. Only closing AURA, the
  // Settings switch, or its own "Hide until restart" puts it away.
  win.on("closed", () => {
    mainWin = null;
    // Closing AURA still puts her to sleep — the buddy must not keep the
    // app (and the brain) alive on its own.
    if (alive(buddyWin)) buddyWin.destroy();
  });

  // Belt and braces for links. The renderer routes clicks through the preload
  // bridge, but anything that still tries to open a window or navigate the app
  // away (a stray target=_blank, a middle-click) is intercepted here: the
  // window must never leave AURA's own UI, or the socket to the brain dies.
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    const here = isDev ? "http://localhost:5173" : "file://";
    if (!url.startsWith(here)) {
      e.preventDefault();
      openExternal(url);
    }
  });

  if (isDev) {
    win.loadURL("http://localhost:5173");
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

// ---------------------------------------------------------------------------
// The buddy — a pixel AURA that hangs out on the taskbar edge.
// A small transparent, always-on-top window. It ignores the mouse (clicks
// fall through to whatever is underneath) except while the pointer is over
// the sprite or its speech bubble; the renderer flips that per mousemove.
// It has no socket of its own: the main window relays AURA's state to it
// and carries its chat, so the brain sees one client and the main
// transcript keeps every exchange.
// ---------------------------------------------------------------------------
const BUDDY_W = 280; // keep in sync with src/buddy/win.ts
const BUDDY_H = 270;
let buddyDismissed = false; // "Hide until restart" from the buddy's menu
const buddyLast = {};       // last state/presence/status, replayed when the buddy (re)loads

// Settings → General → desktop buddy. The switch lives in the brain's
// app_settings, but the brain can still be booting when the buddy could
// first appear, so main keeps its own copy of the last value it was sent.
const BUDDY_PREFS = path.join(app.getPath("userData"), "buddy.json");
let buddyEnabled = readBuddyEnabled();

function readBuddyEnabled() {
  try {
    return JSON.parse(fs.readFileSync(BUDDY_PREFS, "utf8")).enabled !== false;
  } catch {
    return true; // never saved — on by default
  }
}

function createBuddyWindow() {
  const wa = screen.getPrimaryDisplay().workArea;
  const win = (buddyWin = new BrowserWindow({
    width: BUDDY_W,
    height: BUDDY_H,
    x: wa.x + wa.width - BUDDY_W - 40,
    y: wa.y + wa.height - BUDDY_H,
    transparent: true,
    backgroundColor: "#00000000",
    frame: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  }));
  win.setAlwaysOnTop(true, "floating");
  win.setIgnoreMouseEvents(true, { forward: true });

  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e) => e.preventDefault());
  win.once("ready-to-show", showBuddy); // out as soon as AURA launches
  win.on("closed", () => { buddyWin = null; });

  if (isDev) win.loadURL("http://localhost:5173/buddy.html");
  else win.loadFile(path.join(__dirname, "..", "dist", "buddy.html"));
}

function showBuddy() {
  if (!buddyEnabled || buddyDismissed || !alive(buddyWin) || buddyWin.isVisible()) return;
  buddyWin.showInactive();
  buddyWin.setAlwaysOnTop(true, "floating"); // Windows can drop topmost across a hide
}

function hideBuddy() {
  if (!alive(buddyWin) || !buddyWin.isVisible()) return;
  // Hidden mid-hover it would come back swallowing clicks — reset first.
  buddyWin.setIgnoreMouseEvents(true, { forward: true });
  buddyWin.hide();
  buddyWin.webContents.send("buddy:cmd", "hidden");
}

function openMain() {
  if (!alive(mainWin)) return;
  if (mainWin.isMinimized()) mainWin.restore();
  mainWin.show();
  mainWin.focus();
}

/** Clamp a buddy position into the work area of the display it's over. */
function placeBuddy(x, y) {
  const b = buddyWin.getBounds();
  const px = Number.isFinite(x) ? x : b.x;
  const py = Number.isFinite(y) ? y : b.y;
  const work = screen.getDisplayNearestPoint({
    x: Math.round(px + BUDDY_W / 2),
    y: Math.round(py + BUDDY_H / 2),
  }).workArea;
  const cx = Math.round(Math.min(Math.max(px, work.x), work.x + work.width - BUDDY_W));
  const cy = Math.round(Math.min(Math.max(py, work.y), work.y + work.height - BUDDY_H));
  // setBounds, not setPosition: crossing displays with different scaling
  // otherwise resizes the window.
  buddyWin.setBounds({ x: cx, y: cy, width: BUDDY_W, height: BUDDY_H });
  return { x: cx, y: cy, work };
}

// Every buddy channel checks who's talking: the relay only from the main
// window, the buddy's own controls only from the buddy.
const fromMain = (e) => alive(mainWin) && e.sender === mainWin.webContents;
const fromBuddy = (e) => alive(buddyWin) && e.sender === buddyWin.webContents;

ipcMain.on("buddy:relay", (e, msg) => {
  if (!fromMain(e) || !msg || typeof msg.kind !== "string") return;
  if (msg.kind !== "say") buddyLast[msg.kind] = msg;
  if (alive(buddyWin)) buddyWin.webContents.send("buddy:update", msg);
});
ipcMain.on("buddy:set-enabled", (e, on) => {
  if (!fromMain(e) || !!on === buddyEnabled) return;
  buddyEnabled = !!on;
  try {
    fs.writeFileSync(BUDDY_PREFS, JSON.stringify({ enabled: buddyEnabled }));
  } catch { /* still honoured for this run */ }
  if (!buddyEnabled) return hideBuddy();
  // Switching it back on is a fresh start: it also lifts "Hide until restart".
  buddyDismissed = false;
  showBuddy();
});
ipcMain.on("buddy:ready", (e) => {
  if (!fromBuddy(e)) return;
  for (const msg of Object.values(buddyLast)) buddyWin.webContents.send("buddy:update", msg);
});
ipcMain.on("buddy:chat", (e, text) => {
  if (!fromBuddy(e) || !alive(mainWin)) return;
  const t = String(text ?? "").trim().slice(0, 4000);
  if (t) mainWin.webContents.send("buddy:chat", t);
});
ipcMain.on("buddy:move", (e, x, y) => {
  if (!fromBuddy(e) || !Number.isFinite(x) || !Number.isFinite(y)) return;
  buddyWin.setBounds({ x: Math.round(x), y: Math.round(y), width: BUDDY_W, height: BUDDY_H });
});
ipcMain.handle("buddy:place", (e, x, y) => (fromBuddy(e) ? placeBuddy(x, y) : null));
ipcMain.handle("buddy:geom", (e) =>
  fromBuddy(e) ? screen.getDisplayMatching(buddyWin.getBounds()).workArea : null,
);
ipcMain.on("buddy:ignore-mouse", (e, ignore) => {
  if (fromBuddy(e)) buddyWin.setIgnoreMouseEvents(!!ignore, { forward: true });
});
ipcMain.on("buddy:focus", (e) => { if (fromBuddy(e)) buddyWin.focus(); });
ipcMain.on("buddy:open-main", (e) => { if (fromBuddy(e)) openMain(); });
ipcMain.on("buddy:menu", (e, opts) => {
  if (!fromBuddy(e)) return;
  const o = opts || {};
  const cmd = (c) => () => alive(buddyWin) && buddyWin.webContents.send("buddy:cmd", c);
  Menu.buildFromTemplate([
    { label: "Chat with AURA", click: cmd("chat") },
    { label: "Open AURA", click: openMain },
    { type: "separator" },
    { label: "Walk around", type: "checkbox", checked: !!o.wander, click: cmd("toggle-wander") },
    { label: o.napping ? "Wake up" : "Take a nap", click: cmd("toggle-nap") },
    { type: "separator" },
    { label: "Hide until restart", click: () => { buddyDismissed = true; hideBuddy(); } },
  ]).popup({ window: buddyWin });
});

/** Hand a URL to the OS browser — http(s) only, never file:// or a custom
 *  scheme, which is how "open this link" turns into "run this program". */
function openExternal(raw) {
  try {
    const u = new URL(String(raw));
    if (u.protocol === "http:" || u.protocol === "https:") shell.openExternal(u.href);
  } catch {
    /* not a URL — ignore */
  }
}

// Window controls invoked from the renderer (TopBar buttons).
ipcMain.on("win:minimize", (e) => BrowserWindow.fromWebContents(e.sender)?.minimize());
ipcMain.on("win:close", (e) => BrowserWindow.fromWebContents(e.sender)?.close());
ipcMain.on("shell:open-external", (_e, url) => openExternal(url));

app.whenReady().then(() => {
  if (!isDev) startBrainIfNeeded(); // in dev you run server.py yourself
  createWindow();
  createBuddyWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", stopBrain);
process.on("exit", stopBrain);
