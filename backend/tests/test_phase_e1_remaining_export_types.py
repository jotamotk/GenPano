"""Phase E.1 — remaining 4 export types.

Covers citation_list / topic_coverage / products_list / report_data.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    IndustryTopicDaily,
    ProductScoreDaily,
    Project,
    ReportJob,
    User,
)
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
        email=f"e1b-{uuid.uuid4().hex[:6]}@example.com",
        name="E1B",
        role="paid",
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
        name="E1B Project",
        primary_brand_id=900,
        industry_id=42,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ── citation_list ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_citation_list_csv(db_session, client, user, project):
    mention = BrandMention(
        response_id=4001,
        brand_id=900,
        brand_name="Acme",
    )
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)
    db_session.add_all(
        [
            CitationSource(
                response_id=4001,
                mention_id=mention.id,
                url="https://example.com/article-1",
                domain="example.com",
                title="Acme Reviews",
                source_type="review",
            ),
            CitationSource(
                response_id=4001,
                mention_id=mention.id,
                url="https://blog.example.com/post-2",
                domain="blog.example.com",
                title="KOL post",
                source_type="kol_blog",
            ),
        ]
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "citation_list"},
    )
    assert create.status_code == 202
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    assert dl.status_code == 200
    body = dl.text
    lines = body.strip().split("\n")
    assert lines[0].startswith("created_at,response_id,url,domain,title,source_type,brand_name")
    assert len(lines) == 3
    assert "example.com" in body


# ── topic_coverage ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_topic_coverage_csv(db_session, client, user, project):
    today = datetime.now(UTC).replace(tzinfo=None).date()
    db_session.add_all(
        [
            IndustryTopicDaily(
                industry_id=42,
                category="skincare",
                topic_id=11,
                date=datetime.combine(today, datetime.min.time()),
                mention_count=120,
                unique_brand_count=8,
                hot_score=0.75,
            ),
            IndustryTopicDaily(
                industry_id=42,
                category="haircare",
                topic_id=22,
                date=datetime.combine(today - timedelta(days=1), datetime.min.time()),
                mention_count=90,
                unique_brand_count=5,
                hot_score=0.6,
            ),
        ]
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "topic_coverage"},
    )
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    assert dl.status_code == 200
    lines = dl.text.strip().split("\n")
    assert lines[0].startswith("date,category,topic_id,mention_count,unique_brand_count,hot_score")
    assert len(lines) == 3
    # Most recent row first; topic_id=11 was today
    assert "11" in lines[1]


# ── products_list ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_products_list_csv(db_session, client, user, project):
    today = datetime.now(UTC).replace(tzinfo=None).date()
    db_session.add_all(
        [
            ProductScoreDaily(
                brand_id=900,
                product_name="Glow Serum",
                category="skincare",
                date=datetime.combine(today, datetime.min.time()),
                target_llm="chatgpt",
                total_queries=100,
                mention_count=42,
                mention_rate=0.42,
                first_place_count=5,
                avg_position_rank=2.3,
            ),
            ProductScoreDaily(
                brand_id=900,
                product_name="Lite Serum",
                category="skincare",
                date=datetime.combine(today - timedelta(days=2), datetime.min.time()),
                target_llm="doubao",
                total_queries=80,
                mention_count=15,
                mention_rate=0.1875,
                first_place_count=1,
                avg_position_rank=4.1,
            ),
        ]
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "products_list"},
    )
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    lines = dl.text.strip().split("\n")
    assert lines[0].startswith(
        "date,product_name,category,target_llm,mention_count,mention_rate,"
        "first_place_count,avg_position_rank"
    )
    assert len(lines) == 3
    assert "Glow Serum" in lines[1]


# ── report_data ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_report_data_csv(db_session, client, user, project):
    db_session.add_all(
        [
            ReportJob(
                id=_new_id(),
                project_id=project.id,
                type="weekly",
                scope={"locale": "zh-CN"},
                status="done",
                created_by=user.id,
            ),
            ReportJob(
                id=_new_id(),
                project_id=project.id,
                type="lead_diagnostic",
                scope={"locale": "zh-CN"},
                status="failed",
                error="LLM timeout",
                created_by=user.id,
            ),
        ]
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "report_data"},
    )
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    lines = dl.text.strip().split("\n")
    assert lines[0].startswith("report_id,type,status,scheduled_cron,created_at")
    # 2 reports + header
    assert len(lines) == 3
    assert "weekly" in dl.text
    assert "LLM timeout" in dl.text


# ── status reaches done after each new type ──────────────────────


@pytest.mark.asyncio
async def test_all_4_new_types_mark_status_done(db_session, client, user, project):
    """Smoke test — after download every new type lands in 'done' status."""
    for export_type in ("citation_list", "topic_coverage", "products_list", "report_data"):
        create = await client.post(
            f"/api/v1/projects/{project.id}/exports",
            headers=_bearer(user),
            json={"export_type": export_type},
        )
        job_id = create.json()["id"]
        await client.get(
            f"/api/v1/projects/{project.id}/exports/{job_id}/download",
            headers=_bearer(user),
        )
        status = await client.get(
            f"/api/v1/projects/{project.id}/exports/{job_id}",
            headers=_bearer(user),
        )
        assert status.json()["status"] == "done"
        assert status.json()["finished_at"] is not None
