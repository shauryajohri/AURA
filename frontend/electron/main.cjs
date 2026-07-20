// Electron main process — the "body" that hosts the React "face".
// In dev it loads the Vite server; in prod (AURA_PROD=1 or packaged) it loads
// the built dist/index.html AND boots the Python brain itself, so a single
// double-click brings the whole of AURA to life — and closing the window
// puts her back to sleep (the brain is killed with the app).
const { app, BrowserWindow, ipcMain, Menu } = require("electron");
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

function createWindow() {
  const iconPath = path.join(__dirname, "aura.ico");
  const win = new BrowserWindow({
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
  });

  // Always full: open maximized, and if anything un-maximizes it,
  // snap straight back. Minimize (to taskbar) still works.
  win.once("ready-to-show", () => {
    win.maximize();
    win.show();
  });
  win.on("unmaximize", () => win.maximize());

  if (isDev) {
    win.loadURL("http://localhost:5173");
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

// Window controls invoked from the renderer (TopBar buttons).
ipcMain.on("win:minimize", (e) => BrowserWindow.fromWebContents(e.sender)?.minimize());
ipcMain.on("win:close", (e) => BrowserWindow.fromWebContents(e.sender)?.close());

app.whenReady().then(() => {
  if (!isDev) startBrainIfNeeded(); // in dev you run server.py yourself
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", stopBrain);
process.on("exit", stopBrain);
