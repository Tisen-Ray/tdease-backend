/**
 * BackendManager — Electron 主进程 FastAPI 生命周期管理。
 *
 * Phase 5 收敛：只做两件事
 * 1. 启动 FastAPI (uv run uvicorn app.main:app)
 * 2. 轮询 /health 直到就绪
 *
 * 不再管理 worker、DB migration、asset deployment、workspace seeding。
 * 这些是服务端启动时的自身职责（app/main.py lifespan）。
 */
"use strict";

const { spawn, execSync } = require("node:child_process");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8000;
const HEALTH_TIMEOUT_MS = 60_000;
const HEALTH_INTERVAL_MS = 800;

class BackendManager extends EventEmitter {
  constructor(opts = {}) {
    super();
    this.isDev = !!opts.isDev;
    this.host = opts.host || DEFAULT_HOST;
    this.port = opts.port || DEFAULT_PORT;
    this._children = [];
    this._stopped = false;
    this._uvPath = null;
    this._backendRoot = null;
  }

  async start() {
    this._resolvePaths();
    this._ensureUv();
    await this._assertPortAvailable();
    this._spawnBackend();
    await this._waitForHealth();
  }

  async stop() {
    if (this._stopped) return;
    this._stopped = true;
    for (const child of this._children) await this._killTree(child);
    this._children = [];
  }

  _resolvePaths() {
    this._backendRoot = this.isDev
      ? path.resolve(__dirname, "..", "..")
      : path.join(process.resourcesPath, "backend");
    if (!fs.existsSync(path.join(this._backendRoot, "pyproject.toml"))) {
      throw new BackendError("BACKEND_ROOT_NOT_FOUND", `后端根未找到: ${this._backendRoot}`);
    }
  }

  _ensureUv() {
    const bundled = _bundledUvPath();
    if (bundled) { this._uvPath = bundled; return; }
    if (this.isDev) {
      const sysUv = _which("uv");
      if (sysUv) { this._uvPath = sysUv; return; }
    }
    throw new BackendError("UV_MISSING", "未找到 uv。开发模式请安装: pip install uv");
  }

  _runtimeEnv() {
    const binDir = this._uvPath ? path.dirname(this._uvPath) : "";
    const inherited = process.env.PATH || "";
    return {
      ...process.env,
      PATH: binDir ? `${binDir}${path.delimiter}${inherited}` : inherited,
      TDEASE_DATA_ROOT: path.join(this._backendRoot, "server-data"),
    };
  }

  _spawnBackend() {
    const child = spawn(
      this._uvPath,
      ["run", "uvicorn", "app.main:app", "--host", this.host, "--port", String(this.port)],
      { cwd: this._backendRoot, env: this._runtimeEnv(), windowsHide: true, shell: false, stdio: ["ignore", "pipe", "pipe"] },
    );
    _pipeToConsole(child, "backend");
    this._track(child, "backend");
  }

  _track(child, tag) {
    this._children.push(child);
    child.on("exit", (code, signal) => {
      if (!this._stopped) {
        const tail = child._stderrTail ? `\n${child._stderrTail}` : "";
        this.emit("error", new BackendError("CHILD_EXITED", `${tag} 退出 code=${code} signal=${signal}${tail}`));
      }
    });
  }

  async _assertPortAvailable() {
    if (await _isPortAvailable(this.host, this.port)) return;
    _killStaleBackend();
    for (let i = 0; i < 15; i++) {
      if (await _isPortAvailable(this.host, this.port)) return;
      await _sleep(300);
    }
    throw new BackendError("PORT_IN_USE", `端口 ${this.port} 被占用，请关闭占用程序后重试`);
  }

  _waitForHealth() {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + HEALTH_TIMEOUT_MS;
      const tick = () => {
        if (this._stopped) return resolve();
        if (Date.now() > deadline) return reject(new BackendError("HEALTH_TIMEOUT", `后端 /health 在 ${HEALTH_TIMEOUT_MS / 1000}s 内未就绪`));
        const req = http.get({ host: this.host, port: this.port, path: "/health", timeout: 2000 }, (res) => {
          res.resume();
          if (res.statusCode === 200) return resolve();
          setTimeout(tick, HEALTH_INTERVAL_MS);
        });
        req.on("error", () => setTimeout(tick, HEALTH_INTERVAL_MS));
        req.on("timeout", () => { req.destroy(); setTimeout(tick, HEALTH_INTERVAL_MS); });
      };
      tick();
    });
  }

  _killTree(child) {
    return new Promise((resolve) => {
      if (!child || child.exitCode !== null || child.killed) return resolve();
      try {
        if (process.platform === "win32") execSync(`taskkill /pid ${child.pid} /T /F`, { stdio: "ignore" });
        else { process.kill(-child.pid, "SIGTERM"); try { child.kill("SIGKILL"); } catch { /* */ } }
      } catch { /* already dead */ }
      resolve();
    });
  }
}

class BackendError extends Error {
  constructor(code, msg) { super(msg); this.code = code; this.name = "BackendError"; }
}

function _bundledUvPath() {
  const exe = process.platform === "win32" ? "uv.exe" : "uv";
  const p = path.join(process.resourcesPath || "", "backend", "runtime", exe);
  return fs.existsSync(p) ? p : null;
}

function _which(name) {
  const exts = process.platform === "win32" ? ["", ".exe", ".cmd", ".bat"] : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue;
    for (const e of exts) {
      const p = path.join(dir, name + e);
      if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
    }
  }
  return null;
}

function _isPortAvailable(host, port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => { s.close(() => resolve(true)); });
    s.listen(port, host);
  });
}

function _killStaleBackend() {
  if (process.platform !== "win32") return;
  try { execSync(`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','uv.exe') -and $_.CommandLine -match 'uvicorn app\\\\.main:app' } | Stop-Process -Force"`, { stdio: "ignore", timeout: 5000 }); }
  catch { /* */ }
}

function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function _pipeToConsole(child, tag) {
  const prefix = `[${tag}] `;
  child._stderrTail = "";
  child.stdout?.on("data", (d) => _safeWrite(process.stdout, prefix + d));
  child.stderr?.on("data", (d) => {
    const text = d.toString();
    child._stderrTail = (child._stderrTail + text).slice(-4000);
    _safeWrite(process.stderr, prefix + text);
  });
}

function _safeWrite(stream, val) {
  if (!stream || stream.destroyed || !stream.writable) return;
  try { stream.write(val, (err) => { if (err && err.code !== "EPIPE") throw err; }); }
  catch (err) { if (!err || err.code !== "EPIPE") throw err; }
}

module.exports = { BackendManager, BackendError };
