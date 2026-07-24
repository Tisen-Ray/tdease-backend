// @ts-nocheck
/**
 * BackendManager — Electron 主进程内托管的 Python 后端生命周期管理器。
 *
 * v1 桌面交付的核心：双击 TDEase 安装包后，Electron 壳使用随包 uv、
 * 初始化后端环境（uv sync + DB init）、拉起 backend (uvicorn) + worker，
 * 等待健康，退出时清理子进程树。用户全程不碰命令行。
 *
 * 设计约束：
 *   - 纯 Node 实现，零运行时依赖（wait-on 是 devDependency，不会被打进 nsis 包，
 *     所以健康轮询用 node:http 手写）。
 *   - settings.json 是唯一的运行配置入口
 *     （16 键），保持与 release 脚本路径行为一致（单一真相：行为等价）。
 *   - backend/app + backend/src + pyproject.toml 保持同级；workspace/run
 *     仍是工具命令工作目录，运行时位置不进入业务路径协议。
 *
 * 进程契约（来自 scripts/release/start-{backend,worker}.ps1）：
 *   backend: uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
 *   worker:  uv run python -m app.worker_main --poll-interval 2
 *   两者均通过 --settings-file 使用同一个 JSON 配置，cwd 为 backend 根。
 *
 * 错误上报：通过 EventEmitter 的 'error' 事件，main.cjs 监听后决定 UI 反馈。
 */

"use strict";

const { spawn, execSync, execFileSync } = require("node:child_process");
const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { appUserDataDir, configuredDataRoot, ensureSettingsFile } = require("./runtime_config.cjs");

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8000;
const HEALTH_TIMEOUT_MS = 90_000; // uv sync 首次可能较慢
const HEALTH_INTERVAL_MS = 1000;
const SYNC_MARKER_FILE = ".tdease-uv-sync.json";
const DATABASE_MARKER_FILE = ".tdease-database-release.json";
const MANAGED_PYTHON_VERSION = "3.11.11";
class BackendManager extends EventEmitter {
  /**
   * @param {{ isDev?: boolean, port?: number, host?: string }} opts
   */
  constructor(opts = {}) {
    super();
    this.isDev = !!opts.isDev;
    this.host = opts.host || DEFAULT_HOST;
    this.port = opts.port || DEFAULT_PORT;
    /** @type {any[]} */
    this._children = [];
    this._stopped = false;
    this._uvPath = null;
    this._backendRoot = null;
  }

  // ---------------------------------------------------------------- public

  /**
   * 完整启动流程：定位根 → 确保 uv → 初始化（幂等）→ 拉起进程 → 等健康。
   * 解析失败/超时则 emit('error', err) 并 throw。
   */
  async start() {
    this._resolvePaths();
    this._ensureUv();
    await this._ensureInitialized();
    await this._assertPortAvailable();
    this._spawnBackend();
    this._spawnWorker();
    await this._waitForHealth();
  }

  /**
   * 停止所有托管的子进程。幂等。Windows 上需 taskkill /T 清整棵进程树，
   * 否则 uvicorn 的 reload 子进程会残留。
   */
  async stop() {
    if (this._stopped) return;
    this._stopped = true;
    for (const child of this._children) {
      await this._killTree(child);
    }
    this._children = [];
  }

  // --------------------------------------------------------------- paths

  /** 定位 backend 根与 env 文件。打包态用 resourcesPath，dev 态用源码树。 */
  _resolvePaths() {
    let backendRoot;
    if (this.isDev) {
      // electron/main.cjs → 上两级 = 项目根（含 app/ src/ pyproject.toml）
      backendRoot = path.resolve(__dirname, "..", "..");
    } else {
      // electron-builder extraResources 把 app/src/pyproject.toml 放到
      // process.resourcesPath/backend/。详见 electron-builder.json。
      backendRoot = path.join(process.resourcesPath, "backend");
    }
    if (!fs.existsSync(path.join(backendRoot, "pyproject.toml"))) {
      throw new BackendError(
        "BACKEND_ROOT_NOT_FOUND",
        `后端根未找到（缺 pyproject.toml）: ${backendRoot}`,
      );
    }
    this._backendRoot = backendRoot;

    const userDataDir = appUserDataDir();
    fs.mkdirSync(userDataDir, { recursive: true });
    this._settingsFile = this.isDev
      ? path.join(backendRoot, "settings.json")
      : path.join(userDataDir, "settings.json");
    ensureSettingsFile(
      this._settingsFile,
      this.isDev ? null : path.join(this._backendRoot, "data", "seed", "settings.json"),
    );
    this._venvDir = preferredVenvDir(backendRoot, userDataDir, this.isDev);
  }

