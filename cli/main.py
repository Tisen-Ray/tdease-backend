"""
TDEase CLI — 统一命令行入口。

用法:
  tdease submit <workspace>        提交运行
  tdease status <run_id>           查询状态
  tdease pull <run_id>             拉取结果
  tdease log <run_id>              查看日志
  tdease list [workspace]          列出历史运行
  tdease cancel <run_id>           取消运行
  tdease server start              启动服务端
  tdease config [set|get]          配置管理
  tdease --help
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _usage()
        return

    cmd = args[0]
    cmd_args = args[1:]

    if cmd == "server":
        _server(cmd_args)
    elif cmd == "config":
        _config(cmd_args)
    else:
        asyncio.run(_client_cmd(cmd, cmd_args))


# ------------------------------------------------------------------
# 客户端命令
# ------------------------------------------------------------------

async def _client_cmd(cmd: str, args: list[str]):
    from src.backends.resolver import resolve_backend
    backend = resolve_backend()

    try:
        if cmd == "submit":
            if len(args) < 1:
                print("用法: tdease submit <workspace> 或 tdease submit <workspace>/Snakefile")
                return
            ws = args[0]
            snakefile = f"{ws}/Snakefile"
            if Path(args[0]).exists() and args[0].endswith(".smk"):
                ws = str(Path(args[0]).parent)
                snakefile = args[0]
            run = await backend.submit(workspace=ws, snakefile=snakefile)
            print(f"✓ 已提交: {run.id} (QUEUED)")

        elif cmd == "status":
            if len(args) < 1:
                print("用法: tdease status <run_id>")
                return
            run = await backend.status(args[0])
            if not run:
                print(f"✗ 未找到: {args[0]}")
                return
            icon = {"QUEUED": "⏳", "RUNNING": "🔄", "DONE": "✅", "FAILED": "❌"}.get(run.status, "?")
            print(f"{icon} {run.id}: {run.status}")
            if run.pid:
                print(f"   PID: {run.pid}")
            if run.error:
                print(f"   错误: {run.error}")

        elif cmd == "pull":
            if len(args) < 1:
                print("用法: tdease pull <run_id> [pattern]")
                return
            pattern = args[1] if len(args) > 1 else "results/**"
            files = await backend.pull(args[0], patterns=[pattern])
            for f in files:
                print(f"↓ {f}")
            print(f"✓ 已拉取 {len(files)} 个文件")

        elif cmd == "log":
            if len(args) < 1:
                print("用法: tdease log <run_id>")
                return
            lines = int(args[1]) if len(args) > 1 else 50
            log = await backend.tail_log(args[0], lines=lines)
            print(log, end="")

        elif cmd == "list":
            ws = args[0] if args else "."
            runs = await backend.list_runs(ws)
            for r in runs:
                icon = {"QUEUED": "⏳", "RUNNING": "🔄", "DONE": "✅", "FAILED": "❌"}.get(r.status, "?")
                print(f"{icon} {r.id}  {r.status:8s}  {r.created_at}")

        elif cmd == "cancel":
            if len(args) < 1:
                print("用法: tdease cancel <run_id>")
                return
            ok = await backend.cancel(args[0])
            print(f"{'✓ 已取消' if ok else '✗ 无法取消'} {args[0]}")

        else:
            print(f"未知命令: {cmd}")
            _usage()
    finally:
        if hasattr(backend, "close"):
            await backend.close()


# ------------------------------------------------------------------
# 服务端命令
# ------------------------------------------------------------------

def _server(args: list[str]):
    if not args:
        print("用法: tdease server start|status|stop")
        return
    sub = args[0]
    if sub == "start":
        print("启动 TDEase Server...")
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    elif sub == "status":
        print("TDEase Server 状态查询: 未实现")
    elif sub == "stop":
        print("停止服务: 未实现")
    else:
        print(f"未知 server 子命令: {sub}")


# ------------------------------------------------------------------
# 配置命令
# ------------------------------------------------------------------

def _config(args: list[str]):
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
            print("用法: tdease config set <key> <value>")
            return
        _config_set(config_file, args[1], args[2])
    else:
        print(f"未知 config 子命令: {sub}")


def _config_get(config_file: Path, key: str | None):
    import yaml
    if not config_file.exists():
        print("{}")
        return
    cfg = yaml.safe_load(config_file.read_text()) or {}
    if key:
        print(cfg.get(key, ""))
    else:
        import json
        print(json.dumps(cfg, indent=2, default=str))


def _config_set(config_file: Path, key: str, value: str):
    import yaml
    config_file.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if config_file.exists():
        cfg = yaml.safe_load(config_file.read_text()) or {}
    cfg[key] = value
    config_file.write_text(yaml.dump(cfg, default_flow_style=False))


def _usage():
    print("""TDEase — AI 质谱分析平台

命令:
  tdease submit <workspace>    提交运行
  tdease status <run_id>       查询状态
  tdease pull <run_id>         拉取结果
  tdease log <run_id> [N]      查看日志
  tdease list [workspace]      历史运行
  tdease cancel <run_id>       取消运行
  tdease server start          启动服务端
  tdease config get/set        配置管理

模式自动检测:
  无 --server → Pure Desktop (本地直接跑)
  --server URL → Desktop+Server (HTTP通信)
  设置 TDEASE_SERVER 环境变量或 ~/.tdease/config.yaml

示例:
  tdease submit /data/my-project
  tdease status run_a1b2c3
  tdease pull run_a1b2c3 "*.csv"
  tdease server start
""")


if __name__ == "__main__":
    main()
