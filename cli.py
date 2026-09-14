"""Public Backend command line entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdease-backend")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "worker"):
        command = subcommands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        command.add_argument("--allow-env-overrides", action="store_true")
    subcommands.choices["worker"].add_argument("--once", action="store_true")
    subcommands.choices["worker"].add_argument("--parent-pid", type=int, default=None)
    return parser


def _configure(args: argparse.Namespace):
    from src.backend_settings import configure_backend

    return configure_backend(
        args.config,
        allow_env_overrides=args.allow_env_overrides,
    )


def _worker(args: argparse.Namespace) -> int:
    _configure(args)
    from src.services.run_worker import run_loop

    run_loop(once=args.once, parent_pid=args.parent_pid)
    return 0


def _worker_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "cli",
        "worker",
        "--config",
        str(args.config.resolve()),
        "--parent-pid",
        str(os.getpid()),
    ]
    if args.allow_env_overrides:
        command.append("--allow-env-overrides")
    return command


def _supervise_worker(
    args: argparse.Namespace,
    stop: threading.Event,
    unstable: threading.Event,
    workers: list[subprocess.Popen],
    request_shutdown,
) -> None:
    """Keep one worker process alive, and fail loudly when it cannot stay up.

    A worker that dies unnoticed is this product's worst failure mode: the API
    stays ready, the Client stays connected, and every Run sits QUEUED with no
    error anywhere. The worker is a stateless poller -- claims are reconciled
    from the Journal on startup -- so restarting it is safe. Three crashes
    inside a minute are not a transient fault: mark the Backend unstable and
    ask uvicorn to stop, so the Client sees the process exit and reports it.
    """
    crashes: list[float] = []
    while not stop.is_set():
        started = time.monotonic()
        child = subprocess.Popen(
            _worker_command(args), cwd=Path(__file__).resolve().parent
        )
        workers.append(child)
        while child.poll() is None and not stop.wait(0.5):
            pass
        if stop.is_set():
            return
        print(
            json.dumps(
                {
                    "type": "worker_exited",
                    "code": child.returncode,
                    "uptime_s": round(time.monotonic() - started, 1),
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )
        now = time.monotonic()
        crashes = [stamp for stamp in crashes if now - stamp < 60] + [now]
        if len(crashes) >= 3:
            print(
                json.dumps(
                    {"type": "worker_unstable", "crashes": len(crashes)},
                    separators=(",", ":"),
                ),
                file=sys.stderr,
                flush=True,
            )
            unstable.set()
            request_shutdown()
            return


def _serve(args: argparse.Namespace) -> int:
    settings = _configure(args)
    settings.data_root.mkdir(parents=True, exist_ok=True)

    import uvicorn

    from app.main import app

    stop = threading.Event()
    unstable = threading.Event()
    workers: list[subprocess.Popen] = []

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets=None) -> None:
            await super().startup(sockets=sockets)
            if not self.started:
                return
            # Report the port uvicorn actually bound. No pre-flight probe: a
            # probe would bind, close and then race the real bind.
            try:
                bound = self.servers[0].sockets[0].getsockname()[1]
            except (AttributeError, IndexError, OSError):
                bound = settings.bind_port
            print(
                json.dumps(
                    {
                        "type": "ready",
                        "baseUrl": f"http://{settings.bind_host}:{bound}",
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )

    server = ReadyServer(
        uvicorn.Config(
            app,
            host=settings.bind_host,
            port=settings.bind_port,
            log_level=logging_name(settings.log_level),
        )
    )
    supervisor = threading.Thread(
        target=_supervise_worker,
        args=(
            args,
            stop,
            unstable,
            workers,
            lambda: setattr(server, "should_exit", True),
        ),
        daemon=True,
    )
    supervisor.start()

    try:
        server.run()
        return 1 if unstable.is_set() else 0
    finally:
        stop.set()
        for child in list(workers):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()


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
