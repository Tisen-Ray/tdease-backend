"""Authentication boundary for local and remote Backend deployments.

Local Desktop and development Backends are loopback services owned by the current
user. They use the local-owner principal directly. A remote Server selects Bearer
authentication in Backend JSON.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request

from src.backend_settings import BACKEND_SETTINGS
from src.contracts.errors import ErrorCode, TDEaseError

logger = logging.getLogger(__name__)


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


def _rejection(*, code: ErrorCode, message: str, remedy: str) -> HTTPException:
    """Build an auth rejection carrying the one failure envelope.

    domain and http_status come from code via src/contracts/errors.py; neither is
    a parameter here, because both were free strings at this raise site before and
    that is how AUTH_TOKEN_INVALID came to be served with domain: "backend" -- an
    invalid token is not a Backend fault.

    Still an HTTPException rather than a bare TDEaseError: this is raised from
    inside the desktop_auth middleware, which runs before FastAPI's exception
    handlers can see anything, so the middleware must catch it itself. It carries
    TDEaseError.to_envelope() as its detail, so the body on the wire is the
    envelope and nothing else.

    Never carries details/cause: an auth rejection has nothing secret-free and
    useful to attach, and the secret itself must never be constructed into any
    response or log.
    """

    error = TDEaseError(code=code, message=message, remedy=remedy, retryable=False)
    return HTTPException(
        status_code=error.http_status,
        detail=error.to_envelope(),
        headers={"WWW-Authenticate": "Bearer"},
    )

class DesktopAuth:
    """Mints and enforces the single process-lifetime Desktop Bearer token.

    There is exactly one way to become authenticated: exchange the bootstrap
    secret once for a token, then present that token as `Authorization: Bearer
    <token>`. Everything else is rejected, including the case where no secret
    was ever configured.
    """

    def __init__(self, bootstrap_secret: str | None, *, required: bool = True) -> None:
        self._bootstrap_secret = bootstrap_secret or None
        self._token: str | None = None
        if required and not self._bootstrap_secret:
            # docs/design/THREE-REPOSITORY-ARCHITECTURE.md: "Backend ... requires the
            # bootstrap token." A missing secret is a startup-time configuration
            # error, not a state that implicitly grants access. We log it loudly
            # here (never crash the process): crashing at import time would take
            # every route, including public health checks, down with it, and
            # would reproduce the exact "collection/import aborts everything"
            # failure mode docs/STATUS.md flags elsewhere.
            # Instead `configured` below is permanently False, so
            # `authenticate()` rejects every protected request for the rest of
            # the process's life -- the Backend starts, but nothing protected
            # is reachable until it is restarted with a secret.
            logger.error(
                "startup error: the configured bootstrap secret was not supplied; "
                "authentication cannot succeed and every protected request will "
                "be rejected until the Backend is restarted with a secret."
            )

    @property
    def configured(self) -> bool:
        """True while a still-usable bootstrap secret or minted token exists.

        False forever once constructed without a secret -- there is no
        transition back to a working state short of restarting the process.
        """

        return bool(self._bootstrap_secret or self._token)

    def exchange(self, candidate: str) -> str:
        if not self._bootstrap_secret:
            raise _rejection(
                code=ErrorCode.AUTH_BOOTSTRAP_UNAVAILABLE,
                message=(
                    "The Desktop bootstrap secret was already exchanged for a token, "
                    "or none was supplied when the Backend started."
                ),
                remedy=(
                    "Restart the Backend through the Desktop app so a fresh bootstrap "
                    "secret is minted. A bootstrap secret is single-use by design."
                ),
            )
        if not candidate or not secrets.compare_digest(candidate, self._bootstrap_secret):
            raise _rejection(
                code=ErrorCode.AUTH_BOOTSTRAP_SECRET_INVALID,
                message="The supplied Desktop bootstrap secret does not match.",
                remedy=(
                    "Send the exact secret the Desktop app passed to the Backend at "
                    "startup as the 'X-TDEase-Bootstrap' header."
                ),
            )
        self._token = secrets.token_urlsafe(32)
        self._bootstrap_secret = None
        return self._token

    def authenticate(self, authorization: str | None) -> Principal:
        if not self.configured:
            raise _rejection(
                code=ErrorCode.AUTH_BOOTSTRAP_SECRET_MISSING,
                message=(
                    "No Desktop bootstrap secret was supplied when the Backend "
                    "started, so no request can be authenticated."
                ),
                remedy=(
                    "Restart the Backend through the Desktop app so it receives "
                    "a bootstrap secret before "
                    "starting it."
                ),
            )
        scheme, _, credential = (authorization or "").partition(" ")
        token = self._token
        if scheme.lower() != "bearer" or not token or not credential or not secrets.compare_digest(credential, token):
            raise _rejection(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message=(
                    "The Authorization header is missing, malformed, or does not "
                    "match the active Bearer token."
                ),
                remedy=(
                    "Exchange the bootstrap secret for a Bearer token and send "
                    "it as 'Authorization: Bearer <token>'."
                ),
            )
        return LOCAL_OWNER


desktop_auth = DesktopAuth(
    BACKEND_SETTINGS.bootstrap_secret,
    required=BACKEND_SETTINGS.auth_mode == "bearer",
)
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


PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/healthz",
    "/ready",
    "/api/auth/bootstrap",
    # /api/capabilities must be reachable before a Bearer token exists --
    # it is how the Client discovers the auth scheme in the first place
    # (docs/spec/CAPABILITIES.md section 3, "unauthenticated"; A4's report
    # flagged this exact gap). It carries no secret or user data.
    "/api/capabilities",
    # /openapi.json and /docs are FastAPI's own self-description; gating
    # them behind the same Bearer token they would need to explain how to
    # obtain is the identical bootstrap deadlock. Neither exposes secret or
    # user data -- app.py already hides /docs entirely in production
    # (docs_url=None if TDEASE_ENV=production), and /openapi.json is a
    # static route/schema description, not Run or workspace data.
    "/openapi.json",
    "/docs",
})


async def authenticate_request(request: Request) -> Principal:
    if BACKEND_SETTINGS.auth_mode == "local":
        return LOCAL_OWNER
    # A CORS preflight is never authenticated: the browser sends OPTIONS with
    # no Authorization header by specification, and refuses to send the real
    # request until it is answered. Because `desktop_auth` is registered after
    # CORSMiddleware -- and Starlette runs middleware outermost-last-added --
    # auth saw the preflight first and rejected it with 401, so CORSMiddleware
    # never got to answer it. The browser then reported "blocked by CORS
    # policy: no Access-Control-Allow-Origin header", naming a cause that was
    # not the problem, and EVERY authenticated call from the Client failed:
    # attaching the Authorization header is itself what triggers the preflight.
    #
    # Letting OPTIONS through grants nothing. A preflight returns only CORS
    # headers; it never reaches a route handler, so no data can leave here.
    if request.method == "OPTIONS":
        return LOCAL_OWNER
    if request.url.path in PUBLIC_PATHS:
        return LOCAL_OWNER
    return desktop_auth.authenticate(request.headers.get("Authorization"))
