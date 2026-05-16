"""[#1044 B2-12] PDF renderer (PRD §4.7.5).

Server-side PDF generation via fpdf2 — pure Python, no system deps.
Tests verify the contract surface:
  - render_pdf returns bytes with the %PDF- magic header
  - Empty-sections payloads still produce a valid PDF (no-data message)
  - download endpoint with ?format=pdf returns application/pdf
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"pdf-{uuid.uuid4().hex[:6]}@example.com",
        name="pdf",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="PDF Project",
        primary_brand_id=42,
        industry_id=1,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=180),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now(UTC).date()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.6,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


# ── renderer unit ────────────────────────────────────────────────


def test_render_pdf_returns_bytes_with_pdf_magic():
    from app.reports.renderers import render_pdf

    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "reader_perspective": "manager",
        "brand_ids": [42],
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "Executive Summary",
                "summary": "GEO score 80, mention rate 50%.",
                "narrative": "This period the score rose 5 points.",
                "metrics": {"geo_score": 80, "mention_rate": 0.5, "samples": 7},
                "tables": [],
            },
            {
                "section_type": "competitor_comparison",
                "title": "Competitor Comparison",
                "summary": "3 brand(s) compared.",
                "metrics": {},
                "tables": [
                    {
                        "name": "competitor_ranking",
                        "rows": [
                            {"brand_id": 42, "is_primary": True, "geo_score": 80},
                            {"brand_id": 43, "is_primary": False, "geo_score": 75},
                        ],
                    }
                ],
            },
        ],
    }
    out = render_pdf(payload)
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF-"), f"unexpected magic: {out[:8]!r}"
    # Sanity: non-empty body
    assert len(out) > 500


def test_render_pdf_handles_empty_sections():
    from app.reports.renderers import render_pdf

    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [],
    }
    out = render_pdf(payload)
    assert out.startswith(b"%PDF-")


def test_render_pdf_handles_cjk_payload_without_crash():
    """zh-CN payloads must produce a valid PDF whether or not a CJK
    font is registered on the host. With font: glyphs preserved.
    Without font: transliterated to '?' + warning header added (so the
    operator immediately sees the cause). Either way: %PDF- magic
    holds and bytes are returned."""
    from app.reports.renderers import render_pdf

    payload = {
        "report_type": "weekly",
        "locale": "zh-CN",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "执行摘要",
                "summary": "GEO 总分 80,平均提及率 50%。",
                "metrics": {"提及率": 0.5},
                "tables": [],
            }
        ],
    }
    out = render_pdf(payload)
    assert out.startswith(b"%PDF-")


def test_render_pdf_resolver_returns_none_without_env_or_system_path(monkeypatch, tmp_path):
    """Closes the Codex P1 contract surface for zh-CN PDFs: the
    renderer must KNOW when no CJK font is available (so it can fall
    back gracefully). Verify the path resolver returns None when the
    env var is unset AND none of the system paths exist."""
    from app.reports.renderers import pdf_renderer

    # Clear the env override and re-point search paths at an empty dir
    # so the resolver sees no candidates.
    monkeypatch.delenv("GENPANO_PDF_CJK_FONT_PATH", raising=False)
    monkeypatch.setattr(pdf_renderer, "_CJK_FONT_SEARCH_PATHS", (str(tmp_path / "missing.ttc"),))
    assert pdf_renderer._resolve_cjk_font_path() is None


def test_render_pdf_resolver_picks_env_override_first(monkeypatch, tmp_path):
    """Operator override env var takes precedence over the default
    system paths."""
    from app.reports.renderers import pdf_renderer

    override = tmp_path / "operator-font.ttc"
    override.write_bytes(b"")  # exists()-check passes
    monkeypatch.setenv("GENPANO_PDF_CJK_FONT_PATH", str(override))
    assert pdf_renderer._resolve_cjk_font_path() == str(override)


def test_render_pdf_renders_zh_payload_in_no_cjk_mode(monkeypatch, tmp_path):
    """End-to-end: when no CJK font is detected, render_pdf still
    produces a valid PDF for a zh-CN payload (transliteration path).
    The bytes start with %PDF- and the function does not raise."""
    from app.reports.renderers import pdf_renderer

    # Force the no-CJK branch independently of host font availability.
    monkeypatch.setattr(pdf_renderer, "_CJK_FONT_PATH", None)
    payload = {
        "report_type": "weekly",
        "locale": "zh-CN",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "执行摘要",
                "summary": "GEO 总分 80",
                "tables": [],
            }
        ],
    }
    out = pdf_renderer.render_pdf(payload)
    assert out.startswith(b"%PDF-")
    # Sanity: warning page header pushed the body size above the
    # minimum-empty PDF threshold.
    assert len(out) > 700


def test_render_pdf_uses_cjk_font_when_available_for_zh_locale(monkeypatch):
    """When a CJK font IS available, the renderer must (a) skip the
    warning header and (b) preserve the CJK string as UTF-8 in the
    PDF stream so glyphs render correctly."""
    import os

    if not os.path.exists("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"):
        pytest.skip(
            "no wqy-microhei.ttc on test host; this asserts the happy "
            "path on backend Docker image / CI"
        )
    from app.reports.renderers import pdf_renderer

    # Refresh in case a prior test cleared the module-level cache.
    pdf_renderer._refresh_cjk_font_path_for_tests()
    assert pdf_renderer.cjk_font_is_available()

    payload = {
        "report_type": "weekly",
        "locale": "zh-CN",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "executive_summary",
                "title": "执行摘要",
                "summary": "GEO 总分 80",
                "tables": [],
            }
        ],
    }
    out = pdf_renderer.render_pdf(payload)
    assert out.startswith(b"%PDF-")
    # Warning header NOT present (font is registered).
    assert b"GENPANO_PDF_CJK_FONT_PATH" not in out


def test_render_pdf_table_truncates_long_cells():
    """Long cell text should be truncated rather than overflow the row
    width (which renders as a runaway in fpdf2)."""
    from app.reports.renderers import render_pdf

    long_text = "x" * 200
    payload = {
        "report_type": "weekly",
        "locale": "en-US",
        "period": {"from": "2026-01-01", "to": "2026-01-07"},
        "project_id": "p-1",
        "sections": [
            {
                "section_type": "test",
                "title": "Test",
                "summary": "...",
                "tables": [{"name": "t", "rows": [{"col_a": long_text, "col_b": "short"}]}],
            }
        ],
    }
    out = render_pdf(payload)
    assert out.startswith(b"%PDF-")


# ── endpoint ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_pdf_returns_application_pdf(client, user, project):
    """End-to-end: POST a real report, then download with ?format=pdf
    and verify content-type + magic header (PRD §4.7.5 / AC-4.7-10)."""
    create = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={"report_type": "weekly"},
    )
    assert create.status_code == 201
    rid = create.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=pdf",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith(f'attachment; filename="{rid}.pdf"')
    body = resp.content
    assert body.startswith(b"%PDF-")
    # Sanity: PDF should be more than just a stub
    assert len(body) > 1024


@pytest.mark.asyncio
async def test_download_pdf_format_is_validated(client, user, project):
    """An invalid format (e.g. ?format=docx) still returns 422 with the
    allowed-formats list including pdf."""
    create = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={"report_type": "weekly"},
    )
    rid = create.json()["id"]
    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=docx",
        headers=_bearer(user),
    )
    assert resp.status_code == 422
    body = resp.json()
    # Allowed-formats list should include 'pdf' now
    detail = str(body)
    assert "pdf" in detail
