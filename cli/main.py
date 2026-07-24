"""
TDEase CLI — 统一命令行入口。

所有命令走 HTTP 或直接文件操作，不使用独立后端抽象。
Agent 和用户使用同一 CLI。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import hashlib
from pathlib import Path

VERSION = "0.2.0"

# --- 状态常量（来自 src.contracts.enums）---
STATUS_LABELS = {
    "QUEUED": "[Q]",
    "RUNNING": "[R]",
    "SUCCEEDED": "[OK]",
    "FAILED": "[FAIL]",
    "CANCELLED": "[X]",
}
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, "?")


def _server_url() -> str:
    return os.environ.get("TDEASE_SERVER", os.environ.get("TDEASE_SERVER_URL", "http://localhost:8000"))


async def _api(method: str, path: str, **kwargs) -> dict | list | None:
    """薄 HTTP 客户端 — Desktop/CLI/Agent 共用，不引入独立后端抽象。"""
    import urllib.request
    import urllib.error

    url = f"{_server_url()}{path}"
    body = kwargs.pop("body", None)
    headers = kwargs.pop("headers", {})
    if body is not None:
        headers.setdefault("Content-Type", "application/json")
        data = json.dumps(body).encode()
    else:
        data = None
    raw_body = kwargs.pop("raw_body", None)
    if raw_body is not None:
        data = raw_body

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=kwargs.get("timeout", 30)) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        try:
            detail = json.loads(err_body).get("detail", err_body)
        except json.JSONDecodeError:
            detail = err_body
        print(f"HTTP {e.code}: {detail}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"连接失败: {e}", file=sys.stderr)
        return None


def _usage():
    print("""TDEase — AI 质谱分析平台

命令:
  tdease version                 版本信息
  tdease server start            启动服务端
  tdease workspace init PATH     初始化 workspace
  tdease submit [--workspace PATH] [--json]  提交运行
  tdease status <run_id>         查询状态
  tdease wait <run_id>           等待完成
  tdease events <run_id>         事件流
  tdease pull <run_id>           拉取结果
  tdease log <run_id> [N]        查看日志
  tdease run list                历史运行
  tdease cancel <run_id>         取消运行
  tdease config get/set          配置管理
  tdease migrate inspect DIR     扫描旧项目
  tdease migrate assets SRC DST  迁移资产
