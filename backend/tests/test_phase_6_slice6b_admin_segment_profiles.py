"""Phase 6 slice 6b — admin/segments/{seg}/profiles CRUD + import + export.

End-to-end against the sqlite test fixture: ``segments`` and
``profiles`` are real ORM models so writes commit through ORM and the
list/export queries run against the same SQL the SPA hits.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser, Profile, Segment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.segments import db as segments_db

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


def _segment(seg_id: str = "SEG-AAA", *, brand_id="brand-1", brand_name="Brand One") -> Segment:
    return Segment(
        id=seg_id,
        code=seg_id,
        brand_id=brand_id,
        brand_name=brand_name,
        name="Young Pros",
        industry_id="ind-1",
        industry="Beauty",
        status="active",
        weight=1.0,
        is_deleted=False,
        created_at=_now(),
        updated_at=_now(),
    )


def _profile(
    pid: str = "P-AAA-001",
    *,
    segment_id: str = "SEG-AAA",
    name: str = "Anna",
    status: str = "active",
) -> Profile:
    return Profile(
        id=pid,
        code=pid,
        segment_id=segment_id,
        brand_id="brand-1",
        brand_name="Brand One",
        name=name,
        demographic="30F",
        need="trust",
        weight=1.0,
        status=status,
        persona_json={"summary": "x"},
        is_deleted=False,
        created_at=_now(),
        updated_at=_now(),
    )


# ── auth ─────────────────────────────────────────────────────


class _FakeScalarResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar


class _FakeProfileSession:
    def __init__(self):
        self.executed = []
        self.added = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), dict(params or {})))
        return _FakeScalarResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_create_profile_uses_code_not_orm_id_for_integer_profile_schema(monkeypatch):
    session = _FakeProfileSession()
    monkeypatch.setattr(segments_db, "_profiles_use_integer_id", AsyncMock(return_value=True))
    monkeypatch.setattr(segments_db, "_sync_profiles_id_sequence", AsyncMock(return_value=True))
    monkeypatch.setattr(
        segments_db,
        "get_segment",
        AsyncMock(return_value={"id": "SEG-C", "brand_id": "brand-1", "brand_name": "Brand One"}),
    )
    monkeypatch.setattr(
        segments_db,
        "get_profile",
        AsyncMock(return_value={"id": "P-C-NEW", "name": "Bob"}),
    )

    row = await segments_db.create_profile(
        session,
        "SEG-C",
        {"id": "P-C-NEW", "name": "Bob", "status": "active"},
        "admin-1",
    )

    insert_sql = " ".join(sql for sql, _params in session.executed if "INSERT INTO profiles" in sql)
    assert row["id"] == "P-C-NEW"
    assert session.added == []
    assert "code, segment_id" in insert_sql
    assert "(id, code" not in insert_sql


@pytest.mark.asyncio
async def test_update_profile_uses_raw_code_match_for_integer_profile_schema(monkeypatch):
    session = _FakeProfileSession()
    existing = {"id": "P-U-001", "name": "Anna"}
    updated = {"id": "P-U-001", "name": "Renamed"}
    monkeypatch.setattr(segments_db, "_profiles_use_integer_id", AsyncMock(return_value=True))
    monkeypatch.setattr(
        segments_db,
        "get_segment",
        AsyncMock(return_value={"id": "SEG-U", "brand_id": "brand-1", "brand_name": "Brand One"}),
    )
    monkeypatch.setattr(segments_db, "get_profile", AsyncMock(side_effect=[existing, updated]))

    row = await segments_db.update_profile(
        session,
        "SEG-U",
        "P-U-001",
        {"name": "Renamed", "status": "active"},
        "admin-1",
    )

    update_sql = " ".join(sql for sql, _params in session.executed if "UPDATE profiles" in sql)
    assert row == updated
    assert session.added == []
    assert "code = :pid_upper OR CAST(id AS TEXT) = :pid_raw" in update_sql


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/segments/SEG-X/profiles")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/admin/segments/SEG-X/profiles", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_unauth_401(client):
    resp = await client.put("/api/admin/segments/SEG-X/profiles/P-1", json={"name": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/segments/SEG-X/profiles/P-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_unauth_401(client):
    resp = await client.post("/api/admin/segments/SEG-X/profiles/import", json={"rows": []})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_unauth_401(client):
    resp = await client.get("/api/admin/segments/SEG-X/profiles/export")
    assert resp.status_code == 401


# ── GET / list ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_segment_missing_404(client, admin_operator):
    resp = await client.get("/api/admin/segments/SEG-NONE/profiles")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_returns_paged_rows(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-A"))
    for i in range(3):
        db_session.add(_profile(f"P-A-{i:03d}", segment_id="SEG-A"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments/SEG-A/profiles?per_page=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 3
    assert len(body["rows"]) == 2


@pytest.mark.asyncio
async def test_list_filters_by_status(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-B"))
    db_session.add(_profile("P-B-001", segment_id="SEG-B", status="active"))
    db_session.add(_profile("P-B-002", segment_id="SEG-B", status="draft"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments/SEG-B/profiles?status=active")
    body = resp.json()
    ids = [r["id"] for r in body["rows"]]
    assert ids == ["P-B-001"]


# ── POST / create ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_segment_missing_404(client, admin_operator):
    resp = await client.post("/api/admin/segments/SEG-NONE/profiles", json={"name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_201_and_audit(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-C"))
    await db_session.commit()
    resp = await client.post(
        "/api/admin/segments/SEG-C/profiles",
        json={"id": "P-C-NEW", "name": "Bob", "status": "active"},
    )
    assert resp.status_code == 201
    assert resp.json()["profile"]["id"] == "P-C-NEW"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_profile")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_create_missing_name_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-CN"))
    await db_session.commit()
    resp = await client.post("/api/admin/segments/SEG-CN/profiles", json={"status": "active"})
    assert resp.status_code == 422
    assert "profile_name_required" in str(resp.json())


@pytest.mark.asyncio
async def test_create_invalid_status_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-CS"))
    await db_session.commit()
    resp = await client.post(
        "/api/admin/segments/SEG-CS/profiles",
        json={"name": "x", "status": "weird"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_duplicate_id_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-CD"))
    db_session.add(_profile("P-DUP", segment_id="SEG-CD"))
    await db_session.commit()
    resp = await client.post(
        "/api/admin/segments/SEG-CD/profiles",
        json={"id": "P-DUP", "name": "x", "status": "active"},
    )
    assert resp.status_code == 422


# ── PUT /{id} ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_returns_updated_and_audits(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-U"))
    db_session.add(_profile("P-U-001", segment_id="SEG-U"))
    await db_session.commit()
    resp = await client.put(
        "/api/admin/segments/SEG-U/profiles/P-U-001",
        json={"name": "Renamed", "status": "paused"},
    )
    assert resp.status_code == 200
    assert resp.json()["profile"]["name"] == "Renamed"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_profile")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_update_missing_404(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-UM"))
    await db_session.commit()
    resp = await client.put("/api/admin/segments/SEG-UM/profiles/P-NONE", json={"name": "x"})
    assert resp.status_code == 404


# ── DELETE ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_audits_high(
    client, admin_operator, db_session: AsyncSession
):
    db_session.add(_segment("SEG-D"))
    db_session.add(_profile("P-D-001", segment_id="SEG-D"))
    await db_session.commit()
    resp = await client.delete("/api/admin/segments/SEG-D/profiles/P-D-001")
    assert resp.status_code == 200
    after = (await db_session.execute(select(Profile).where(Profile.id == "P-D-001"))).scalar_one()
    assert after.is_deleted is True

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_profile")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_delete_missing_404(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-DM"))
    await db_session.commit()
    resp = await client.delete("/api/admin/segments/SEG-DM/profiles/P-NONE")
    assert resp.status_code == 404


# ── POST /import ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_segment_missing_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/segments/SEG-NONE/profiles/import",
        json={"rows": [{"name": "x"}]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_invalid_rows_422(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-II"))
    await db_session.commit()
    resp = await client.post("/api/admin/segments/SEG-II/profiles/import", json={"rows": "nope"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_added_updated_skipped_and_audit(
    client, admin_operator, db_session: AsyncSession
):
    db_session.add(_segment("SEG-IM"))
    db_session.add(_profile("P-EXIST", segment_id="SEG-IM"))
    await db_session.commit()
    resp = await client.post(
        "/api/admin/segments/SEG-IM/profiles/import",
        json={
            "rows": [
                {"id": "P-NEW", "name": "Alice", "status": "active"},
                {"id": "P-EXIST", "name": "Renamed", "status": "active"},
                {"id": "P-BAD", "status": "weird"},  # missing name + invalid status
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["updated"] == 1
    assert body["skipped"] == 1

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "import_profiles")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


# ── GET /export ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_returns_csv_with_attachment_disposition(
    client, admin_operator, db_session: AsyncSession
):
    db_session.add(_segment("SEG-E"))
    db_session.add(_profile("P-E-001", segment_id="SEG-E"))
    db_session.add(_profile("P-E-002", segment_id="SEG-E"))
    await db_session.commit()
    resp = await client.get("/api/admin/segments/SEG-E/profiles/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "SEG-E-profiles.csv" in resp.headers["content-disposition"]
    body = resp.text
    assert "id,segment_id,name" in body  # header row
    assert "P-E-001" in body
    assert "P-E-002" in body


@pytest.mark.asyncio
async def test_export_segment_missing_404(client, admin_operator):
    resp = await client.get("/api/admin/segments/SEG-NONE/profiles/export")
    assert resp.status_code == 404


# ── legacy alias ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_alias_list(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-LA"))
    db_session.add(_profile("P-LA-001", segment_id="SEG-LA"))
    await db_session.commit()
    resp = await client.get("/api/segments/SEG-LA/profiles")
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_legacy_alias_create(client, admin_operator, db_session: AsyncSession):
    db_session.add(_segment("SEG-LC"))
    await db_session.commit()
    resp = await client.post(
        "/api/segments/SEG-LC/profiles",
        json={"id": "P-LC", "name": "x", "status": "active"},
    )
    assert resp.status_code == 201


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice6b():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
