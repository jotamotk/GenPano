"""Hotfix: GET /api/admin/_meta/whoami diagnostic endpoint.

Lets operators report what backend sees about their session when
admin_console SPA hits a 401 — separates "cookie didn't arrive" from
"cookie arrived but admin_user_id wasn't set".
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_whoami_no_session_returns_empty(client):
    """Anonymous request — no cookie, empty session, no admin_user_id."""
    resp = await client.get("/api/admin/_meta/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cookie_present"] is False
    assert body["session_keys"] == []
    assert body["admin_user_id"] is None


@pytest.mark.asyncio
async def test_whoami_reports_cookie_present_when_set(client):
    """Send a (garbage) genpano_admin_session cookie — middleware will
    silently drop the bad signature, but our endpoint still reports the
    raw cookie was received. Confirms the endpoint can distinguish
    "cookie absent" from "cookie present but unsigned/stale"."""
    resp = await client.get(
        "/api/admin/_meta/whoami",
        cookies={"genpano_admin_session": "not-a-real-signed-payload"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cookie_present"] is True
    # Bad cookie → middleware drops it → empty session
    assert body["session_keys"] == []
    assert body["admin_user_id"] is None


@pytest.mark.asyncio
async def test_whoami_reports_forwarded_proto(client):
    """nginx terminating HTTPS sets X-Forwarded-Proto=https; backend
    cookie Secure flag depends on the browser seeing HTTPS, not on the
    backend's view, but this header is the diagnostic users want when
    chasing Secure-cookie drops."""
    resp = await client.get(
        "/api/admin/_meta/whoami",
        headers={"x-forwarded-proto": "https"},
    )
    assert resp.status_code == 200
    assert resp.json()["forwarded_proto"] == "https"
