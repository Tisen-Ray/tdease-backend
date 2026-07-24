"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function appUserDataDir() {
  try {
    const { app } = require("electron");
    if (app && app.getPath) return app.getPath("userData");
  } catch {
    // electron is unavailable in node-only checks/tests.
  }
  return path.join(os.tmpdir(), "tdease-desktop");
}

function settingsFilePath(projectRoot = null) {
  return projectRoot
    ? path.join(projectRoot, "settings.json")
    : path.join(appUserDataDir(), "settings.json");
}

function readSettings(filePath = settingsFilePath()) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

function ensureSettingsFile(target = settingsFilePath(), providerSeedFile = null) {
  if (!fs.existsSync(target)) {
    const seed = providerSeedFile ? readSettings(providerSeedFile) : null;
    const providers = seed?.providers && typeof seed.providers === "object"
      ? seed.providers
      : {
          deepseek: {
            base_url: "https://api.deepseek.com/v1",
            api_key: "",
          },
        };
    const runtime = seed?.runtime && typeof seed.runtime === "object"
      ? seed.runtime
      : { database_role: "verify", internal_dispatcher: false };
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, `${JSON.stringify({
      schemaVersion: 1,
      data_root: defaultDataRoot(),
      providers,
      runtime,
    }, null, 2)}\n`, "utf8");
  }
  return target;
}

/**
 * Writable runtime root (database/logs/tmp/workspaces).
 * Defaults to <userData>/tdease-data so dev and packaged modes share the same
 * location and the repo tree is never polluted by runtime writes.
 */
function defaultDataRoot() {
  return path.join(appUserDataDir(), "tdease-data");
}

function configuredDataRoot(filePath = settingsFilePath()) {
  const configured = readSettings(filePath)?.data_root;
  return configured && String(configured).trim()
    ? path.resolve(path.dirname(filePath), String(configured))
    : defaultDataRoot();
}

function logDir(filePath = settingsFilePath()) {
  return path.join(configuredDataRoot(filePath), "logs");
}

function ensureRuntimeDirectories({ host = "127.0.0.1", port = 8000, settingsFile = settingsFilePath() } = {}) {
  ensureSettingsFile(settingsFile);
  const runtimeRoot = configuredDataRoot(settingsFile);
  const databasePath = path.join(runtimeRoot, "database", "tdease.db");
  for (const dir of [
    appUserDataDir(),
    runtimeRoot,
    path.join(runtimeRoot, "logs"),
    path.join(runtimeRoot, "tmp"),
    path.join(runtimeRoot, "workspaces"),
    path.dirname(databasePath),
  ]) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return { dataRoot: runtimeRoot, databasePath, host, port };
}

module.exports = {
  appUserDataDir,
  configuredDataRoot,
  defaultDataRoot,
  ensureRuntimeDirectories,
  ensureSettingsFile,
  settingsFilePath,
  logDir,
};
