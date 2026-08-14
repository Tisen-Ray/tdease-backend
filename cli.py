"""Public Backend command line entrypoint."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdease-backend")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "worker"):
        command = subcommands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        command.add_argument("--allow-env-overrides", action="store_true")
    subcommands.choices["worker"].add_argument("--once", action="store_true")
    return parser


def _select_port(host: str, requested: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, requested))
        return int(probe.getsockname()[1])


def _configure(args: argparse.Namespace):
    from src.backend_settings import configure_backend

    return configure_backend(
        args.config,
        allow_env_overrides=args.allow_env_overrides,
    )


def _worker(args: argparse.Namespace) -> int:
    _configure(args)
    from src.services.run_worker import run_loop

    run_loop(once=args.once)
    return 0


def _serve(args: argparse.Namespace) -> int:
    settings = _configure(args)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    port = _select_port(settings.bind_host, settings.bind_port)
    worker_args = [sys.executable, "-m", "cli", "worker", "--config", str(args.config.resolve())]
    if args.allow_env_overrides:
        worker_args.append("--allow-env-overrides")
    worker = subprocess.Popen(worker_args, cwd=Path(__file__).resolve().parent)

    try:
        import uvicorn

        from app.main import app

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets=None) -> None:
                await super().startup(sockets=sockets)
                if self.started:
                    print(json.dumps({
                        "type": "ready",
                        "baseUrl": f"http://{settings.bind_host}:{port}",
                    }, separators=(",", ":")), flush=True)

        config = uvicorn.Config(
            app,
            host=settings.bind_host,
            port=port,
            log_level=logging_name(settings.log_level),
        )
        ReadyServer(config).run()
        return 0
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()


def logging_name(level: int) -> str:
    import logging

    return logging.getLevelName(level).lower()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "worker":
        return _worker(args)
    return _serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
