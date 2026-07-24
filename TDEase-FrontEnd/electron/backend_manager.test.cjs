"use strict";

const assert = require("node:assert/strict");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { BackendError, BackendManager, deploySystemAssets } = require("./backend_manager.cjs");
const fs = require("node:fs");
const { configuredDataRoot, ensureSettingsFile } = require("./runtime_config.cjs");

test("runtime data root comes from the selected settings file", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-settings-"));
  const settingsFile = path.join(root, "settings.json");
  fs.writeFileSync(settingsFile, JSON.stringify({ data_root: "D:\\TDEase" }));

  assert.equal(configuredDataRoot(settingsFile), path.resolve("D:\\TDEase"));
});

test("managed uv directory is first in child PATH", () => {
  const manager = new BackendManager({ isDev: true });
  manager._uvPath = path.join(os.tmpdir(), "tdease-runtime", "uv.exe");
  manager._venvDir = path.join(os.tmpdir(), "tdease-venv");

  const env = manager._runtimeEnv();

  assert.equal(env.PATH.split(path.delimiter)[0], path.dirname(manager._uvPath));
  assert.equal(env.UV_PROJECT_ENVIRONMENT, manager._venvDir);
});

test("packaged runtime never falls back to uv from user PATH", () => {
  const manager = new BackendManager({ isDev: false });

  assert.throws(
    () => manager._ensureUv(),
    (error) => error instanceof BackendError && error.code === "BUNDLED_UV_MISSING",
  );
});

test("desktop processes receive the same explicit settings file", () => {
  const source = fs.readFileSync(path.join(__dirname, "backend_manager.cjs"), "utf8");

  assert.match(source, /app\.desktop_server[\s\S]*--settings-file/);
  assert.match(source, /app\.worker_main[\s\S]*--settings-file/);
  assert.doesNotMatch(source, /TDEASE_ENV_FILE|writeDefaultEnvFile/);
});

test("relative data root resolves beside the selected settings file", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-relative-settings-"));
  const settingsFile = path.join(root, "config", "settings.json");
  fs.mkdirSync(path.dirname(settingsFile), { recursive: true });
  fs.writeFileSync(settingsFile, JSON.stringify({ data_root: "../data" }));

  assert.equal(configuredDataRoot(settingsFile), path.join(root, "data"));
});

test("provider seed initializes only a missing settings file", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-provider-seed-"));
  const settingsFile = path.join(root, "settings.json");
  const seedFile = path.join(root, "settings.seed.json");
  fs.writeFileSync(seedFile, JSON.stringify({
    providers: { deepseek: { base_url: "https://seed.test/v1", api_key: "seed-key" } },
  }));

  ensureSettingsFile(settingsFile, seedFile);
  assert.equal(JSON.parse(fs.readFileSync(settingsFile, "utf8")).providers.deepseek.api_key, "seed-key");

  fs.writeFileSync(seedFile, JSON.stringify({
    providers: { deepseek: { base_url: "https://changed.test/v1", api_key: "changed-key" } },
  }));
  ensureSettingsFile(settingsFile, seedFile);
  assert.equal(JSON.parse(fs.readFileSync(settingsFile, "utf8")).providers.deepseek.api_key, "seed-key");
});

test("system assets deploy once and refresh when source inventory changes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-assets-"));
  const source = path.join(root, "source");
  const target = path.join(root, "data", "system");
  fs.mkdirSync(path.join(source, "workflows"), { recursive: true });
  fs.mkdirSync(path.join(source, "nodes", "example"), { recursive: true });
  fs.writeFileSync(path.join(source, "workflows", "workflow.json"), "{}\n");
  fs.writeFileSync(path.join(source, "nodes", "example", "node.json"), "{}\n");

  assert.equal(deploySystemAssets(source, target), true);
  assert.equal(deploySystemAssets(source, target), false);
  fs.writeFileSync(path.join(source, "workflows", "second.json"), "{}\n");
  assert.equal(deploySystemAssets(source, target), true);
  assert.equal(fs.existsSync(path.join(target, "workflows", "second.json")), true);
  const workflowPath = path.join(source, "workflows", "workflow.json");
  const originalTimes = fs.statSync(workflowPath);
  fs.writeFileSync(workflowPath, "[]\n");
  fs.utimesSync(workflowPath, originalTimes.atime, originalTimes.mtime);
  assert.equal(deploySystemAssets(source, target), true);
  assert.equal(fs.readFileSync(path.join(target, "workflows", "workflow.json"), "utf8"), "[]\n");
});

test("packaged runtime keeps its managed venv in userData", () => {
  const source = fs.readFileSync(path.join(__dirname, "backend_manager.cjs"), "utf8");

  assert.match(source, /preferredVenvDir\(backendRoot, userDataDir, this\.isDev\)/);
  assert.match(source, /if \(!isDev\)[\s\S]*return fallbackVenvDir/);
});

test("database migration marker skips only the matching release", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-db-marker-"));
  const databasePath = path.join(root, "tdease.db");
  fs.writeFileSync(databasePath, "sqlite");
  const manager = new BackendManager({ isDev: true });

  assert.equal(manager._isDatabaseReleaseReady(databasePath, "release-a"), false);
  manager._writeDatabaseReleaseMarker(databasePath, "release-a");
  assert.equal(manager._isDatabaseReleaseReady(databasePath, "release-a"), true);
  assert.equal(manager._isDatabaseReleaseReady(databasePath, "release-b"), false);
});

test("database migration marker never hides a missing database", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tdease-db-missing-"));
  const databasePath = path.join(root, "tdease.db");
  const manager = new BackendManager({ isDev: true });

  manager._writeDatabaseReleaseMarker(databasePath, "release-a");
  assert.equal(manager._isDatabaseReleaseReady(databasePath, "release-a"), false);
});
