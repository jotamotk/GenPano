"""Phase 2.2 — metrics / topics / sentiment / citations endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectTopicPin,
    SentimentDriver,
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
        email=f"m-{uuid.uuid4().hex[:6]}@example.com",
        name="Metrics User",
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
async def project_with_full_data(db_session: AsyncSession, user: User) -> Project:
    p = Project(user_id=user.id, name="Full Data", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    # 30d of geo_score_daily
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.5,
                mention_rate=0.5 + i * 0.005,
                avg_sov=0.3 + i * 0.005,
                avg_sentiment=0.6 + i * 0.005,
                avg_position_rank=2.5 - i * 0.05,
                citation_rate=0.2 + i * 0.003,
                total_queries=100,
            )
        )
    # brand_mentions: 10 positive, 5 neutral, 3 negative
    sentiments = ["positive"] * 10 + ["neutral"] * 5 + ["negative"] * 3
    for i, s in enumerate(sentiments):
        db_session.add(
            BrandMention(
                response_id=2000 + i,
                brand_id=42,
                brand_name="Test Brand",
                sentiment=s,
                sentiment_score=0.7 if s == "positive" else (-0.5 if s == "negative" else 0.0),
                position_rank=(i % 5) + 1,
                created_at=datetime.now() - timedelta(days=i % 30),
            )
        )
    # sentiment_drivers
    for i in range(8):
        db_session.add(
            SentimentDriver(
                mention_id=1,  # FK to brand_mentions; in fresh DB just any id
                response_id=2000 + i,
                brand_name="Test Brand",
                driver_text=f"feature-{i}",
                polarity="positive" if i % 2 == 0 else "negative",
                category="taste",
                strength=0.7,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    # topic pins
    db_session.add(ProjectTopicPin(project_id=p.id, topic_id=101, state="tracked"))
    db_session.add(ProjectTopicPin(project_id=p.id, topic_id=102, state="ignored"))
    # citations: insert mentions first to satisfy FK, then citations
    await db_session.commit()

    # Pull a brand_mention ID to attach citations
    bm_id = (
        await db_session.execute(
            BrandMention.__table__.select().where(BrandMention.brand_id == 42).limit(1)
        )
    ).first()
    bm_id_val = bm_id[0] if bm_id else 1
    for i in range(5):
        db_session.add(
            CitationSource(
                response_id=2000 + i,
                mention_id=bm_id_val,
                url=f"https://example.com/article-{i}",
                domain="example.com" if i < 3 else "another.com",
                title=f"Article {i}",
                source_type="article",
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_metrics_default_window(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["brand_id"] == 42
    series_keys = {s["metric"] for s in body["series"]}
    assert series_keys == {"mention_rate", "sov", "rank", "sentiment", "citation"}
    by_metric = {s["metric"]: s for s in body["series"]}
    assert len(by_metric["mention_rate"]["points"]) == 30
    assert len(by_metric["rank"]["points"]) == 30
    assert len(by_metric["sentiment"]["points"]) == 30
    assert len(by_metric["citation"]["points"]) == 30
    assert by_metric["sov"]["points"] == []
    assert by_metric["sov"]["formula_status"] == "missing_required_inputs"
    assert "brand_mentions.competitive_set" in by_metric["sov"]["missing_inputs"]


@pytest.mark.asyncio
async def test_metrics_subset_series(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/metrics",
        headers=_bearer(user),
        params={"series": "mention_rate,sov"},
    )
    assert resp.status_code == 200
    body = resp.json()
    series_keys = {s["metric"] for s in body["series"]}
    assert series_keys == {"mention_rate", "sov"}


@pytest.mark.asyncio
async def test_metrics_marks_brand_mentions_partial_when_daily_rollups_missing(
    client, user, db_session
):
    p = Project(user_id=user.id, name="Mention Metrics", primary_brand_id=12, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    now = datetime.now()
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=5100 + i,
                brand_id=12,
                brand_name="Estée Lauder",
                position_rank=(i % 4) + 1,
                sentiment_score=0.8,
                created_at=now - timedelta(days=i % 3),
            )
        )
    for i in range(3):
        db_session.add(
            BrandMention(
                response_id=5200 + i,
                brand_id=77,
                brand_name="Other Brand",
                position_rank=3,
                sentiment_score=0.1,
                created_at=now - timedelta(days=i % 3),
            )
        )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"series": "mention_rate,sov,sentiment,rank,citation"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert "eligible_response_denominator" in body["missing_inputs"]
    by_metric = {s["metric"]: s for s in body["series"]}
    assert by_metric["mention_rate"]["points"] == []
    assert by_metric["sov"]["points"] == []
    assert by_metric["sentiment"]["points"] == []
    assert by_metric["rank"]["points"] == []


@pytest.mark.asyncio
async def test_metrics_invalid_date_returns_422(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/metrics",
        headers=_bearer(user),
        params={"from": "not-a-date"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_topics_returns_pinned(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/topics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["total"] == 2
    states = {t["state"] for t in body["items"]}
    assert states == {"tracked", "ignored"}


@pytest.mark.asyncio
async def test_topics_empty(client, user, db_session):
    p = Project(user_id=user.id, name="Topic Empty", primary_brand_id=99)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    resp = await client.get(f"/api/v1/projects/{p.id}/topics", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["items"] == []


@pytest.mark.asyncio
async def test_sentiment_distribution_and_keywords(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/sentiment",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    dist = body["distribution"]
    assert dist["positive_count"] == 10
    assert dist["negative_count"] == 3
    assert dist["neutral_count"] == 5
    assert round(dist["positive_pct"], 1) == round(10 / 18 * 100, 1)
    assert len(body["top_keywords"]) >= 4
    assert len(body["top_drivers"]) >= 4


@pytest.mark.asyncio
async def test_sentiment_empty_for_no_brand(client, user, db_session):
    p = Project(user_id=user.id, name="No Brand", primary_brand_id=None)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    resp = await client.get(f"/api/v1/projects/{p.id}/sentiment", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["distribution"]["positive_count"] == 0


@pytest.mark.asyncio
async def test_citations_list_and_domains(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/citations",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["total"] == 5
    assert len(body["items"]) == 5
    domains = {d["domain"] for d in body["by_domain_top"]}
    assert "example.com" in domains
    assert "another.com" in domains


@pytest.mark.asyncio
async def test_citations_pagination(client, user, project_with_full_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_full_data.id}/citations?page_size=2",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None


@pytest.mark.asyncio
async def test_phase_2_2_cross_tenant_returns_404(client, db_session, project_with_full_data):
    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    for path in ["metrics", "topics", "sentiment", "citations"]:
        resp = await client.get(
            f"/api/v1/projects/{project_with_full_data.id}/{path}",
            headers=_bearer(other),
        )
        assert resp.status_code == 404, f"path {path} should 404"
        assert resp.json()["detail"]["code"] == "not_found"
