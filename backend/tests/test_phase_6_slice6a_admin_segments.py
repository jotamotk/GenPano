"""Phase 6 slice 6a — admin/segments CRUD (5 routes).

End-to-end against the sqlite test fixture: ``segments`` and
``profiles`` are real ORM models in Base.metadata so the writes go
through ORM and the read-side aggregations exercise the same SQL the
SPA hits in production.

Coverage:
- 401 unauth on every method
- GET / paged + summary fields
- POST / 201 + audit row + segment_name_required 422
- GET /{id} 200 + 404
- PUT /{id} 200 + audit + invalid_segment_status 422 + 404
- DELETE /{id} cascade-soft-deletes profiles + audit (high)
- legacy alias /api/segments/* reaches the same handlers
- audit gate (source-scan) keeps passing
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser, Profile, Segment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _segment(seg_id: str = "SEG-AAA", *, status: str = "active", weight: float = 5.0) -> Segment:
    return Segment(
        id=seg_id,
        code=seg_id,
        brand_id="brand-1",
        brand_name="Brand One",
        name="Young Pros",
        industry_id="ind-1",
        industry="Beauty",
        status=status,
        weight=weight,
        is_deleted=False,
        created_at=_now(),
        updated_at=_now(),
    )


# ── auth ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/segments")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/admin/segments", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_unauth_401(client):
    resp = await client.get("/api/admin/segments/SEG-X")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_unauth_401(client):
    resp = await client.put("/api/admin/segments/SEG-X", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/segments/SEG-X")
    assert resp.status_code == 401


# ── GET / list ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_paged_rows_and_summary(
    client, admin_operator, db_session: AsyncSession
):
    for i in range(3):
        db_session.add(_segment(f"SEG-{i:03d}", status="active" if i else "draft"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments?per_page=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["rows"]) == 2
    pag = body["pagination"]
    assert pag["page"] == 1 and pag["per_page"] == 2 and pag["total"] == 3
    summary = body["summary"]
    assert summary["segment_count"] == 3
    assert summary["active_segment_count"] == 2


@pytest.mark.asyncio
async def test_list_filters_by_status(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-A", status="active"))
    db_session.add(_segment("SEG-B", status="draft"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments?status=active")
    body = resp.json()
    ids = [r["id"] for r in body["rows"]]
    assert ids == ["SEG-A"]


# ── POST / create ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_returns_201_and_audit(client, admin_operator, db_session: AsyncSession):
    resp = await client.post(
        "/api/admin/segments",
        json={"id": "seg-new", "name": "Brand new", "status": "active", "weight": 3},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["segment"]["id"] == "SEG-NEW"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_segment")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_create_missing_name_422(client, admin_operator):
    resp = await client.post("/api/admin/segments", json={"status": "active"})
    assert resp.status_code == 422
    assert "segment_name_required" in str(resp.json())


@pytest.mark.asyncio
async def test_create_invalid_status_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/segments",
        json={"name": "Brand new", "status": "weird"},
    )
    assert resp.status_code == 422
    assert "invalid_segment_status" in str(resp.json())


@pytest.mark.asyncio
async def test_create_duplicate_id_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-DUP"))
    await db_session.commit()
    resp = await client.post(
        "/api/admin/segments",
        json={"id": "SEG-DUP", "name": "x", "status": "active"},
    )
    assert resp.status_code == 422
    assert "segment_id_exists" in str(resp.json())


# ── GET /{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_existing_returns_segment(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-X"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments/SEG-X")
    assert resp.status_code == 200
    assert resp.json()["segment"]["id"] == "SEG-X"


@pytest.mark.asyncio
async def test_get_lowercase_path_normalized(client, admin_operator, db_session: AsyncSession):
    """admin_console upper-cases the segment id internally — make sure
    requests with mixed/lower case still resolve."""
    db_session.add(_segment("SEG-Y"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments/seg-y")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_missing_returns_404(client, admin_operator):
    resp = await client.get("/api/admin/segments/SEG-MISSING")
    assert resp.status_code == 404


# ── PUT /{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_changes_fields_and_audits(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-U"))
    await db_session.commit()
    resp = await client.put(
        "/api/admin/segments/SEG-U",
        json={"name": "Renamed", "status": "paused", "weight": 7},
    )
    assert resp.status_code == 200
    assert resp.json()["segment"]["name"] == "Renamed"
    assert resp.json()["segment"]["status"] == "paused"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_segment")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_update_missing_returns_404(client, admin_operator):
    resp = await client.put("/api/admin/segments/SEG-NONE", json={"name": "y"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_invalid_status_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-V"))
    await db_session.commit()
    resp = await client.put(
        "/api/admin/segments/SEG-V",
        json={"name": "x", "status": "weird"},
    )
    assert resp.status_code == 422


# ── DELETE /{id} ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_cascades_to_profiles_and_audits_high(
    client, admin_operator, db_session: AsyncSession
):
    db_session.add(_segment("SEG-D"))
    db_session.add(
        Profile(
            id="P-D-1",
            segment_id="SEG-D",
            code="P-D-1",
            brand_id="brand-1",
            brand_name="Brand One",
            name="alpha",
            demographic="30F",
            need="trust",
            weight=1.0,
            status="active",
            is_deleted=False,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    await db_session.commit()

    resp = await client.delete("/api/admin/segments/SEG-D")
    assert resp.status_code == 200
    assert resp.json()["segment"]["id"] == "SEG-D"

    after_seg = (
        await db_session.execute(select(Segment).where(Segment.id == "SEG-D"))
    ).scalar_one()
    assert after_seg.is_deleted is True
    assert after_seg.status == "deleted"

    after_prof = (
        await db_session.execute(select(Profile).where(Profile.id == "P-D-1"))
    ).scalar_one()
    assert after_prof.is_deleted is True
    assert after_prof.status == "deleted"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_segment")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_delete_missing_returns_404(client, admin_operator):
    resp = await client.delete("/api/admin/segments/SEG-NONE")
    assert resp.status_code == 404


# ── legacy alias ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_alias_list(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-L"))
    await db_session.commit()
    resp = await client.get("/api/segments")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["rows"]]
    assert "SEG-L" in ids


@pytest.mark.asyncio
async def test_legacy_alias_create(client, admin_operator):
    resp = await client.post(
        "/api/segments",
        json={"id": "SEG-LEG", "name": "x", "status": "active"},
    )
    assert resp.status_code == 201


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice6a():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
