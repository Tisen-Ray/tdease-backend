// @ts-nocheck
const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { BackendManager } = require("./backend_manager.cjs");
const { logDir } = require("./runtime_config.cjs");

// 注意：不能用 app.isPackaged 判断 —— 我们用 unpacked 目录形式（resources/app/）而非
// app.asar，electron 会误判 isPackaged=false。改用 backend 源码是否存在于 resourcesPath
// 作为"真打包态"标志（backend_manager 同样用此判断）。
const isDev = !fs.existsSync(path.join(process.resourcesPath, "backend", "pyproject.toml"));
const devUrl = process.env.TDEASE_ELECTRON_DEV_URL || "http://127.0.0.1:5173";
const distDir = path.resolve(__dirname, "..", "dist");
const indexHtml = path.join(distDir, "index.html");
const appIcon = path.resolve(__dirname, "assets", "icon.png");
const splashHtml = path.join(__dirname, "splash.html");

app.setName("TDEase");
if (process.platform === "win32") {
  app.setAppUserModelId("com.ray.tdease-frontend");
}

let splashWindow = null;
let mainWindow = null;
/** @type {BackendManager|null} */
let backendManager = null;
let updateCheckStarted = false;

// ---------------------------------------------------------------- splash

/**
 * 打包态启动流程：
 * 1. 立即显示 splash 窗口（轻量 HTML，不加载 Vue，即时反馈）
 * 2. backend_manager.start()，progress 事件推给 splash 显示进度
 * 3. 成功 → 关 splash + 开主窗；失败 → splash 显示错误 + 退出
 *
 * dev 态：直接开主窗（后端由 scripts/electron-dev.cjs 起的 vite 旁边用户自管）
 */
function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 480,
    height: 340,
    frame: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    center: true,
    backgroundColor: "#f4f1e8",
    icon: appIcon,
    webPreferences: {
      // splash 是我们自己写的纯本地静态文件，不加载远程内容。
      // 用 nodeIntegration 让 splash.html 内 require electron（ipcRenderer）。
      // 仅限 splash 窗口；主窗口仍保持 contextIsolation + sandbox。
      nodeIntegration: true,
      contextIsolation: false,
      sandbox: false,
    },
  });
  splashWindow.loadFile(splashHtml);
  // splash 不可关闭（用户不该在启动中途关掉它而留下僵尸后端）
  splashWindow.on("close", (e) => {
    if (!app.isQuitting) e.preventDefault();
  });
}

ipcMain.handle("desktop:open-logs", async () => {
  const dir = logDir();
  fs.mkdirSync(dir, { recursive: true });
  return shell.openPath(dir);
});
ipcMain.handle("desktop:open-uv-docs", () => shell.openExternal("https://docs.astral.sh/uv/getting-started/installation/"));

ipcMain.on("splash:quit", () => {
  app.isQuitting = true;
  app.quit();
});
ipcMain.on("splash:retry", () => {
  void bootApp({ retry: true });
});

function sendSplash(channel, payload) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send(channel, payload);
  }
}

// ---------------------------------------------------------------- main window

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#f4f1e8",
    autoHideMenuBar: true,
    icon: appIcon,
    show: false, // 先隐藏，加载完再显示避免白闪
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // 打包态用 file:// 加载：ES module scripts 在 file:// 下被同源策略阻止。
      // webSecurity:false 让本地受信前端能加载 module + 调 127.0.0.1:8000 后端。
      // 仅打包态；dev 态走 http dev server 不需要。
      webSecurity: !isDev ? false : true,
      allowRunningInsecureContent: !isDev ? true : false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.destroy();
      splashWindow = null;
    }
    startUpdateCheck();
  });

  if (isDev) {
    mainWindow.loadURL(devUrl);
    mainWindow.webContents.openDevTools({ mode: "detach" });
    return;
  }

  if (!fs.existsSync(indexHtml)) {
    throw new Error(`Electron frontend bundle not found: ${indexHtml}`);
  }
  mainWindow.loadFile(indexHtml);
}

// ---------------------------------------------------------------- boot

function startUpdateCheck() {
  if (isDev || updateCheckStarted) return;
  updateCheckStarted = true;
  try {
    const { autoUpdater } = require("electron-updater");
    autoUpdater.autoDownload = false;
    autoUpdater.on("error", (err) => {
      console.warn("[updater] check failed:", err?.message || err);
    });
    autoUpdater.on("update-available", (info) => {
      console.info("[updater] update available:", info?.version || "unknown");
    });
    autoUpdater.checkForUpdates().catch((err) => {
      console.warn("[updater] check failed:", err?.message || err);
    });
  } catch {
    console.warn("[updater] electron-updater is not installed; skipping auto update check.");
  }
}

async function bootApp(options = {}) {
  if (isDev) {
    createMainWindow();
    return;
  }
  if (options.retry && backendManager) {
    await backendManager.stop();
    backendManager = null;
  }
  // 打包态：splash-first
  if (!splashWindow || splashWindow.isDestroyed()) {
    createSplashWindow();
  } else {
    sendSplash("splash:reset", {});
  }
  backendManager = new BackendManager({ isDev: false });
  backendManager.on("progress", (info) => {
    sendSplash("splash:progress", info);
  });
  backendManager.on("error", (err) => {
    sendSplash("splash:error", { code: err.code || "BACKEND_ERROR", message: err.message || String(err) });
  });
  try {
    await backendManager.start();
    createMainWindow();
  } catch (err) {
    sendSplash("splash:error", { code: err.code || "ERROR", message: err.message || String(err) });
    // 不立即退出，让用户看到错误信息；由 splash 的退出按钮或关闭窗口触发 quit
  }
}

app.whenReady().then(() => {
  bootApp();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && isDev) {
      createMainWindow();
    }
  });
});

// 退出前清理后端子进程树（Windows 上 uvicorn 子进程需 taskkill /T）
app.on("before-quit", async (e) => {
  if (backendManager) {
    e.preventDefault();
    app.isQuitting = true;
    await backendManager.stop();
    app.exit(0);
  }
});

app.on("window-all-closed", () => {
  // 打包态下，主窗口关闭才退出（splash 关闭不退出，由 close handler 拦截）
  if (process.platform !== "darwin" && (!splashWindow || splashWindow.isDestroyed())) {
    app.quit();
  }
});
