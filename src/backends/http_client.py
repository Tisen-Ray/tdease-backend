"""
ServerBackend — Desktop + Server / Cloud 模式。

通过 HTTP 与后端通信。和 Cloud 模式共用同一套协议。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx

from src.backends.base import WorkspaceBackend, RunInfo

logger = logging.getLogger(__name__)


class ServerBackend(WorkspaceBackend):
    """通过 HTTP 与服务端通信。Cloud 模式也是这个实现，只认证方式不同。"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    # ------------------------------------------------------------------
    # 接口实现
    # ------------------------------------------------------------------

    async def submit(
        self,
        workspace: str,
        snakefile: str,
        config: Optional[dict] = None,
        cores: int = 4,
    ) -> RunInfo:
        data = {
            "workspace": workspace,
            "snakefile": snakefile,
            "config": config,
            "cores": cores,
        }
        resp = await self.client.post("/api/runs", json=data)
        resp.raise_for_status()
        return RunInfo(**resp.json())

    async def status(self, run_id: str) -> Optional[RunInfo]:
        resp = await self.client.get(f"/api/runs/{run_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return RunInfo(**resp.json())

    async def pull(
        self,
        run_id: str,
        patterns: list[str] | None = None,
        dest: str | Path | None = None,
    ) -> list[str]:
        params = {"patterns": patterns or ["results/**"]}
        resp = await self.client.get(
            f"/api/runs/{run_id}/files",
            params=params,
            follow_redirects=True,
        )
        resp.raise_for_status()
        files = resp.json()

        dest = Path(dest or Path.cwd() / "downloads" / run_id)
        dest.mkdir(parents=True, exist_ok=True)
        pulled = []
        for f in files:
            target = dest / f["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f["content"].encode() if isinstance(f["content"], str) else f["content"])
            pulled.append(str(target))
        return pulled

    async def fetch(self, run_id: str, path: str) -> Optional[Path]:
        resp = await self.client.get(f"/api/runs/{run_id}/files/{path}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        cache = Path.cwd() / ".tdease" / "cache" / run_id / path
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(resp.content)
        return cache

    async def tail_log(self, run_id: str, lines: int = 50) -> str:
        resp = await self.client.get(
            f"/api/runs/{run_id}/log",
            params={"lines": lines},
        )
        resp.raise_for_status()
        return resp.text

    async def list_runs(self, workspace: str) -> list[RunInfo]:
        params = {"workspace": workspace}
        resp = await self.client.get("/api/runs", params=params)
        resp.raise_for_status()
        return [RunInfo(**item) for item in resp.json()]

    async def cancel(self, run_id: str) -> bool:
        resp = await self.client.post(f"/api/runs/{run_id}/cancel")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return resp.json().get("cancelled", False)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