""")


def _version(args):
    if "--json" in args:
        print(json.dumps({"version": VERSION, "name": "TDEase-zero"}))
    else:
        print(f"TDEase-zero v{VERSION}")


def _server(args):
    if not args:
        print("用法: tdease server start|token", file=sys.stderr)
        sys.exit(1)
    sub = args[0]
    if sub == "start":
        _server_start(args[1:])
    elif sub == "token":
        _server_token(args[1:])
    else:
        print(f"未知 server 子命令: {sub}", file=sys.stderr)
        sys.exit(1)


def _server_start(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="server-data")
    parser.add_argument("--port", type=int, default=8000)
    opts, _ = parser.parse_known_args(args)
    os.environ["TDEASE_DATA_ROOT"] = opts.data_root
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=opts.port, reload=False, log_level="info")


def _server_token(args):
    if not args or args[0] != "create":
        print("用法: tdease server token create --name NAME --scope user|agent --json", file=sys.stderr)
        return
    import uuid
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="test")
    parser.add_argument("--scope", default="user")
    parser.add_argument("--json", action="store_true")
    opts = parser.parse_args(args[1:])
    tok = {"token": "tk_" + uuid.uuid4().hex, "scope": opts.scope, "name": opts.name}
    print(json.dumps(tok))


def _workspace(args):
    if not args or args[0] != "init":
        print("用法: tdease workspace init PATH", file=sys.stderr)
        sys.exit(1)
    ws_path = Path(args[1]).resolve()
    ws_path.mkdir(parents=True, exist_ok=True)
    identity_dir = ws_path / ".tdease"
    identity_dir.mkdir(exist_ok=True)
    import uuid as _uuid
    identity = {
        "workspace_id": "ws_" + _uuid.uuid4().hex[:8],
        "name": ws_path.name,
        "owner": "local",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (identity_dir / "workspace.json").write_text(json.dumps(identity, indent=2))
    print(f"- workspace 初始化: {ws_path}")


async def _submit(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", "-w", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--dry-run", action="store_true")
    opts, extra = parser.parse_known_args(args)

    ws = Path(opts.workspace).resolve()
    snakefile_path = ws / "Snakefile"
    if extra:
        maybe = Path(extra[0])
        if maybe.exists() and maybe.suffix == ".smk":
            ws = maybe.parent.resolve()
            snakefile_path = maybe.resolve()

    if not snakefile_path.exists():
        print(f"x Snakefile 不存在: {snakefile_path}", file=sys.stderr)
        sys.exit(1)

    import uuid
    snakefile_content = snakefile_path.read_text(encoding="utf-8")
    idem_key = opts.idempotency_key or f"ik_{uuid.uuid4().hex[:12]}"

    local_files = [snakefile_path]
    candidates = [ws / "config.yaml"]
    if (ws / "scripts").is_dir():
        candidates.extend(sorted((ws / "scripts").rglob("*")))
    for candidate in candidates:
        if candidate.is_file():
            local_files.append(candidate)
    local_files.extend(sorted(p for p in ws.glob("*.smk") if p.is_file() and p != snakefile_path))
    entries = []
    payloads = {}
    for path in local_files:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        rel = path.relative_to(ws).as_posix()
        entries.append({"path": rel, "blob_hash": digest, "size": len(data), "mode": "file", "executable": False})
        payloads[digest] = data
    data_map_path = ws / ".tdease" / "data-map.json"
    if data_map_path.is_file():
        entries.extend(json.loads(data_map_path.read_text(encoding="utf-8")))
    entries.sort(key=lambda item: item["path"])
    tree_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    tree_hash = hashlib.sha256(tree_bytes).hexdigest()
    if opts.dry_run:
        print(json.dumps({"files": entries, "total_bytes": sum(x["size"] for x in entries)}))
        return
    negotiation = await _api("POST", "/api/v2/uploads/manifest", body={"entries": entries})
    if not negotiation:
        sys.exit(1)
    missing = set(negotiation["missing"])
    unavailable = missing - payloads.keys()
    if unavailable:
        print(f"x 服务端缺少已映射数据 blob: {sorted(unavailable)}；请重新 push-data", file=sys.stderr)
        sys.exit(1)
    for digest in sorted(missing):
        result = await _api("PUT", f"/api/v2/uploads/{digest}", raw_body=payloads[digest])
        if not result:
            sys.exit(1)

    commit = {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "idempotency_key": idem_key,
        "workspace_id": "ws_local",
        "workspace_tree_hash": tree_hash,
        "workspace_files": entries,
        "snakefile": snakefile_content,
        "config": {},
        "cores": 4,
        "user_id": "local",
        "mode": "local",
        "packages": [],
        "nodes": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "labels": {},
    }

    result = await _api("POST", "/api/v2/runs", body={"commit": commit})
    if result:
        if opts.json:
            print(json.dumps(result))
        else:
            dup = " (幂等)" if result.get("idempotent") else ""
            print(f"- 已提交: {result['run_id']} ({result.get('status', '?')}){dup}")


async def _push_data(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--workspace", "-w", default=".")
    parser.add_argument("--json", action="store_true")
    opts = parser.parse_args(args)
    ws = Path(opts.workspace).resolve()
    source = (ws / opts.path).resolve() if not Path(opts.path).is_absolute() else Path(opts.path).resolve()
    if not source.is_file():
        print(f"x 数据文件不存在: {source}", file=sys.stderr)
        sys.exit(1)
    try:
        rel = source.relative_to(ws).as_posix()
    except ValueError:
        print("x 数据必须位于 workspace 内；请先放入本地 workspace", file=sys.stderr)
        sys.exit(1)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    entry = {"path": rel, "blob_hash": digest, "size": source.stat().st_size,
             "mode": "file", "executable": False}
    negotiation = await _api("POST", "/api/v2/uploads/manifest", body={"entries": [entry]})
    if negotiation and digest in negotiation["missing"]:
        if not await _api("PUT", f"/api/v2/uploads/{digest}", raw_body=source.read_bytes(), timeout=3600):
            sys.exit(1)
    map_path = ws / ".tdease" / "data-map.json"
    existing = json.loads(map_path.read_text(encoding="utf-8")) if map_path.is_file() else []
    existing = [item for item in existing if item["path"] != rel] + [entry]
    map_path.write_text(json.dumps(sorted(existing, key=lambda x: x["path"]), indent=2), encoding="utf-8")
    print(json.dumps({"path": rel, "sha256": digest, "size": entry["size"]}))


async def _status(args):
    if not args:
        print("用法: tdease status <run_id> --json", file=sys.stderr)
        return
    run_id = args[0]
    use_json = "--json" in args
    result = await _api("GET", f"/api/v2/runs/{run_id}")
    if not result:
        print(json.dumps({"error": "not_found"}) if use_json else f"x 未找到: {run_id}")
        return
    if use_json:
        print(json.dumps(result))
    else:
        print(f"{_status_label(result.get('status', '?'))} {run_id}: {result.get('status')}")


async def _wait(args):
    if not args:
        print("用法: tdease wait <run_id> --timeout SEC --json", file=sys.stderr)
        return
    run_id = args[0]
    timeout_sec = 180
    use_json = "--json" in args
    for i, a in enumerate(args):
        if a == "--timeout" and i + 1 < len(args):
            timeout_sec = int(args[i + 1])

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        result = await _api("GET", f"/api/v2/runs/{run_id}")
        if not result:
            if use_json:
                print(json.dumps({"error": "not_found"}))
            return
        status = result.get("status", "")
        if status in TERMINAL_STATUSES:
            if use_json:
                print(json.dumps(result))
            else:
                print(f"{status}: {run_id}")
            return
        await asyncio.sleep(0.5)
    print(json.dumps({"error": "timeout"}), file=sys.stderr)


async def _events(args):
    if not args:
        print("用法: tdease events <run_id> --json", file=sys.stderr)
        return
    run_id = args[0]
    data_root = Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))
    events_file = data_root / "runs" / run_id / "events.jsonl"
    if events_file.exists():
        events = [json.loads(line) for line in events_file.read_text().strip().splitlines() if line.strip()]
        print(json.dumps({"events": events}))
    else:
        result = await _api("GET", f"/api/v2/runs/{run_id}")
        print(json.dumps({"events": [], "status": result.get("status") if result else None}))


async def _pull(args):
    if not args:
        print("用法: tdease pull <run_id> --dest DIR", file=sys.stderr)
        return
    run_id = args[0]
    dest = "."
    for i, a in enumerate(args):
        if a == "--dest" and i + 1 < len(args):
            dest = args[i + 1]
    dest_dir = Path(dest) / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    data_root = Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))
    run_dir = data_root / "runs" / run_id
    if not run_dir.exists():
        print(f"x Run 目录不存在: {run_dir}", file=sys.stderr)
        return
    import shutil
    for f in run_dir.rglob("*"):
        if f.is_file() and f.suffix != ".jsonl":
            rel = f.relative_to(run_dir)
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            print(f"-> {rel}")


async def _run(args):
    if not args or args[0] != "list":
        print("用法: tdease run list --json", file=sys.stderr)
        return
    use_json = "--json" in args
    result = await _api("GET", "/api/v2/runs")
    if not result:
        print(json.dumps({"runs": []}))
        return
    runs = result.get("runs", [])
    if use_json:
        print(json.dumps({"runs": runs}))
    else:
        for r in runs:
            print(f"{_status_label(r.get('status', '?'))} {r['run_id']}  {r.get('status', '?'):10s}  {r.get('created_at', '')}")


async def _cancel(args):
    if not args:
        print("用法: tdease cancel <run_id>", file=sys.stderr)
        return
    result = await _api("POST", f"/api/v2/runs/{args[0]}/cancel")
    print(f"{'- 已取消' if result else 'x 无法取消'} {args[0]}")


async def _log(args):
    if not args:
        print("用法: tdease log <run_id> [N]", file=sys.stderr)
        return
    run_id = args[0]
    lines = int(args[1]) if len(args) > 1 else 50
    data_root = Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))
    events_file = data_root / "runs" / run_id / "events.jsonl"
    if events_file.exists():
        all_lines = events_file.read_text().strip().splitlines()
        for line in all_lines[-lines:]:
            if line.strip():
                try:
                    evt = json.loads(line)
                    if evt.get("type") in ("LOG_STDOUT", "LOG_STDERR"):
                        print(evt.get("data", {}).get("text", ""), end="")
                except json.JSONDecodeError:
                    pass
    else:
        print("(无日志)")


async def _migrate(args):
    """委托给 cli/migrate.py。"""
    from cli.migrate import main as migrate_main
    # 临时替换 sys.argv 以适配 migrate.py 的 argparse
    old_argv = sys.argv
    sys.argv = ["tdease migrate"] + args
    try:
        migrate_main()
    finally:
        sys.argv = old_argv


def _config(args):
    config_dir = Path.home() / ".tdease"
    config_file = config_dir / "config.yaml"
    if not args:
        print(f"配置文件: {config_file}")
        if config_file.exists():
            print(config_file.read_text())
        else:
            print("（未配置）")
        return
    sub = args[0]
    if sub == "get":
        key = args[1] if len(args) > 1 else None
        _config_get(config_file, key)
    elif sub == "set":
        if len(args) < 3:
            print("用法: tdease config set <key> <value>", file=sys.stderr)
            return
        _config_set(config_file, args[1], args[2])
    else:
        print(f"未知 config 子命令: {sub}", file=sys.stderr)


def _config_get(config_file, key):
    import yaml
    if not config_file.exists():
        print("{}")
        return
    cfg = yaml.safe_load(config_file.read_text()) or {}
    if key:
        print(cfg.get(key, ""))
    else:
        print(json.dumps(cfg, indent=2, default=str))


def _config_set(config_file, key, value):
    import yaml
    config_file.parent.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(config_file.read_text()) if config_file.exists() else {}
    cfg[key] = value
    config_file.write_text(yaml.dump(cfg, default_flow_style=False))


def main():
    if len(sys.argv) <= 1 or sys.argv[1] in ("-h", "--help"):
        _usage()
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    handlers = {
        "version": lambda: _version(args),
        "server": lambda: _server(args),
        "workspace": lambda: _workspace(args),
        "config": lambda: _config(args),
    }
    async_handlers = {
        "submit": _submit, "status": _status, "wait": _wait,
        "events": _events, "pull": _pull, "run": _run,
        "cancel": _cancel, "log": _log, "migrate": _migrate,
        "push-data": _push_data,
    }

    if cmd in handlers:
        handlers[cmd]()
    elif cmd in async_handlers:
        asyncio.run(async_handlers[cmd](args))
    else:
        print(f"未知命令: {cmd}", file=sys.stderr)
        _usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
