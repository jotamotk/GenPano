"""Hotfix #4 — decouple admin cookie ``Secure`` flag from GENPANO_ENVIRONMENT.

Originally backend/app/main.py wired the admin session cookie's ``Secure``
attribute to ``GENPANO_ENVIRONMENT == "production"``. That broke any
HTTP-only "production" deployment (internal IP / no TLS): every
``Set-Cookie`` carried ``Secure``, browsers silently dropped it, login
appeared to succeed but every subsequent ``/api/admin/*`` request 401-ed
with ``admin_session_required``. This was the actual root cause behind
the topic-plan / prompt-matrix 401s reported in #347 / #353 / #355 —
those PRs all repaired downstream symptoms.

The fix introduces an explicit ``ADMIN_COOKIE_SECURE`` env var and keeps
``GENPANO_ENVIRONMENT`` as a backwards-compat fallback. This test file
exercises the resolver in isolation (``_admin_cookie_secure``) so the
gate logic is locked in even though the live ``SessionMiddleware``
decision is captured at import time and can't easily be re-tested per
case in the same process.
"""

from __future__ import annotations

import pytest


def test_explicit_admin_cookie_secure_1_returns_true(monkeypatch: pytest.MonkeyPatch):
    """ADMIN_COOKIE_SECURE=1 → Secure flag, regardless of GENPANO_ENVIRONMENT."""
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", "1")
    monkeypatch.setenv("GENPANO_ENVIRONMENT", "development")
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is True


@pytest.mark.parametrize("value", ["true", "TRUE", "yes", "On", "1"])
def test_truthy_admin_cookie_secure_returns_true(monkeypatch: pytest.MonkeyPatch, value: str):
    """Common truthy spellings all turn Secure on."""
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", value)
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", ""])
def test_falsy_admin_cookie_secure_returns_false_even_if_production(
    monkeypatch: pytest.MonkeyPatch, value: str
):
    """ADMIN_COOKIE_SECURE explicitly false beats GENPANO_ENVIRONMENT=production.

    This is the user's exact failure mode (#347/#353/#355): production
    deploy on plain HTTP needs to disable Secure or every request 401s.
    """
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", value)
    monkeypatch.setenv("GENPANO_ENVIRONMENT", "production")
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is False, (
        f"ADMIN_COOKIE_SECURE={value!r} must override GENPANO_ENVIRONMENT=production"
    )


def test_unset_admin_cookie_secure_falls_back_to_environment_production(
    monkeypatch: pytest.MonkeyPatch,
):
    """When ADMIN_COOKIE_SECURE is unset, fall back to legacy gate."""
    monkeypatch.delenv("ADMIN_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("GENPANO_ENVIRONMENT", "production")
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is True


def test_unset_admin_cookie_secure_dev_environment_returns_false(
    monkeypatch: pytest.MonkeyPatch,
):
    """No env signal at all → no Secure flag (sensible local-dev default)."""
    monkeypatch.delenv("ADMIN_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("GENPANO_ENVIRONMENT", "development")
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is False


def test_unset_both_returns_false(monkeypatch: pytest.MonkeyPatch):
    """No GENPANO_ENVIRONMENT and no ADMIN_COOKIE_SECURE → no Secure."""
    monkeypatch.delenv("ADMIN_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("GENPANO_ENVIRONMENT", raising=False)
    from app.main import _admin_cookie_secure

    assert _admin_cookie_secure() is False


# Note: ``_ADMIN_COOKIE_SECURE`` is captured at import time and threaded
# into both ``SessionMiddleware(https_only=...)`` and the bad-cookie
# self-heal exception handler. We don't reload the module per test (the
# live FastAPI app is shared with every other test in the suite); the
# resolver tests above lock in the gate logic. Visual review of
# ``app/main.py`` covers that the captured constant is the only secure
# gate in use.
