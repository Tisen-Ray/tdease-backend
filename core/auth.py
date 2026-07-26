"""Process-local authentication for the bundled Desktop backend."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    scopes: tuple[str, ...]
    auth_source: str


LOCAL_OWNER = Principal(
    user_id="local-owner",
    role="owner",
    scopes=("desktop", "workspace:read", "workspace:write", "run:execute"),
    auth_source="desktop-bootstrap",
)


class DesktopAuth:
    def __init__(self, bootstrap_secret: str | None) -> None:
        self._bootstrap_secret = bootstrap_secret
        self._token: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._bootstrap_secret or self._token)

    def exchange(self, candidate: str) -> str:
        if not self._bootstrap_secret:
            raise HTTPException(status_code=410, detail="desktop bootstrap is unavailable")
        if not candidate or not secrets.compare_digest(candidate, self._bootstrap_secret):
            raise HTTPException(status_code=401, detail="invalid desktop bootstrap secret")
        self._token = secrets.token_urlsafe(32)
        self._bootstrap_secret = None
        return self._token

    def authenticate(self, authorization: str | None) -> Principal:
        if not self.enabled:
            return LOCAL_OWNER
        scheme, _, credential = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not self._token or not secrets.compare_digest(credential, self._token):
            raise HTTPException(status_code=401, detail="authentication required")
        return LOCAL_OWNER


desktop_auth = DesktopAuth(os.environ.pop("TDEASE_BOOTSTRAP_SECRET", None))
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/bootstrap")
async def bootstrap(request: Request) -> dict[str, object]:
    token = desktop_auth.exchange(request.headers.get("X-TDEase-Bootstrap", ""))
    return {
        "access_token": token,
        "token_type": "bearer",
        "principal": {
            "user_id": LOCAL_OWNER.user_id,
            "role": LOCAL_OWNER.role,
            "scopes": list(LOCAL_OWNER.scopes),
        },
    }


PUBLIC_PATHS = frozenset({"/", "/health", "/healthz", "/ready", "/api/auth/bootstrap"})


async def authenticate_request(request: Request) -> Principal:
    if request.url.path in PUBLIC_PATHS:
        return LOCAL_OWNER
    return desktop_auth.authenticate(request.headers.get("Authorization"))