  /** 返回让 uv 使用托管 venv 的环境变量（UV_PROJECT_ENVIRONMENT）。 */
  _venvEnv() {
    return { UV_PROJECT_ENVIRONMENT: this._venvDir };
  }

  _runtimeEnv(extra = {}) {
    const runtimeBin = this._uvPath ? path.dirname(this._uvPath) : "";
    const inheritedPath = process.env.PATH || "";
    return {
      ...process.env,
      PATH: runtimeBin ? `${runtimeBin}${path.delimiter}${inheritedPath}` : inheritedPath,
      ...this._venvEnv(),
      ...extra,
    };
  }

  // --------------------------------------------------------------- uv

  /** Resolve the application-owned uv. Release never depends on user PATH. */
  _ensureUv() {
    const bundledUv = bundledUvPath();
    if (bundledUv) {
      this._uvPath = bundledUv;
      return;
    }

    // Development remains convenient. Packaged builds fail if their managed
    // runtime is incomplete instead of silently selecting another uv.
    if (this.isDev) {
      const pathUv = which("uv");
      if (pathUv) {
        this._uvPath = pathUv;
        return;
      }
    }
    throw new BackendError(
      "BUNDLED_UV_MISSING",
      "安装包缺少受控 uv 运行时，请重新安装 TDEase。",
    );
  }

  // ----------------------------------------------------------- initialize

  /**
   * Idempotent initialization from one settings.json and one DataRoot.
   */
  async _ensureInitialized() {
    ensureSettingsFile(
      this._settingsFile,
      this.isDev ? null : path.join(this._backendRoot, "data", "seed", "settings.json"),
    );

    // uv sync：构建/同步后端环境。venv 在用户数据区（this._venvDir），
    // 通过 UV_PROJECT_ENVIRONMENT 指定。仅当 venv 不存在时跑（首次）。
    const venvReady = fs.existsSync(path.join(this._venvDir, process.platform === "win32" ? "Scripts" : "bin"));
    const syncFingerprint = backendDependencyFingerprint(this._backendRoot);
    if (!venvReady || !this._isVenvSynced(syncFingerprint)) {
      this.emit("progress", {
        stage: "uv-sync",
        message: "正在准备 Python 后端环境（首次启动，可能需要数分钟）",
      });
      await runCmd(this._uvPath, ["sync", "--frozen", "--python", MANAGED_PYTHON_VERSION], {
        cwd: this._backendRoot,
        env: this._runtimeEnv(),
      });
      this._writeSyncMarker(syncFingerprint);
    }

    deploySystemAssets(path.join(this._backendRoot, "data", "system"), path.join(configuredDataRoot(this._settingsFile), "system"));
    seedInitialWorkspaces(
      path.join(this._backendRoot, "data", "seed", "workspaces"),
      path.join(configuredDataRoot(this._settingsFile), "workspaces"),
    );

    const databasePath = path.join(configuredDataRoot(this._settingsFile), "database", "tdease.db");
    fs.mkdirSync(path.dirname(databasePath), { recursive: true });
    const databaseFingerprint = databaseReleaseFingerprint(this._backendRoot);
    if (!this._isDatabaseReleaseReady(databasePath, databaseFingerprint)) {
      this.emit("progress", { stage: "db-init", message: "正在校验并迁移数据库" });
      await runCmd(
        this._uvPath,
        [
          "run",
          "python",
          "-m",
          "app.desktop_bootstrap",
          "--settings-file",
          this._settingsFile,
          "migrate-database",
        ],
        { cwd: this._backendRoot, env: this._runtimeEnv() },
      );
      this._writeDatabaseReleaseMarker(databasePath, databaseFingerprint);
    }
  }

  _isVenvSynced(fingerprint) {
    if (!fingerprint) return false;
    const marker = path.join(this._venvDir, SYNC_MARKER_FILE);
    if (!fs.existsSync(marker)) return false;
    try {
      const raw = JSON.parse(fs.readFileSync(marker, "utf8"));
      return raw && raw.fingerprint === fingerprint;
    } catch {
      return false;
    }
  }

