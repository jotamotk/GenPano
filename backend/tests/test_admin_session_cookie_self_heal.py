"""Hotfix #2 — cookie self-heal on bad ADMIN_SESSION_SECRET signatures.

When the admin session secret rotates (e.g., after a redeploy or after
the env_file: .env hotfix landed in #347), every cookie issued under the
old secret becomes undecryptable. Starlette's SessionMiddleware silently
empties the session, so ``request.session.get('admin_user_id')`` returns
None and ``current_admin`` 401s.

Without help, the browser keeps sending the bad cookie forever and every
admin request keeps 401-ing. The self-heal in current_admin clears the
session when it sees ``cookie_present and admin_user_id is None``, which
makes SessionMiddleware emit ``Set-Cookie: ...; Max-Age=0`` so the
browser drops the bad cookie. The next page load is anonymous → SPA
detects 401 + flips isLoggedIn=false → user is forced to login.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_current_admin_clears_bad_cookie_on_401(client):
    """When a request arrives with a (garbage) genpano_admin_session
    cookie, current_admin returns 401 AND the response carries
    Set-Cookie: genpano_admin_session=; ... Max-Age=0.
    """
    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={"candidate_ids": ["x"], "status": "rejected"},
        cookies={"genpano_admin_session": "garbage-not-a-real-signed-payload"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "admin_session_required"

    # Set-Cookie header must clear the bad cookie. Starlette's
    # SessionMiddleware emits Max-Age=0 when scope["session"] is empty
    # and the request had a cookie.
    set_cookie_headers = resp.headers.get_list("set-cookie")
    cleared = any(
        "genpano_admin_session=" in h
        and ("Max-Age=0" in h or "max-age=0" in h or "expires=" in h.lower())
        for h in set_cookie_headers
    )
    assert cleared, f"expected Max-Age=0 / expires Set-Cookie; got: {set_cookie_headers}"


@pytest.mark.asyncio
async def test_current_admin_no_cookie_returns_401_without_set_cookie(client):
    """No genpano_admin_session at all → 401, but NO Set-Cookie header
    (nothing to clear). Sanity check that we don't spam Set-Cookie on
    every anonymous probe."""
    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={"candidate_ids": ["x"], "status": "rejected"},
    )
    assert resp.status_code == 401
    set_cookie_headers = resp.headers.get_list("set-cookie")
    cleared = any("genpano_admin_session=" in h for h in set_cookie_headers)
    assert not cleared, f"unexpected Set-Cookie on anonymous probe: {set_cookie_headers}"
