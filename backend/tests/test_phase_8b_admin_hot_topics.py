"""Phase 8 slice 8b — admin/hot-topics (CRUD + archive + batch + collect).

Pure-python validators tested directly. DB helpers + the in-process
hotspot_collectors / celery dispatch are mocked since neither has a
sqlite-friendly path. Audit-gate self-check at the end.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.hot_topics.lib import (
    HOT_TOPIC_BATCH_ACTIONS,
    HOT_TOPIC_BROWSER_SOURCES,
    HOT_TOPIC_STATUSES,
    HotTopicValidationError,
    hot_topic_row_to_dict,
    parse_batch_payload,
    parse_collect_payload,
    parse_create_payload,
    parse_update_payload,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


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


def _hot_topics_router_module():
    import app.api.admin.hot_topics.router  # noqa: F401

    return sys.modules["app.api.admin.hot_topics.router"]


def _hot_topic_row(hot_id: int = 1) -> dict:
    return {
        "id": hot_id,
        "title": "Test Topic",
        "summary": "",
        "category": "",
        "source": "manual",
        "source_url": "",
        "raw_rank": None,
        "raw_metric": "",
        "industry": "",
        "brand_id": None,
        "brand_name": None,
        "effective_from": "2026-05-07T10:00:00",
        "effective_until": "2026-05-21T10:00:00",
        "status": "active",
        "days_remaining": 14,
        "created_at": "2026-05-07T10:00:00",
        "updated_at": "2026-05-07T10:00:00",
    }


def _patch_db(
    monkeypatch,
    *,
    list_returns: tuple[list[dict], dict[str, int]] = ([], {}),
    detail: dict | None = None,
    create_returns: dict | None = None,
    update_returns: dict | None = None,
    delete_returns: tuple[bool, int] = (True, 0),
    archive_returns: int = 0,
    batch_returns: dict | None = None,
):
    a = _hot_topics_router_module()
    monkeypatch.setattr(a.hot_topics_db, "list_hot_topics", AsyncMock(return_value=list_returns))
    monkeypatch.setattr(a.hot_topics_db, "get_hot_topic", AsyncMock(return_value=detail))
    monkeypatch.setattr(
        a.hot_topics_db,
        "create_hot_topic",
        AsyncMock(return_value=create_returns or _hot_topic_row(1)),
    )
    monkeypatch.setattr(
        a.hot_topics_db,
        "update_hot_topic",
        AsyncMock(return_value=update_returns or _hot_topic_row(1)),
    )
    monkeypatch.setattr(a.hot_topics_db, "delete_hot_topic", AsyncMock(return_value=delete_returns))
    monkeypatch.setattr(a.hot_topics_db, "archive_expired", AsyncMock(return_value=archive_returns))
    monkeypatch.setattr(
        a.hot_topics_db,
        "batch_update_hot_topics",
        AsyncMock(return_value=batch_returns if batch_returns is not None else {"updated": 0}),
    )


# ── lib.py: pure validators ──────────────────────────────────


def test_hot_topic_statuses_constant():
    assert HOT_TOPIC_STATUSES == ("draft", "active", "expired", "rejected")


def test_hot_topic_batch_actions_constant():
    assert HOT_TOPIC_BATCH_ACTIONS == ("status", "industry", "brand", "delete")


def test_hot_topic_browser_sources():
    assert HOT_TOPIC_BROWSER_SOURCES == frozenset({"douyin", "xhs"})


def test_parse_create_minimal():
    out = parse_create_payload({"title": "t"})
    assert out["title"] == "t"
    assert out["status"] == "active"
    assert out["effective_days"] == 14
    assert out["source"] == "manual"


def test_parse_create_no_title():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_create_payload({})
    assert exc.value.code == "title_required"


def test_parse_create_clamps_effective_days():
    # admin_console parity: ``0 or 14`` → falls back to 14 days default,
    # huge values clamp to 90.
    assert parse_create_payload({"title": "t", "effective_days": 0})["effective_days"] == 14
    assert parse_create_payload({"title": "t", "effective_days": 9999})["effective_days"] == 90


def test_parse_create_invalid_brand_id():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_create_payload({"title": "t", "brand_id": "weird"})
    assert exc.value.code == "invalid_brand_id"


def test_parse_create_status_falls_back_when_not_in_create_set():
    out = parse_create_payload({"title": "t", "status": "expired"})
    assert out["status"] == "active"


def test_parse_create_collected_source_default_status_draft():
    """A non-manual source defaults the create status to draft."""
    out = parse_create_payload({"title": "t", "source": "baidu"})
    assert out["status"] == "draft"


def test_parse_update_invalid_status():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_update_payload({"status": "weird"})
    assert exc.value.code == "invalid_status"


def test_parse_update_invalid_effective_days():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_update_payload({"effective_days": 999})
    assert exc.value.code == "invalid_effective_days"


def test_parse_update_normalizes_text_fields():
    out = parse_update_payload({"summary": "  hi  ", "category": "  "})
    assert out["summary"] == "hi"
    assert out["category"] is None


def test_parse_batch_no_ids():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_batch_payload({"action": "status", "ids": []})
    assert exc.value.code == "ids_required"


def test_parse_batch_invalid_action():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_batch_payload({"action": "weird", "ids": [1]})
    assert exc.value.code == "invalid_action"


def test_parse_batch_status_must_be_valid():
    with pytest.raises(HotTopicValidationError) as exc:
        parse_batch_payload({"action": "status", "ids": [1], "status": "weird"})
    assert exc.value.code == "invalid_status"


def test_parse_batch_clamps_to_500_ids():
    big = list(range(1, 700))
    out = parse_batch_payload({"action": "delete", "ids": big})
    assert len(out["ids"]) == 500


def test_parse_collect_alias_and_dedupe():
    out = parse_collect_payload({"sources": ["xiaohongshu", "Xhs", "baidu", "baidu"]})
    assert out["sources"] == ["xhs", "baidu"]
    assert out["browser_sources"] == ["xhs"]
    assert out["local_sources"] == ["baidu"]


def test_parse_collect_csv_string():
    out = parse_collect_payload({"sources": "baidu,zhihu,llm_search"})
    assert out["local_sources"] == ["baidu", "zhihu", "llm_search"]
    assert out["browser_sources"] == []


def test_parse_collect_default_sources_when_missing():
    out = parse_collect_payload({})
    assert "baidu" in out["local_sources"]
    assert "zhihu" in out["local_sources"]
    assert "llm_search" in out["local_sources"]


def test_hot_topic_row_to_dict_handles_none():
    assert hot_topic_row_to_dict(None) is None


def test_hot_topic_row_to_dict_default_status():
    out = hot_topic_row_to_dict({"id": 1, "title": "t"})
    assert out is not None
    assert out["status"] == "active"
    assert out["source"] == "manual"
    assert out["summary"] == ""


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/hot-topics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_unauth_401(client):
    resp = await client.post("/api/admin/hot-topics", json={"title": "t"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_unauth_401(client):
    resp = await client.put("/api/admin/hot-topics/1", json={"status": "active"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/hot-topics/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_archive_unauth_401(client):
    resp = await client.post("/api/admin/hot-topics/archive-expired")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_batch_unauth_401(client):
    resp = await client.post("/api/admin/hot-topics/batch", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_collect_unauth_401(client):
    resp = await client.post("/api/admin/hot-topics/collect", json={})
    assert resp.status_code == 401


# ── GET /hot-topics ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pagination_and_counts(client, admin_operator, monkeypatch):
    rows = [_hot_topic_row(1), _hot_topic_row(2)]
    counts = {"draft": 1, "active": 4, "expired": 0, "rejected": 0}
    _patch_db(monkeypatch, list_returns=(rows, counts))
    resp = await client.get(
        "/api/admin/hot-topics?status=active&source=manual&industry=美妆&brand_id=1&limit=20"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hot_topics"]) == 2
    assert body["counts"]["active"] == 4
    assert body["counts"]["total"] == 5


# ── POST /hot-topics ────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/admin/hot-topics", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "title_required"


@pytest.mark.asyncio
async def test_create_returns_503_when_table_missing(client, admin_operator, monkeypatch):
    a = _hot_topics_router_module()
    monkeypatch.setattr(a.hot_topics_db, "create_hot_topic", AsyncMock(return_value=None))
    monkeypatch.setattr(a.hot_topics_db, "get_hot_topic", AsyncMock(return_value=None))
    monkeypatch.setattr(a.hot_topics_db, "list_hot_topics", AsyncMock(return_value=([], {})))
    monkeypatch.setattr(a.hot_topics_db, "update_hot_topic", AsyncMock(return_value=None))
    monkeypatch.setattr(a.hot_topics_db, "delete_hot_topic", AsyncMock(return_value=(False, 0)))
    monkeypatch.setattr(a.hot_topics_db, "archive_expired", AsyncMock(return_value=0))
    monkeypatch.setattr(
        a.hot_topics_db, "batch_update_hot_topics", AsyncMock(return_value={"updated": 0})
    )
    resp = await client.post("/api/admin/hot-topics", json={"title": "t"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "hot_topics_unavailable"


@pytest.mark.asyncio
async def test_create_audit_med_severity(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, create_returns=_hot_topic_row(99))
    resp = await client.post(
        "/api/admin/hot-topics",
        json={"title": "Hot", "industry": "美妆", "effective_days": 7},
    )
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_hot_topic")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"
    assert audit[0].after.get("effective_days") == 7


# ── PUT /hot-topics/{id} ────────────────────────────────────


@pytest.mark.asyncio
async def test_update_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.put("/api/admin/hot-topics/1", json={"status": "active"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_no_fields_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=_hot_topic_row(1))
    resp = await client.put("/api/admin/hot-topics/1", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_fields"


@pytest.mark.asyncio
async def test_update_audit_high_on_reject(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    before = {**_hot_topic_row(1), "status": "active"}
    after = {**_hot_topic_row(1), "status": "rejected"}
    _patch_db(monkeypatch, detail=before, update_returns=after)
    resp = await client.put("/api/admin/hot-topics/1", json={"status": "rejected"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_hot_topic")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_update_audit_med_for_field_edit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    before = _hot_topic_row(1)
    after = {**_hot_topic_row(1), "summary": "newsy"}
    _patch_db(monkeypatch, detail=before, update_returns=after)
    resp = await client.put("/api/admin/hot-topics/1", json={"summary": "newsy"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_hot_topic")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


# ── DELETE /hot-topics/{id} ─────────────────────────────────


@pytest.mark.asyncio
async def test_delete_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail=None)
    resp = await client.delete("/api/admin/hot-topics/1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_audit_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, detail=_hot_topic_row(7), delete_returns=(True, 4))
    resp = await client.delete("/api/admin/hot-topics/7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unlinked_prompts"] == 4
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_hot_topic")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"


# ── archive-expired ────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_expired_returns_count(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, archive_returns=12)
    resp = await client.post("/api/admin/hot-topics/archive-expired")
    assert resp.status_code == 200
    assert resp.json()["archived"] == 12
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "archive_expired_hot_topics")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("archived") == 12


# ── POST /hot-topics/batch ─────────────────────────────────


@pytest.mark.asyncio
async def test_batch_invalid_action_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/admin/hot-topics/batch", json={"action": "weird", "ids": [1]})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_action"


@pytest.mark.asyncio
async def test_batch_status_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(monkeypatch, batch_returns={"updated": 3})
    resp = await client.post(
        "/api/admin/hot-topics/batch",
        json={"action": "status", "ids": [1, 2, 3], "status": "rejected"},
    )
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "batch_hot_topics_status")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("ids_count") == 3


@pytest.mark.asyncio
async def test_batch_delete_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_db(
        monkeypatch,
        batch_returns={"deleted": 3, "unlinked_prompts": 5},
    )
    resp = await client.post(
        "/api/admin/hot-topics/batch", json={"action": "delete", "ids": [1, 2, 3]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == 3
    assert body["unlinked_prompts"] == 5
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "batch_hot_topics_delete")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"


# ── POST /hot-topics/collect ───────────────────────────────


@pytest.mark.asyncio
async def test_collect_returns_503_when_collectors_missing(client, admin_operator, monkeypatch):
    """In-process collectors live in admin_console.hotspot_collectors;
    sqlite test environment doesn't import that module → 503 with stable
    code so the SPA can show a clean error."""
    _patch_db(monkeypatch)
    a = _hot_topics_router_module()
    monkeypatch.setattr(a, "fetch_brand_context", AsyncMock(return_value=None))
    resp = await client.post("/api/admin/hot-topics/collect", json={"sources": ["baidu"]})
    # Backend's tests run without admin_console on the path → 503.
    assert resp.status_code == 503
    assert resp.json()["error"] == "collectors_unavailable"


@pytest.mark.asyncio
async def test_collect_brand_not_found_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    a = _hot_topics_router_module()
    monkeypatch.setattr(a, "fetch_brand_context", AsyncMock(return_value=None))
    resp = await client.post(
        "/api/admin/hot-topics/collect",
        json={"sources": ["baidu"], "brand_id": 9999},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "brand_not_found"


@pytest.mark.asyncio
async def test_collect_browser_only_no_celery_records_errors(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    """When ONLY browser sources are requested and celery isn't on the
    path, return 200 with errors-by-source rather than 503 (the local
    collector code path is bypassed entirely, mirroring admin_console)."""
    _patch_db(monkeypatch)
    a = _hot_topics_router_module()
    monkeypatch.setattr(a, "fetch_brand_context", AsyncMock(return_value=None))
    resp = await client.post("/api/admin/hot-topics/collect", json={"sources": ["xhs"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("queued_sources") == []
    assert "xhs" in (body.get("errors") or {})
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "collect_hot_topics")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice8b():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