  _writeSyncMarker(fingerprint) {
    if (!fingerprint) return;
    fs.mkdirSync(this._venvDir, { recursive: true });
    fs.writeFileSync(
      path.join(this._venvDir, SYNC_MARKER_FILE),
      `${JSON.stringify({ fingerprint, syncedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );
  }

  _isDatabaseReleaseReady(databasePath, fingerprint) {
    if (!databasePath || !fingerprint || !fs.existsSync(databasePath)) return false;
    const marker = path.join(path.dirname(databasePath), DATABASE_MARKER_FILE);
    try {
      const raw = JSON.parse(fs.readFileSync(marker, "utf8"));
      return raw && raw.fingerprint === fingerprint;
    } catch {
      return false;
    }
  }

  _writeDatabaseReleaseMarker(databasePath, fingerprint) {
    if (!databasePath || !fingerprint) return;
    const marker = path.join(path.dirname(databasePath), DATABASE_MARKER_FILE);
    fs.writeFileSync(
      marker,
      `${JSON.stringify({ fingerprint, migratedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );
  }

  // --------------------------------------------------------------- spawn

  _spawnBackend() {
    const child = spawn(
      this._uvPath,
      ["run", "python", "-m", "app.desktop_server", "--settings-file", this._settingsFile, "--host", this.host, "--port", String(this.port)],
      {
        cwd: this._backendRoot,
        env: this._runtimeEnv(),
        windowsHide: true,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    pipeToConsole(child, "backend");
    this._track(child, "backend");
  }

  async _assertPortAvailable() {
    if (await isPortAvailable(this.host, this.port)) return;

    const killed = killKnownTDEaseBackendProcesses();
    if (killed > 0) {
      this.emit("progress", {
        stage: "cleanup-backend",
        message: `已清理 ${killed} 个旧 TDEase 后端进程，正在重新启动`,
      });
      for (let i = 0; i < 20; i += 1) {
        if (await isPortAvailable(this.host, this.port)) return;
        await sleep(250);
      }
    }

    throw new BackendError(
      "PORT_IN_USE",
      `后端端口 ${this.host}:${this.port} 已被占用，且占用者不是可识别的 TDEase 后端进程。请关闭占用 8000 端口的程序后重试。`,
    );
  }

  _spawnWorker() {
    const child = spawn(
      this._uvPath,
      ["run", "python", "-m", "app.worker_main", "--settings-file", this._settingsFile, "--poll-interval", "2"],
      {
        cwd: this._backendRoot,
        env: this._runtimeEnv(),
        windowsHide: true,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    pipeToConsole(child, "worker");
    this._track(child, "worker");
  }

  _track(child, tag) {
    this._children.push(child);
    child.on("exit", (code, signal) => {
      if (!this._stopped) {
        // 非主动停止时的子进程退出 = 异常
        const tail = child._stderrTail ? `\n\n${child._stderrTail}` : "";
        this.emit("error", new BackendError("CHILD_EXITED", `${tag} 子进程退出 code=${code} signal=${signal}${tail}`));
      }
    });
  }

  // --------------------------------------------------------------- health

  /** 轮询 /ready，超时则 throw。纯 node:http，无依赖。 */
  _waitForHealth() {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + HEALTH_TIMEOUT_MS;
      const tick = () => {
        if (this._stopped) return resolve();
        if (Date.now() > deadline) {
          return reject(
            new BackendError(
              "HEALTH_TIMEOUT",
              `后端 ${this.host}:${this.port}/ready 在 ${HEALTH_TIMEOUT_MS / 1000}s 内未就绪`,
            ),
          );
        }
        const req = http.get(
          { host: this.host, port: this.port, path: "/ready", timeout: 2000 },
          (res) => {
            res.resume();
            if (res.statusCode === 200) return resolve();
            setTimeout(tick, HEALTH_INTERVAL_MS);
          },
        );
        req.on("error", () => setTimeout(tick, HEALTH_INTERVAL_MS));
        req.on("timeout", () => {
          req.destroy();
          setTimeout(tick, HEALTH_INTERVAL_MS);
        });
      };
      tick();
    });
  }

  // --------------------------------------------------------------- kill

  _killTree(child) {
    return new Promise((resolve) => {
      if (!child || child.exitCode !== null || child.killed) return resolve();
      try {
        if (process.platform === "win32") {
          // /T 杀整棵进程树（uvicorn 可能 fork 子进程）
          execSync(`taskkill /pid ${child.pid} /T /F`, { stdio: "ignore" });
        } else {
          process.kill(-child.pid, "SIGTERM");
        }
      } catch {
        try {
          child.kill("SIGKILL");
        } catch {
          /* already gone */
        }
      }
      resolve();
    });
  }
}

// --------------------------------------------------------------- helpers

class BackendError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = "BackendError";
  }
}

function preferredVenvDir(backendRoot, userDataDir, isDev) {
  const projectVenvDir = path.join(backendRoot, ".venv");
  const fallbackVenvDir = path.join(userDataDir, "backend-venv");
  if (!isDev) {
    fs.mkdirSync(fallbackVenvDir, { recursive: true });
    return fallbackVenvDir;
  }
  try {
    fs.mkdirSync(projectVenvDir, { recursive: true });
    const probe = path.join(projectVenvDir, ".write-test");
    fs.writeFileSync(probe, "ok", "utf8");
    fs.unlinkSync(probe);
    return projectVenvDir;
  } catch {
    fs.mkdirSync(fallbackVenvDir, { recursive: true });
    return fallbackVenvDir;
  }
}

function isPortAvailable(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

function killKnownTDEaseBackendProcesses() {
  if (process.platform !== "win32") return 0;
  const script = `
$procs = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -in @('python.exe','uv.exe')) -and
  $_.CommandLine -and
  ($_.CommandLine -match 'app\\.worker_main|uvicorn(\\.exe)?[" ]+app\\.main:app|uvicorn app\\.main:app') -and
  ($_.CommandLine -match 'TDEase|backend-venv|resources\\\\backend')
}
$ids = @($procs | Select-Object -ExpandProperty ProcessId)
foreach ($id in $ids) {
  Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
$ids.Count
`;
  try {
    const output = execFileSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 10_000,
    });
    const count = Number.parseInt(String(output).trim(), 10);
    return Number.isFinite(count) ? count : 0;
  } catch {
    return 0;
  }
}

function backendDependencyFingerprint(backendRoot) {
  const hash = crypto.createHash("sha256");
  for (const name of ["pyproject.toml", "uv.lock"]) {
    const file = path.join(backendRoot, name);
    if (!fs.existsSync(file)) return "";
    hash.update(name);
    hash.update(fs.readFileSync(file));
  }
  return hash.digest("hex");
}

function databaseReleaseFingerprint(backendRoot) {
  const hash = crypto.createHash("sha256");
  const files = [
    path.join(backendRoot, "app", "database", "init_db.py"),
    path.join(backendRoot, "app", "database", "lifecycle.py"),
    ...listFilesRecursively(path.join(backendRoot, "app", "database", "migrations")),
  ].sort();
  if (files.length < 3 || files.some((file) => !fs.existsSync(file))) return "";
  for (const file of files) {
    hash.update(path.relative(backendRoot, file).replaceAll(path.sep, "/"));
    hash.update(fs.readFileSync(file));
  }
  return hash.digest("hex");
}

function listFilesRecursively(root) {
  if (!fs.existsSync(root)) return [];
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...listFilesRecursively(target));
    else if (entry.isFile() && entry.name.endsWith(".py")) files.push(target);
  }
  return files;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 模拟 which/where，返回首个命中或 null。 */
function which(name) {
  const ext = process.platform === "win32" ? ["", ".exe", ".cmd", ".bat"] : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue;
    for (const e of ext) {
      const p = path.join(dir, name + e);
      if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
    }
  }
  return null;
}

