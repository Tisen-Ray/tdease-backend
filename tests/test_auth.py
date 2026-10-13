"""DesktopAuth exchange contract: one secret, two scoped principals, one use.

Pins the semantics the Desktop launch depends on: the exchange mints the
owner token (every scope) and the agent token (no irreversible scopes) in ONE
ownership namespace, works exactly once, and fails closed on every other
input.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import DESKTOP_AGENT, LOCAL_OWNER, DesktopAuth
from src.contracts.errors import ErrorCode


def test_exchange_mints_owner_and_agent_principals() -> None:
    auth = DesktopAuth("secret-1")

    tokens = auth.exchange("secret-1")

    owner = auth.authenticate(f"Bearer {tokens['access_token']}")
    agent = auth.authenticate(f"Bearer {tokens['agent_token']}")
    # One ownership namespace: the agent is the owner acting through a scoped
    # delegate, not a second user.
    assert owner.user_id == agent.user_id == LOCAL_OWNER.user_id
    assert owner.role == "owner"
    assert agent.role == DESKTOP_AGENT.role
    # The agent token carries the working scopes but never the irreversible
    # ones -- a hallucinated destructive loop must fail closed at the route.
    assert "run:purge" in owner.scopes
    assert "run:execute" in agent.scopes
    assert "run:purge" not in agent.scopes


def test_exchange_is_single_use() -> None:
    auth = DesktopAuth("secret-1")
    auth.exchange("secret-1")

    with pytest.raises(HTTPException) as rejected:
        auth.exchange("secret-1")

    envelope = rejected.value.detail
    assert envelope["error"]["code"] == ErrorCode.AUTH_BOOTSTRAP_UNAVAILABLE.value


def test_exchange_rejects_a_wrong_secret_and_stays_exchangeable() -> None:
    auth = DesktopAuth("secret-1")

    with pytest.raises(HTTPException) as rejected:
        auth.exchange("wrong-secret")

    assert (
        rejected.value.detail["error"]["code"]
        == ErrorCode.AUTH_BOOTSTRAP_SECRET_INVALID.value
    )
    assert auth.configured, "a failed attempt must not consume the real secret"


def test_constructing_without_a_secret_rejects_every_request() -> None:
    auth = DesktopAuth(None)

    with pytest.raises(HTTPException) as rejected:
        auth.authenticate("Bearer anything")

    assert (
        rejected.value.detail["error"]["code"]
        == ErrorCode.AUTH_BOOTSTRAP_SECRET_MISSING.value
    )
