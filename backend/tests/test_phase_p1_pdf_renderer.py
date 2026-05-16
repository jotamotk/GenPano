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


def test_render_pdf_strips_non_latin1_when_no_cjk_font():
    """fpdf2's built-in Helvetica is Latin-1; the renderer should
    transliterate (not crash) when the payload contains CJK text.
    Production deployments install a CJK TTF via register_cjk_font()."""
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
    # No exception; bytes returned.
    out = render_pdf(payload)
    assert out.startswith(b"%PDF-")


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