function bundledUvPath() {
  const executable = process.platform === "win32" ? "uv.exe" : "uv";
  const candidate = path.join(
    process.resourcesPath || "",
    "backend",
    "data",
    "system",
    "runtime",
    "uv",
    executable,
  );
  return fs.existsSync(candidate) ? candidate : null;
}

function deploySystemAssets(sourceRoot, targetRoot) {
  const workflowRoot = path.join(sourceRoot, "workflows");
  const nodesRoot = path.join(sourceRoot, "nodes");
  if (!fs.existsSync(workflowRoot) || !fs.existsSync(nodesRoot)) {
    throw new BackendError("SYSTEM_ASSETS_INCOMPLETE", `系统资产不完整: ${sourceRoot}`);
  }
  const manifestCount = countNamedFiles(nodesRoot, "node.json");
  if (manifestCount < 1) {
    throw new BackendError("SYSTEM_ASSETS_INCOMPLETE", `系统节点清单为空: ${nodesRoot}`);
  }

  const fingerprint = systemAssetsFingerprint(sourceRoot);
  const marker = path.join(targetRoot, ".release-assets.json");
  try {
    const deployed = JSON.parse(fs.readFileSync(marker, "utf8"));
    if (deployed.fingerprint === fingerprint) return false;
  } catch {
    // Missing or invalid marker requires a fresh atomic deployment.
  }

  const parent = path.dirname(targetRoot);
  const staging = path.join(parent, `.system-staging-${process.pid}`);
  const backup = path.join(parent, `.system-backup-${process.pid}`);
  fs.rmSync(staging, { recursive: true, force: true });
  fs.rmSync(backup, { recursive: true, force: true });
  fs.mkdirSync(parent, { recursive: true });
  fs.cpSync(sourceRoot, staging, { recursive: true, force: true });
  fs.writeFileSync(
    path.join(staging, ".release-assets.json"),
    `${JSON.stringify({ fingerprint }, null, 2)}\n`,
    "utf8",
  );
  try {
    if (fs.existsSync(targetRoot)) fs.renameSync(targetRoot, backup);
    fs.renameSync(staging, targetRoot);
    fs.rmSync(backup, { recursive: true, force: true });
  } catch (error) {
    if (!fs.existsSync(targetRoot) && fs.existsSync(backup)) fs.renameSync(backup, targetRoot);
    fs.rmSync(staging, { recursive: true, force: true });
    throw error;
  }
  return true;
}

