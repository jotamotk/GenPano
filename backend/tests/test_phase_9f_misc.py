"""Phase 9 slice 9f — misc tail (sms_register / task_status / html_files /
html / screenshot / backfill_citations / queries-by-day)."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.misc.lib import (
    MiscValidationError,
    classify_debug_file,
    deduplicate_citations,
    extract_citations_from_text,
    extract_hrefs,
    list_debug_files,
    parse_by_day_args,
    validate_screenshot_path,
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


def _misc_router_module():
    import app.api.misc.router  # noqa: F401

    return sys.modules["app.api.misc.router"]


def _misc_dispatch_module():
    import app.admin.misc.celery_dispatch  # noqa: F401

    return sys.modules["app.admin.misc.celery_dispatch"]


def _patch_backend_celery_fallback(monkeypatch, celery_app):
    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "geo_tracker.celery_app":
            raise ModuleNotFoundError(name)
        if name == "app.celery_app":
            return types.SimpleNamespace(celery_app=celery_app)
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)


# ── lib.py ──────────────────────────────────────────────────


def test_classify_debug_file():
    assert classify_debug_file("page.html") == "html"
    assert classify_debug_file("shot.PNG") == "image"
    assert classify_debug_file("data.json") == "json"
    assert classify_debug_file("foo.txt") == "other"


def test_extract_citations_basic():
    out = extract_citations_from_text("see https://a.com and https://b.com/x")
    assert "https://a.com" in out
    assert any(u.startswith("https://b.com/x") for u in out)


def test_extract_hrefs_strips_html():
    html = '<a href="https://a.com">a</a> <a class="x" href="https://b.com">b</a>'
    out = extract_hrefs(html)
    assert "https://a.com" in out
    assert "https://b.com" in out


def test_deduplicate_strips_trailing_punct_and_skips_blacklist():
    out = deduplicate_citations(["https://x.com/a.", "https://x.com/a", "https://chatgpt.com/page"])
    assert len(out) == 1
    assert out[0]["url"] == "https://x.com/a"


def test_validate_path_blocks_traversal(tmp_path):
    inside = tmp_path / "ok.txt"
    inside.write_text("hello")
    real, err = validate_screenshot_path(str(inside), str(tmp_path))
    assert err is None
    assert real is not None and os.path.realpath(real) == os.path.realpath(str(inside))

    # Try a path outside screenshot_dir.
    outside = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    outside.write(b"x")
    outside.close()
    try:
        real2, err2 = validate_screenshot_path(outside.name, str(tmp_path))
        assert real2 is None
        assert err2 == ("Access denied", 403)
    finally:
        os.unlink(outside.name)


def test_validate_path_missing_file(tmp_path):
    _real, err = validate_screenshot_path(str(tmp_path / "ghost.txt"), str(tmp_path))
    assert err == ("File not found", 404)


def test_validate_path_required():
    _real, err = validate_screenshot_path(None, "/tmp")
    assert err == ("Path required", 400)


def test_list_debug_files_filters_query_id(tmp_path):
    (tmp_path / "query_1_main.html").write_text("a")
    (tmp_path / "query_2_main.html").write_text("b")
    (tmp_path / "ignored.txt").write_text("x")  # wrong ext
    items, total = list_debug_files(screenshot_dir=str(tmp_path), query_id="1", page=1, per_page=10)
    assert total == 1
    assert items[0]["name"] == "query_1_main.html"


def test_list_debug_files_include_images_false(tmp_path):
    (tmp_path / "shot.png").write_bytes(b"\x89PNG")
    (tmp_path / "page.html").write_text("a")
    items_html_only, _ = list_debug_files(
        screenshot_dir=str(tmp_path), include_images=False, page=1, per_page=10
    )
    assert {i["name"] for i in items_html_only} == {"page.html"}


def test_parse_by_day_invalid_month():
    with pytest.raises(MiscValidationError) as exc:
        parse_by_day_args({"month": "2026/05"})
    assert exc.value.code == "invalid_month"


def test_parse_by_day_invalid_date():
    with pytest.raises(MiscValidationError) as exc:
        parse_by_day_args({"date": "not-a-date"})
    assert exc.value.code == "invalid_date"


def test_parse_by_day_normalized_month():
    out = parse_by_day_args({"month": "2026-05"})
    assert out["mode"] == "month"
    assert out["month"] == "2026-05"


def test_parse_by_day_default_when_empty():
    out = parse_by_day_args({})
    # mode is "month" with month=None — caller fills the default.
    assert out["mode"] == "month"
    assert out["month"] is None


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sms_register_unauth_401(client):
    resp = await client.post("/api/sms_register", json={"platform": "doubao"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_task_status_unauth_401(client):
    resp = await client.get("/api/task_status/abc")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_html_files_unauth_401(client):
    resp = await client.get("/api/html_files")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_html_unauth_401(client):
    resp = await client.get("/api/html?path=/tmp/x")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_screenshot_unauth_401(client):
    resp = await client.get("/api/screenshot?path=/tmp/x.png")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_backfill_unauth_401(client):
    resp = await client.post("/api/backfill_citations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_queries_by_day_unauth_401(client):
    resp = await client.get("/api/queries/by-day?month=2026-05")
    assert resp.status_code == 401


# ── sms_register ────────────────────────────────────────────


def test_sms_register_uses_backend_celery_app_when_geo_tracker_app_module_is_absent(
    monkeypatch,
):
    dispatch = _misc_dispatch_module()
    sent: list[tuple[str, dict[str, object], str | None]] = []

    class FakeResult:
        id = "task-fallback"

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            sent.append((name, kwargs or {}, queue))
            return FakeResult()

    _patch_backend_celery_fallback(monkeypatch, FakeCelery())

    assert dispatch.trigger_sms_register("chatgpt") == ("task-fallback", None)
    assert sent == [
        (
            "geo_tracker.tasks.celery_tasks.auto_login",
            {"platform": "chatgpt", "new_account": True},
            "account_login",
        )
    ]


@pytest.mark.parametrize("platform", ["doubao", "deepseek"])
def test_sms_register_fallback_preserves_non_chatgpt_platforms(monkeypatch, platform):
    dispatch = _misc_dispatch_module()
    sent: list[tuple[str, dict[str, object], str | None]] = []

    class FakeResult:
        id = "task-platform"

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            sent.append((name, kwargs or {}, queue))
            return FakeResult()

    _patch_backend_celery_fallback(monkeypatch, FakeCelery())

    assert dispatch.trigger_sms_register(platform) == ("task-platform", None)
    assert sent == [
        (
            "geo_tracker.tasks.celery_tasks.auto_login",
            {"platform": platform, "new_account": True},
            "account_login",
        )
    ]


def test_sms_register_send_failure_returns_stable_error(monkeypatch):
    dispatch = _misc_dispatch_module()

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            raise RuntimeError("broker password=secret exploded")

    monkeypatch.setattr(dispatch, "_load_celery_app", lambda: FakeCelery())

    assert dispatch.trigger_sms_register("chatgpt") == (None, "Celery dispatch failed")


@pytest.mark.parametrize("task_id", [None, "", "   "])
def test_sms_register_missing_result_id_returns_stable_error(monkeypatch, task_id):
    dispatch = _misc_dispatch_module()

    class FakeResult:
        id = task_id

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            return FakeResult()

    monkeypatch.setattr(dispatch, "_load_celery_app", lambda: FakeCelery())

    assert dispatch.trigger_sms_register("chatgpt") == (None, "Celery task id missing")


def test_sms_register_missing_celery_returns_stable_unavailable(monkeypatch):
    dispatch = _misc_dispatch_module()
    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "celery":
            raise ModuleNotFoundError(name)
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    assert dispatch.trigger_sms_register("chatgpt") == (None, "Celery not available")


@pytest.mark.asyncio
async def test_sms_register_celery_unavailable_503(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    a = _misc_router_module()
    monkeypatch.setattr(
        a, "trigger_sms_register", MagicMock(return_value=(None, "Celery not available"))
    )
    resp = await client.post("/api/sms_register", json={"platform": "doubao"})
    assert resp.status_code == 503
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "trigger_sms_register")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("celery_unavailable") is True


@pytest.mark.asyncio
async def test_sms_register_route_uses_backend_celery_app_fallback(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    sent: list[tuple[str, dict[str, object], str | None]] = []

    class FakeResult:
        id = "task-route-fallback"

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            sent.append((name, kwargs or {}, queue))
            return FakeResult()

    _patch_backend_celery_fallback(monkeypatch, FakeCelery())

    resp = await client.post("/api/sms_register", json={"platform": "chatgpt"})

    assert resp.status_code == 200
    assert resp.json()["task_id"] == "task-route-fallback"
    assert sent == [
        (
            "geo_tracker.tasks.celery_tasks.auto_login",
            {"platform": "chatgpt", "new_account": True},
            "account_login",
        )
    ]
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "trigger_sms_register")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("task_id") == "task-route-fallback"


@pytest.mark.asyncio
async def test_sms_register_route_send_failure_503_without_raw_error(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            raise RuntimeError("broker password=secret exploded")

    _patch_backend_celery_fallback(monkeypatch, FakeCelery())

    resp = await client.post("/api/sms_register", json={"platform": "chatgpt"})

    assert resp.status_code == 503
    assert resp.json()["error"] == "Celery dispatch failed"
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "trigger_sms_register")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("error") == "Celery dispatch failed"


@pytest.mark.asyncio
async def test_sms_register_route_missing_task_id_503_without_raw_error(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    class FakeResult:
        id = "   "

    class FakeCelery:
        def send_task(self, name, *, kwargs=None, queue=None):
            return FakeResult()

    _patch_backend_celery_fallback(monkeypatch, FakeCelery())

    resp = await client.post("/api/sms_register", json={"platform": "chatgpt"})

    assert resp.status_code == 503
    assert resp.json()["error"] == "Celery task id missing"
    assert "secret" not in str(resp.json()).lower()
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "trigger_sms_register")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("error") == "Celery task id missing"
    assert "secret" not in str(audit[0].after).lower()


@pytest.mark.asyncio
async def test_sms_register_success_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    a = _misc_router_module()
    monkeypatch.setattr(a, "trigger_sms_register", MagicMock(return_value=("task-abc", None)))
    resp = await client.post("/api/sms_register", json={"platform": "chatgpt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "task-abc"
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "trigger_sms_register")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("platform") == "chatgpt"


# ── task_status ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_status_celery_unavailable(client, admin_operator, monkeypatch):
    a = _misc_router_module()
    monkeypatch.setattr(
        a,
        "fetch_task_status",
        MagicMock(return_value={"state": "UNKNOWN", "error": "Celery not available"}),
    )
    resp = await client.get("/api/task_status/abc")
    assert resp.status_code == 200
    assert resp.json()["state"] == "UNKNOWN"


# ── html_files ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_html_files_bare_returns_array(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    (tmp_path / "query_5_main.html").write_text("a")
    resp = await client.get("/api/html_files")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(item["name"] == "query_5_main.html" for item in body)


@pytest.mark.asyncio
async def test_html_files_paginated(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    (tmp_path / "query_1.html").write_text("a")
    (tmp_path / "query_2.html").write_text("b")
    resp = await client.get("/api/html_files?page=1&per_page=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert isinstance(body["items"], list)


# ── html / screenshot ──────────────────────────────────────


@pytest.mark.asyncio
async def test_html_path_required_400(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    resp = await client.get("/api/html")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_html_returns_text(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    file_path = tmp_path / "a.html"
    file_path.write_text("<h1>hello</h1>")
    resp = await client.get(f"/api/html?path={file_path}")
    assert resp.status_code == 200
    assert "hello" in resp.text


@pytest.mark.asyncio
async def test_screenshot_unsupported_415(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    file_path = tmp_path / "a.txt"
    file_path.write_text("hello")
    resp = await client.get(f"/api/screenshot?path={file_path}")
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_screenshot_serves_png(client, admin_operator, monkeypatch, tmp_path):
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    file_path = tmp_path / "a.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    resp = await client.get(f"/api/screenshot?path={file_path}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


# ── backfill_citations ──────────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_audit_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    a = _misc_router_module()
    monkeypatch.setattr(
        a.misc_db,
        "backfill_citations_from_responses",
        AsyncMock(return_value={"scanned": 10, "updated": 4}),
    )
    resp = await client.post("/api/backfill_citations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned"] == 10
    assert body["updated"] == 4
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "backfill_citations")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("updated") == 4


# ── queries/by-day ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_by_day_invalid_month_400(client, admin_operator):
    resp = await client.get("/api/queries/by-day?month=2026/05")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_by_day_invalid_date_400(client, admin_operator):
    resp = await client.get("/api/queries/by-day?date=weird")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_by_day_month_returns_calendar(client, admin_operator, monkeypatch):
    a = _misc_router_module()
    monkeypatch.setattr(
        a.misc_db,
        "queries_by_day_month",
        AsyncMock(
            return_value=[
                {
                    "date": "2026-05-01",
                    "total": 10,
                    "done": 8,
                    "failed": 1,
                    "running": 0,
                    "pending": 1,
                    "completion_rate": 80.0,
                }
            ]
        ),
    )
    resp = await client.get("/api/queries/by-day?month=2026-05")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "month"
    assert body["days"][0]["completion_rate"] == 80.0


@pytest.mark.asyncio
async def test_by_day_date_returns_grouped(client, admin_operator, monkeypatch):
    a = _misc_router_module()
    monkeypatch.setattr(
        a.misc_db,
        "queries_by_day_date",
        AsyncMock(
            return_value={
                "groups": [
                    {
                        "engine": "doubao",
                        "profile_id": "pf_1",
                        "queries": [{"id": 1, "status": "done"}],
                        "total": 1,
                        "done": 1,
                        "failed": 0,
                        "running": 0,
                        "pending": 0,
                    }
                ],
                "totals": {"total": 1, "done": 1, "failed": 0, "running": 0, "pending": 0},
            }
        ),
    )
    resp = await client.get("/api/queries/by-day?date=2026-05-08")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "date"
    assert body["totals"]["done"] == 1
    assert len(body["groups"]) == 1


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice9f():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
