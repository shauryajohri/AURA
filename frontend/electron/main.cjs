// Electron main process — the "body" that hosts the React "face".
// In dev it loads the Vite server; in prod it loads the built dist/index.html.
const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const path = require("path");

const isDev = !app.isPackaged;

// AURA owns its chrome: no OS titlebar, no menu bar.
Menu.setApplicationMenu(null);

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    frame: false, // frameless — AURA renders its own minimize/close controls
    backgroundColor: "#05060f",
    show: false,
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
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
