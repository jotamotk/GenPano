"""Phase 5 hardening — rate limit + CORS + multi-tenant audit."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from genpano_models import Project, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import reset_for_tests
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "u" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


# ── rate limit middleware ───────────────────────────────────────


@pytest_asyncio.fixture
async def live_client(env, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """Re-enable rate limiting for the rate-limit-specific tests."""
    monkeypatch.delenv("GENPANO_RATE_LIMIT_DISABLED", raising=False)
    reset_for_tests()
    yield env.client
    reset_for_tests()


@pytest.mark.asyncio
async def test_anon_rate_limit_kicks_in(live_client: AsyncClient) -> None:
    """30 anon requests/min/IP allowed; the 31st returns 429."""
    # Hit a /api/v1 endpoint without auth — should 401, but counts toward
    # the anonymous bucket.
    last_status = None
    for _ in range(40):
        resp = await live_client.get("/api/v1/projects")
        last_status = resp.status_code
        if last_status == 429:
            assert resp.json()["detail"]["code"] == "rate_limited"
            assert "retry_after_seconds" in resp.json()["detail"]
            assert "Retry-After" in resp.headers
            return
    pytest.fail(f"rate limit never tripped — last status {last_status}")


@pytest.mark.asyncio
async def test_health_endpoint_not_rate_limited(live_client: AsyncClient) -> None:
    """/health should be open even under heavy load (probe traffic)."""
    for _ in range(80):
        resp = await live_client.get("/healthz")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_authed_rate_limit_higher_capacity(
    live_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Authenticated users get 60/min, 2x anon. First 30 must all pass."""
    user = User(
        id=_new_id(),
        email=f"rl-{uuid.uuid4().hex[:6]}@example.com",
        name="RL",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(user)
    await db_session.commit()
    headers = _bearer(user)

    for i in range(30):
        resp = await live_client.get("/api/v1/projects", headers=headers)
        assert resp.status_code != 429, f"unexpected 429 at iter {i}"


# ── CORS preflight ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cors_preflight_allows_known_origin() -> None:
    """OPTIONS request from configured origin returns Access-Control-* headers."""
    from app.main import app

    # Use the default dev origins
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
    # FastAPI's CORSMiddleware returns 200 for preflight from allowed origin
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_cors_preflight_blocks_unknown_origin() -> None:
    """Origin not in allowlist gets no Access-Control-Allow-Origin."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    # CORSMiddleware sends 400 OR omits the allow-origin header for unknown
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"


# ── multi-tenant audit ──────────────────────────────────────────


@pytest_asyncio.fixture
async def two_users_two_projects(
    db_session: AsyncSession,
) -> tuple[User, User, Project, Project]:
    """Pair of users each owning a project — for cross-tenant tests."""
    u_a = User(
        id=_new_id(),
        email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        name="A",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    u_b = User(
        id=_new_id(),
        email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        name="B",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add_all([u_a, u_b])
    await db_session.commit()

    p_a = Project(user_id=u_a.id, name="A's Project", primary_brand_id=10)
    p_b = Project(user_id=u_b.id, name="B's Project", primary_brand_id=20)
    db_session.add_all([p_a, p_b])
    await db_session.commit()
    await db_session.refresh(p_a, ["competitors"])
    await db_session.refresh(p_b, ["competitors"])
    return u_a, u_b, p_a, p_b


@pytest.mark.parametrize(
    "method,path_template",
    [
        ("GET", "/api/v1/projects/{pid}"),
        ("GET", "/api/v1/projects/{pid}/overview"),
        ("GET", "/api/v1/projects/{pid}/metrics"),
        ("GET", "/api/v1/projects/{pid}/diagnostics"),
        ("GET", "/api/v1/projects/{pid}/citations"),
        ("GET", "/api/v1/projects/{pid}/products"),
        ("GET", "/api/v1/projects/{pid}/topics"),
        ("GET", "/api/v1/projects/{pid}/sentiment"),
        ("GET", "/api/v1/projects/{pid}/reports"),
        ("PATCH", "/api/v1/projects/{pid}"),
        ("DELETE", "/api/v1/projects/{pid}"),
    ],
)
@pytest.mark.asyncio
async def test_cross_tenant_returns_404(
    client: AsyncClient,
    two_users_two_projects: tuple[User, User, Project, Project],
    method: str,
    path_template: str,
) -> None:
    """User A querying B's project_id MUST return 404 (deny existence info, ADR-005).

    Spans 11 endpoints — covers Phase 1 / 2 / RP / D read + write surface.
    """
    u_a, _u_b, _p_a, p_b = two_users_two_projects
    headers = _bearer(u_a)
    path = path_template.format(pid=p_b.id)
    if method == "GET":
        resp = await client.get(path, headers=headers, follow_redirects=True)
    elif method == "PATCH":
        resp = await client.patch(
            path, headers=headers, json={"name": "hijack"}, follow_redirects=True
        )
    elif method == "DELETE":
        resp = await client.delete(path, headers=headers, follow_redirects=True)
    else:
        pytest.fail(f"unsupported method {method}")
    assert resp.status_code == 404, (
        f"{method} {path} returned {resp.status_code}, expected 404 — "
        "multi-tenant deny contract violated"
    )


@pytest.mark.asyncio
async def test_cross_tenant_report_create_404(
    client: AsyncClient,
    two_users_two_projects: tuple[User, User, Project, Project],
) -> None:
    u_a, _u_b, _p_a, p_b = two_users_two_projects
    resp = await client.post(
        f"/api/v1/projects/{p_b.id}/reports",
        headers=_bearer(u_a),
        json={"report_type": "weekly"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_unknown_project_id_404(
    client: AsyncClient, two_users_two_projects: tuple[User, User, Project, Project]
) -> None:
    """Random UUID must also yield 404 (not 422 — schema validates UUIDs)."""
    u_a, *_ = two_users_two_projects
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/api/v1/projects/{fake_id}", headers=_bearer(u_a))
    assert resp.status_code == 404