function systemAssetsFingerprint(root) {
  const hash = crypto.createHash("sha256");
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.name === ".release-assets.json") continue;
      const target = path.join(current, entry.name);
      const relative = path.relative(root, target).replaceAll(path.sep, "/");
      hash.update(entry.isDirectory() ? `d:${relative}\n` : `f:${relative}\n`);
      if (entry.isDirectory()) stack.push(target);
      else if (entry.isFile()) {
        const stat = fs.statSync(target);
        hash.update(`${stat.size}:${Math.trunc(stat.mtimeMs)}\n`);
        // Manifests, workflows, skills, and configuration are small but
        // semantically important. Hash their bytes so preserved timestamps
        // cannot hide a release change. Large binaries retain the cheap
        // size/mtime fingerprint to avoid reading hundreds of MB at startup.
        if (stat.size <= 1024 * 1024) hash.update(fs.readFileSync(target));
      }
    }
  }
  return hash.digest("hex");
}

function seedInitialWorkspaces(sourceRoot, targetRoot) {
  if (!fs.existsSync(sourceRoot)) return [];
  fs.mkdirSync(targetRoot, { recursive: true });
  const seeded = [];
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const source = path.join(sourceRoot, entry.name);
    if (!fs.existsSync(path.join(source, "workspace.json"))) continue;
    const target = path.join(targetRoot, entry.name);
    if (fs.existsSync(target)) continue;
    fs.cpSync(source, target, { recursive: true, force: false });
    seeded.push(entry.name);
  }
  return seeded;
}

function countNamedFiles(root, name) {
  let count = 0;
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const target = path.join(current, entry.name);
      if (entry.isDirectory()) stack.push(target);
      else if (entry.isFile() && entry.name.toLowerCase() === name.toLowerCase()) count += 1;
    }
  }
  return count;
}

/** spawn 一个命令并包装为 Promise（保留 stderr tail 供打包态报错）。 */
function runCmd(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], shell: false, ...opts });
    let stdoutTail = "";
    let stderrTail = "";
    const append = (current, chunk) => (current + chunk.toString()).slice(-4000);
    child.stdout?.on("data", (d) => {
      stdoutTail = append(stdoutTail, d);
      safeConsoleWrite(process.stdout, d);
    });
    child.stderr?.on("data", (d) => {
      stderrTail = append(stderrTail, d);
      safeConsoleWrite(process.stderr, d);
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) return resolve();
      const tail = stderrTail || stdoutTail;
      reject(new BackendError("CMD_FAILED", `${cmd} ${args.join(" ")} exit ${code}${tail ? `\n\n${tail}` : ""}`));
    });
  });
}

/** 把子进程 stdout/stderr 加前缀打到主进程控制台（dev 可见；打包态日志归文件）。 */
function pipeToConsole(child, tag) {
  const prefix = `[${tag}] `;
  child._stderrTail = "";
  child.stdout?.on("data", (d) => safeConsoleWrite(process.stdout, prefix + d));
  child.stderr?.on("data", (d) => {
    const text = d.toString();
    child._stderrTail = (child._stderrTail + text).slice(-4000);
    safeConsoleWrite(process.stderr, prefix + text);
  });
}

function safeConsoleWrite(stream, value) {
  if (!stream || stream.destroyed || !stream.writable) return;
  try {
    stream.write(value, (error) => {
      if (error && error.code !== "EPIPE") throw error;
    });
  } catch (error) {
    if (!error || error.code !== "EPIPE") throw error;
  }
}

module.exports = {
  BackendManager,
  BackendError,
  deploySystemAssets,
  seedInitialWorkspaces,
  systemAssetsFingerprint,
};
