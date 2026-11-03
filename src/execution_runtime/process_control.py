"""Single process-tree kill policy shared by workflow and engine teardown.

A bare terminate() on a parent pid leaves children (topfd/toppic/...) running
unsupervised; engines are started in their own process group precisely so the
whole tree can be taken down in one shot.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)


def kill_tree(pid: int, *, graceful: bool) -> None:
    """Kill the whole process tree rooted at ``pid``.

    ``graceful``: SIGTERM first, wait up to 3s, then SIGKILL (2s more).
    Otherwise SIGKILL immediately. Windows taskkill /T /F covers both cases.
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
            )
            return
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, OSError):
            pgid = None

        def _sig(sig: int) -> None:
            try:
                if pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    os.kill(pid, sig)
            except (ProcessLookupError, OSError):
                pass

        if graceful:
            _sig(signal.SIGTERM)
            _wait_group_exit(pid, timeout=3.0)
            if _alive(pid):
                _sig(signal.SIGKILL)
                _wait_group_exit(pid, timeout=2.0)
        else:
            _sig(signal.SIGKILL)
    except Exception:
        logger.exception("kill_tree failed for pid %s", pid)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True  # exists but owned by another user
    except (ProcessLookupError, OSError):
        return False


def _wait_group_exit(pid: int, timeout: float) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.1)
