"""Middleware decision matrix + dependency — 15 cases."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.admin.auth.jwt import sign_access_token
from app.admin.auth.middleware import (
    AUTH_WHITELIST_PREFIXES,
    FORCE_CHANGE_WHITELIST_PREFIXES,
    decide_admin_auth,
    is_api_path,
    is_whitelisted,
    require_admin_session,
)


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ADMIN_JWT_SECRET",
        "x" * 64,
    )


# ---------------------------------------------------------------------------
# Pure helpers (3 cases)
# ---------------------------------------------------------------------------


def test_is_api_path_recognises_admin_api_prefix() -> None:
    assert is_api_path("/admin/api/v1/auth/login") is True
    assert is_api_path("/admin/dashboard") is False
    assert is_api_path("/admin") is False


def test_is_whitelisted_matches_each_anonymous_prefix() -> None:
    for prefix in AUTH_WHITELIST_PREFIXES:
        assert is_whitelisted(prefix) is True
        assert is_whitelisted(prefix + "/anything") is True


def test_force_change_whitelist_membership() -> None:
    # change-password page + change-password API + logout API are reachable
    # while force_password_change_at is set; everything else is gated.
    assert "/admin/change-password" in FORCE_CHANGE_WHITELIST_PREFIXES
    assert "/admin/api/v1/auth/change-password" in FORCE_CHANGE_WHITELIST_PREFIXES
    assert "/admin/api/v1/auth/logout" in FORCE_CHANGE_WHITELIST_PREFIXES


# ---------------------------------------------------------------------------
# decide_admin_auth — anonymous-whitelist short-circuits (2 cases)
# ---------------------------------------------------------------------------


def test_login_page_allows_without_token() -> None:
    decision = decide_admin_auth(
        pathname="/admin/login",
        access_token_cookie=None,
        force_password_change_at=None,
    )
    assert decision.action == "allow"


def test_refresh_endpoint_allowed_without_access_cookie() -> None:
    # /admin/api/v1/auth/refresh is whitelisted because the access token
    # has by definition expired when refresh is called.
    decision = decide_admin_auth(
        pathname="/admin/api/v1/auth/refresh",
        access_token_cookie=None,
        force_password_change_at=None,
    )
    assert decision.action == "allow"


# ---------------------------------------------------------------------------
# decide_admin_auth — no-token paths (3 cases)
# ---------------------------------------------------------------------------


def test_no_token_on_page_redirects_to_login() -> None:
    decision = decide_admin_auth(
        pathname="/admin/dashboard",
        access_token_cookie=None,
        force_password_change_at=None,
    )
    assert decision.action == "redirect"
    assert decision.target == "/admin/login"
    assert decision.reason == "no_session"


def test_no_token_on_api_returns_unauthorized() -> None:
    decision = decide_admin_auth(
        pathname="/admin/api/v1/users",
        access_token_cookie=None,
        force_password_change_at=None,
    )
    assert decision.action == "unauthorized"
    assert decision.reason == "no_session"
    assert decision.target is None


def test_empty_string_cookie_is_treated_as_missing() -> None:
    decision = decide_admin_auth(
        pathname="/admin/dashboard",
        access_token_cookie="",
        force_password_change_at=None,
    )
    assert decision.action == "redirect"
    assert decision.target == "/admin/login"


# ---------------------------------------------------------------------------
# decide_admin_auth — force-change-password gating (4 cases)
# ---------------------------------------------------------------------------


def test_force_change_redirects_normal_page_to_change_password() -> None:
    decision = decide_admin_auth(
        pathname="/admin/dashboard",
        access_token_cookie="opaque",
        force_password_change_at=datetime.now(UTC),
    )
    assert decision.action == "redirect"
    assert decision.target == "/admin/change-password"
    assert decision.reason == "force_password_change"


def test_force_change_unauthorizes_normal_api_call() -> None:
    decision = decide_admin_auth(
        pathname="/admin/api/v1/users",
        access_token_cookie="opaque",
        force_password_change_at=datetime.now(UTC),
    )
    assert decision.action == "unauthorized"
    assert decision.reason == "force_password_change"


def test_force_change_allows_change_password_page() -> None:
    decision = decide_admin_auth(
        pathname="/admin/change-password",
        access_token_cookie="opaque",
        force_password_change_at=datetime.now(UTC),
    )
    assert decision.action == "allow"


def test_force_change_allows_logout_so_user_can_bail_out() -> None:
    decision = decide_admin_auth(
        pathname="/admin/api/v1/auth/logout",
        access_token_cookie="opaque",
        force_password_change_at=datetime.now(UTC),
    )
    assert decision.action == "allow"


# ---------------------------------------------------------------------------
# decide_admin_auth — happy path + dependency (3 cases)
# ---------------------------------------------------------------------------


def test_valid_cookie_no_force_change_allows() -> None:
    decision = decide_admin_auth(
        pathname="/admin/dashboard",
        access_token_cookie="opaque",
        force_password_change_at=None,
    )
    assert decision.action == "allow"


def test_require_admin_session_returns_payload_for_valid_token() -> None:
    token, _ = sign_access_token(admin_user_id="user-id-1")
    payload = require_admin_session(access_token=token)
    assert payload.sub == "user-id-1"
    assert payload.aud == "genpano-admin-access"


def test_require_admin_session_raises_401_when_cookie_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        require_admin_session(access_token=None)
    assert exc.value.status_code == 401
    detail: object = exc.value.detail
    assert detail == {"reason": "no_session"}


def test_require_admin_session_surfaces_jwt_invalid_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mint a token under one secret then verify under a different secret —
    # the dependency must surface reason='signature' to the caller.
    token, _ = sign_access_token(admin_user_id="user-id-2")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "y" * 64)
    # Force the lru_cache nothing — _load_secret reads env each call.
    assert os.environ["ADMIN_JWT_SECRET"] == "y" * 64
    with pytest.raises(HTTPException) as exc:
        require_admin_session(access_token=token)
    assert exc.value.status_code == 401
    detail: object = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["reason"] in {"signature", "claims", "malformed"}
