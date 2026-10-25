"""
The failure contract, as code — transport half.

FAILURE-CONTRACT.md §1 requires every error response to be exactly one envelope.
The envelope, the closed `code` enumeration and the `TDEaseError` exception are
owned by the domain half, `src/contracts/errors.py` (which must not import
FastAPI). This module owns only the FastAPI wiring that turns a raised
`TDEaseError` into that envelope on the wire, and normalises any other transport
error that already carries the envelope.

Dependency direction is `app/` -> `src/` (docs/design/THREE-REPOSITORY-ARCHITECTURE.md
§4.1): transport translates domain errors to HTTP responses; it never re-defines
the contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse

from src.contracts.errors import TDEaseError

__all__ = [
    "http_exception_envelope_handler",
    "register_error_handlers",
    "tdease_error_handler",
]


async def tdease_error_handler(request: Request, exc: TDEaseError) -> JSONResponse:
    """Exception-handler function for `TDEaseError`; registered by `register_error_handlers`."""

    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


async def http_exception_envelope_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Serve an HTTPException whose detail is already the failure envelope as-is.

    Some transport raise sites (app/auth.py's `_rejection`) carry
    `TDEaseError.to_envelope()` as an HTTPException's `detail` so the middleware
    can catch it before FastAPI's exception handlers run. When such an
    HTTPException instead reaches a route handler (e.g. /api/auth/bootstrap),
    Starlette's default handler would wrap the envelope again in `{"detail":
    ...}` — a second, incompatible shape on the wire that no Client can parse
    with the same code path as every other error. This handler unwraps
    envelope-shaped details and defers everything else (plain 4xx, 404 routing,
    ...) to Starlette's default, so non-contract HTTPExceptions behave exactly
    as before.
    """

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    return await http_exception_handler(request, exc)


def register_error_handlers(app: Any) -> None:
    """Register the failure-contract handlers on `app`.

    `TDEaseError` -> the envelope (the contract). An `HTTPException` that already
    carries the envelope -> the envelope as-is; everything else -> default.
    """

    app.add_exception_handler(TDEaseError, tdease_error_handler)
    app.add_exception_handler(HTTPException, http_exception_envelope_handler)
