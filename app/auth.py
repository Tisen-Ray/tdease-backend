"""Authentication boundary for local and remote Backend deployments.

Local Desktop and development Backends are loopback services owned by the current
user. They use the local-owner principal directly. A remote Server selects Bearer
authentication in Backend JSON.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request

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
    scopes=("desktop", "workspace:read", "workspace:write", "run:execute", "run:purge"),
    auth_source="desktop-bootstrap",
)

# The AI agent harness runs as a second launch-time principal with the same
# working scopes but WITHOUT the irreversible ones: a hallucinated call loop
# must never be able to purge (or otherwise destroy) the user's Runs. The
# Desktop launcher exchanges one bootstrap secret for both tokens and hands
# each to its own client.
DESKTOP_AGENT = Principal(
    user_id="local-agent",
    role="agent",
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
    """Mints and enforces the process-lifetime Desktop Bearer tokens.

    There is exactly one way to become authenticated: exchange the bootstrap
    secret once for the launch's token pair, then present a token as
    `Authorization: Bearer <token>`. The single-use exchange mints TWO tokens
    from one secret -- the owner token (full scopes) and the agent token
    (no irreversible scopes) -- because one launch owns two clients with
    different blast radii: the Desktop UI and the AI agent harness.
    Everything else is rejected, including the case where no secret was ever
    configured.
    """

    def __init__(self, bootstrap_secret: str | None, *, required: bool = True) -> None:
        self._bootstrap_secret = bootstrap_secret or None
        self._tokens: dict[str, Principal] = {}
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

        return bool(self._bootstrap_secret or self._tokens)

    def exchange(self, candidate: str) -> dict[str, str]:
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
        tokens = {
            "access_token": secrets.token_urlsafe(32),
            "agent_token": secrets.token_urlsafe(32),
        }
        self._tokens = {
            tokens["access_token"]: LOCAL_OWNER,
            tokens["agent_token"]: DESKTOP_AGENT,
        }
        self._bootstrap_secret = None
        return tokens

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
        if scheme.lower() != "bearer" or not credential:
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
        for token, principal in self._tokens.items():
            if secrets.compare_digest(credential, token):
                return principal
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


def require_scope(scope: str):
    """Route dependency: the authenticated principal must hold `scope`.

    Scopes are the ceiling on a principal's blast radius -- the agent token
    deliberately lacks the irreversible ones (e.g. run:purge), so a
    hallucinated destructive call loop fails closed at the route.
    """

    def _checker(request: Request) -> None:
        principal = getattr(request.state, "principal", None)
        if scope not in getattr(principal, "scopes", ()):
            raise TDEaseError(
                code=ErrorCode.AUTH_SCOPE_DENIED,
                message=(
                    f"this action requires the '{scope}' scope, which the "
                    "authenticated principal does not hold"
                ),
                remedy="Perform the action from the Desktop client, whose token holds every scope.",
                retryable=False,
            )

    return Depends(_checker)


desktop_auth = DesktopAuth(
    BACKEND_SETTINGS.bootstrap_secret,
    required=BACKEND_SETTINGS.auth_mode == "bearer",
)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/bootstrap")
async def bootstrap(request: Request) -> dict[str, object]:
    tokens = desktop_auth.exchange(request.headers.get("X-TDEase-Bootstrap", ""))
    return {
        "access_token": tokens["access_token"],
        # The agent token is handed to the AI agent harness only; it holds the
        # working scopes but not the irreversible ones (run:purge).
        "agent_token": tokens["agent_token"],
        "token_type": "bearer",
        "principal": {
            "user_id": LOCAL_OWNER.user_id,
            "role": LOCAL_OWNER.role,
            "scopes": list(LOCAL_OWNER.scopes),
        },
        "agent_principal": {
            "user_id": DESKTOP_AGENT.user_id,
            "role": DESKTOP_AGENT.role,
            "scopes": list(DESKTOP_AGENT.scopes),
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
