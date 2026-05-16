"""Phase RP.5 — markdown / json / csv report renderers + download endpoint."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta

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
        email=f"rp5-{uuid.uuid4().hex[:6]}@example.com",
        name="RP5 User",
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
    p = Project(user_id=user.id, name="RP5 P", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i,
                mention_rate=0.5,
                avg_sov=0.3,
                avg_sentiment=0.6,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


# ── markdown renderer (unit) ──────────────────────────────────


def test_render_markdown_empty_payload():
    from app.reports.renderers import render_markdown

    md = render_markdown(
        {
            "report_type": "weekly",
            "locale": "en-US",
            "period": {"from": "2026-01-01", "to": "2026-01-07"},
            "project_id": "p-1",
            "sections": [],
        }
    )
    assert "# Report: WEEKLY" in md
    assert "p-1" in md
    assert "No data this period." in md


def test_render_markdown_with_sections():
    from app.reports.renderers import render_markdown

    md = render_markdown(
        {
            "report_type": "weekly",
            "locale": "en-US",
            "period": {"from": "2026-01-01", "to": "2026-01-07"},
            "project_id": "p-1",
            "sections": [
                {
                    "section_type": "executive_summary",
                    "title": "Executive Summary",
                    "summary": "Top-line view.",
                    "metrics": {"geo_score": 82, "mention_rate": 0.42},
                    "tables": [],
                },
                {
                    "section_type": "pano_score",
                    "title": "PANO Score",
                    "summary": "Per-brand breakdown",
                    "tables": [
                        {
                            "name": "pano_by_brand",
                            "rows": [
                                {"brand_id": 42, "geo_score": 82, "sov": 0.4},
                                {"brand_id": 99, "geo_score": 71, "sov": 0.25},
                            ],
                        }
                    ],
                },
            ],
        }
    )
    assert "## Executive Summary" in md
    assert "## PANO Score" in md
    assert "**Metrics**" in md
    assert "`geo_score`: 82" in md
    assert "| brand_id | geo_score | sov |" in md
    assert "| 42 | 82 | 0.4 |" in md


def test_render_markdown_zh_locale():
    from app.reports.renderers import render_markdown

    md = render_markdown(
        {
            "report_type": "weekly",
            "locale": "zh-CN",
            "period": {"from": "2026-01-01", "to": "2026-01-07"},
            "project_id": "p-1",
            "sections": [],
        }
    )
    assert "时间范围" in md
    assert "本期无数据" in md


# ── json renderer ───────────────────────────────────────────


def test_render_json_pretty():
    from app.reports.renderers import render_json

    payload = {"report_type": "weekly", "sections": []}
    out = render_json(payload, pretty=True)
    # Pretty indent is present
    assert "\n  " in out
    parsed = json.loads(out)
    assert parsed == payload


def test_render_json_compact():
    from app.reports.renderers import render_json

    payload = {"a": 1, "b": [1, 2, 3]}
    out = render_json(payload, pretty=False)
    assert out == '{"a":1,"b":[1,2,3]}'


def test_render_json_handles_unicode():
    from app.reports.renderers import render_json

    out = render_json({"title": "执行摘要"}, pretty=False)
    assert "执行摘要" in out


# ── csv renderer ────────────────────────────────────────────


def test_render_csv_skips_sections_without_tables():
    from app.reports.renderers import render_csv

    out = render_csv(
        {
            "sections": [
                {"section_type": "exec", "title": "Exec", "tables": []},
                {
                    "section_type": "pano",
                    "title": "PANO",
                    "tables": [
                        {
                            "name": "pano_by_brand",
                            "rows": [{"brand_id": 1, "geo_score": 80}],
                        }
                    ],
                },
            ]
        }
    )
    # Empty section header is suppressed
    assert "# Exec" not in out
    assert "# PANO" in out
    assert "## pano_by_brand" in out
    assert "brand_id,geo_score" in out
    assert "1,80" in out


def test_render_csv_empty_payload():
    from app.reports.renderers import render_csv

    assert render_csv({"sections": []}) == ""


# ── download endpoint integration ──────────────────────────


@pytest.mark.asyncio
async def test_download_markdown(client, user, project):
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly", "locale": "en-US"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=markdown",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert f'filename="{rid}.md"' in resp.headers["content-disposition"]
    body = resp.text
    assert "# Report: WEEKLY" in body
    assert project.id in body


@pytest.mark.asyncio
async def test_download_json(client, user, project):
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=json",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    parsed = json.loads(resp.text)
    assert parsed["report_type"] == "weekly"
    assert parsed["project_id"] == project.id


@pytest.mark.asyncio
async def test_download_csv(client, user, project):
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=csv",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert f'filename="{rid}.csv"' in resp.headers["content-disposition"]
    # Has section header line at minimum
    assert "#" in resp.text


@pytest.mark.asyncio
async def test_download_md_alias(client, user, project):
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=md",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")


@pytest.mark.asyncio
async def test_download_invalid_format_422(client, user, project):
    """PDF is now supported (#1044 B2-12) — use a truly invalid format
    here to exercise the validation gate."""
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=docx",
        headers=_bearer(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_download_unknown_report_404(client, user, project):
    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/no-such-id/download?format=json",
        headers=_bearer(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_cross_tenant_404(client, user, project, db_session):
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    other = User(
        id=_new_id(),
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}/download?format=json",
        headers=_bearer(other),
    )
    assert resp.status_code == 404
