"""Phase 2.2 — metrics / topics / sentiment / citations endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    AnalysisFactLink,
    AnalyzerQualityFlag,
    AnalyzerRun,
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectTopicPin,
    SentimentDriver,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import _metrics_service
from app.api.v1.projects._metrics_dto import MetricSeries, MetricSeriesPoint
from app.api.v1.projects.contracts.builder import _first_class_analyzer_fact_rollup
from app.api.v1.projects.contracts.models import AnalyticsContractContext, ProjectScope
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _partial_package_gap_context(metric_key: str = "coverage") -> AnalyticsContractContext:
    return AnalyticsContractContext(
        project_scope=ProjectScope(
            project_id=_new_id(),
            primary_brand_id=42,
            requested_brand_id=42,
        ),
        state="partial",
        state_reason="partial_analyzer_data",
        missing_inputs=["missing_analyzer_fact_packages"],
        missing_sources=[
            "response_analyses.raw_analysis_json.analyzer_fact_package_v3",
            "response_analyses.raw_analysis_json.analyzer_fact_packages",
        ],
        missing_reasons=["missing_analyzer_fact_packages"],
        evidence_counts={
            "geo_score_daily_rows": 30,
            "brand_mention_count": 48,
            "brand_mentioned_response_count": 48,
            "admin_fact_response_count": 70,
        },
        formula_status="partial",
        metric_formula_evidence={
            metric_key: {
                "metric_key": metric_key,
                "formula_status": "partial",
                "reason_codes": ["missing_analyzer_fact_packages"],
                "source_tables": [
                    "response_analyses.raw_analysis_json.analyzer_fact_package_v3",
                    "response_analyses.raw_analysis_json.analyzer_fact_packages",
                ],
            }
        },
    )


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def test_metrics_series_contract_marks_aggregate_points_ok_when_only_package_metadata_missing():
    series = [
        MetricSeries(
            metric="mention_rate",
            points=[MetricSeriesPoint(date=date(2026, 5, 11), value=0.814)],
            formula_status="ok",
        )
    ]

    out = _metrics_service._apply_metric_series_contract(
        series,
        _partial_package_gap_context("coverage"),
    )

    assert out[0].points == series[0].points
    assert out[0].formula_status == "ok"
    assert out[0].state == "ok"


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
    # SoV's competitive denominator (`brand_mentions.competitive_set`) is
    # critical missing input for the SoV metric — no competitor mentions
    # in this fixture — so points stay cleared per the no-fallback contract.
    assert by_metric["sov"]["points"] == []
    assert by_metric["sov"]["formula_status"] == "missing_required_inputs"
    assert "brand_mentions.competitive_set" in by_metric["sov"]["missing_inputs"]


@pytest_asyncio.fixture
async def project_with_primary_sources_and_competitors(
    db_session: AsyncSession, user: User
) -> Project:
    """Issue #948 fixture: all primary sources are populated for the
    target brand AND a competitor, but analyzer fact packages are absent.

    This is the scenario where the user reported `—` for 提及率 /
    引用份额 / 行业排名 / Sentiment on `/brand/overview` and
    `/brand/visibility`: `GeoScoreDaily`, `BrandMention` (target +
    competitor), `CitationSource`, and `SentimentDriver` rows all exist,
    yet the analyzer-evidence rollup is empty so peripheral missing
    inputs surface as `missing_analyzer_fact_packages`. Before the
    issue-948 fix, `_apply_metric_series_contract` cleared all points
    in this state, breaking the frontend KPI cards.
    """
    p = Project(user_id=user.id, name="Peripheral Missing", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
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
    # Target brand + competitor mentions (so SoV's competitive_set is
    # non-empty), with sentiment + position rank so all per-metric
    # primary sources are populated.
    for i in range(8):
        db_session.add(
            BrandMention(
                response_id=7000 + i,
                brand_id=42,
                brand_name="Test Brand",
                sentiment="positive",
                sentiment_score=0.7,
                position_rank=(i % 3) + 1,
                created_at=datetime.now() - timedelta(days=i % 5),
            )
        )
    for i in range(4):
        db_session.add(
            BrandMention(
                response_id=7100 + i,
                brand_id=99,
                brand_name="Competitor",
                sentiment="neutral",
                sentiment_score=0.0,
                position_rank=(i % 4) + 1,
                created_at=datetime.now() - timedelta(days=i % 5),
            )
        )
    await db_session.commit()

    bm_id = (
        await db_session.execute(
            BrandMention.__table__.select().where(BrandMention.brand_id == 42).limit(1)
        )
    ).first()
    bm_id_val = bm_id[0] if bm_id else 1
    for i in range(3):
        db_session.add(
            CitationSource(
                response_id=7000 + i,
                mention_id=bm_id_val,
                url=f"https://example.com/948-{i}",
                domain="example.com",
                title=f"948 Article {i}",
                source_type="article",
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_metric_series_with_evidence_survives_peripheral_missing_inputs(
    client, user, project_with_primary_sources_and_competitors
):
    """Issue #948: KPI cards showed `—` because `_apply_metric_series_contract`
    cleared `points` when only peripheral analyzer inputs (e.g.
    `missing_analyzer_fact_packages`) were missing, even though the value
    itself was computed from real `GeoScoreDaily` rows and all per-metric
    primary sources (brand_mentions, citation_sources) were populated.

    The fix keeps `points` populated and reports metric-level
    `formula_status=ok` when aggregate evidence proves the displayed value,
    so the frontend E2E has a concrete metric-level ok KPI to assert instead of
    rendering `—`.

    Critical missing inputs (denominator missing, primary source missing,
    project unbound) still clear points per the no-fallback contract —
    see `test_metrics_marks_brand_mentions_partial_when_daily_rollups_missing`
    and `test_citation_metric_agrees_with_citations_when_sources_absent`.
    """
    resp = await client.get(
        f"/api/v1/projects/{project_with_primary_sources_and_competitors.id}/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    by_metric = {s["metric"]: s for s in body["series"]}
    # All 5 metrics have GeoScoreDaily evidence rows AND per-metric primary
    # sources populated. Only peripheral analyzer-fact-package evidence is
    # missing. Points must survive (issue #948) so the frontend renders
    # numbers instead of `—`.
    for metric in ("mention_rate", "sov", "rank", "sentiment", "citation"):
        assert len(by_metric[metric]["points"]) == 30, (
            f"{metric} should keep points when GeoScoreDaily evidence + "
            f"primary sources exist (only analyzer fact packages missing)"
        )
        assert by_metric[metric]["formula_status"] == "ok", (
            f"{metric} formula_status should be ok when GeoScoreDaily points "
            f"and primary sources back the displayed values (got "
            f"{by_metric[metric]['formula_status']})"
        )
        assert by_metric[metric]["formula_status"] != "missing_required_inputs", (
            f"{metric} formula_status should not be missing_required_inputs "
            f"when value is real (got {by_metric[metric]['formula_status']})"
        )


@pytest.mark.asyncio
async def test_sentiment_formula_status_partial_when_score_label_complete_with_aux_flags(
    db_session: AsyncSession,
):
    """Issue #948 follow-up: sentiment KPI rendered ``—`` on
    ``/v1/projects/:id/overview`` for BestCoffer because
    ``_first_class_analyzer_fact_rollup`` reported
    ``formula_status: missing_required_inputs`` whenever the analyzer
    emitted auxiliary driver-related flags (e.g.
    ``malformed_sentiment_driver_dropped`` from analyzer v4 enum
    rejections in ``geo_tracker/analyzer/v4_contract.py``), even though
    the sentiment formula's required inputs (``score_count`` +
    ``label_count``) were both present (200 / 200 / 172 drivers in the
    live response).

    The fix: when ``score_count > 0`` AND ``label_count > 0`` AND no
    critical reason is present in
    ``_METRIC_BLOCKING_REASONS["sentiment"]`` /
    ``_COMMON_METRIC_BLOCKING_REASONS``, downgrade the sentiment
    evidence to ``formula_partial`` instead of
    ``missing_required_inputs``. Reason codes are preserved so the UI
    can hover "Coverage partial". This mirrors the SoV /
    MentionRate / GeoScore pattern from PR #953 / PR #960 so the
    frontend gate ``canUseContractMetricValue('partial', { formula_status:
    'partial' })`` keeps surfacing the 0.21 value.
    """
    today = datetime(2026, 5, 14, 12, 0, 0)
    target_response_ids: set[int] = set()
    for i in range(8):
        response_id = 9700 + i
        target_response_ids.add(response_id)
        run = AnalyzerRun(
            response_id=response_id,
            schema_version="analyzer_v4",
            status="done",
            trigger_source="test",
            validator_summary_json={"schema_version": "analyzer_v4"},
            started_at=today,
            completed_at=today,
        )
        db_session.add(run)
        await db_session.flush()

        mention = BrandMention(
            response_id=response_id,
            brand_id=4242,
            brand_name="BestCoffer",
            sentiment="positive",
            sentiment_score=0.21,
            mention_count=1,
            position_rank=2,
            created_at=today - timedelta(days=i % 5),
        )
        db_session.add(mention)
        await db_session.flush()

        db_session.add(
            SentimentDriver(
                mention_id=mention.id,
                response_id=response_id,
                brand_name="BestCoffer",
                driver_text=f"driver-{i}",
                polarity="positive",
                category="value",
                strength=0.7,
                source_quote=f"quote-{i}",
                created_at=today - timedelta(days=i % 5),
            )
        )
        # Auxiliary analyzer-v4 flags: driver-type enum failures (see
        # geo_tracker/analyzer/v4_contract.py:60-71). These DO NOT
        # invalidate the sentiment formula, only the driver-type
        # breakdown.
        db_session.add(
            AnalyzerQualityFlag(
                run_id=run.id,
                response_id=response_id,
                flag_key=f"flag_malformed_driver_{i}",
                severity="warning",
                code="malformed_sentiment_driver_dropped",
                message="Driver dropped due to malformed shape.",
                target_type="driver",
                target_key=f"driver_{i}",
                blocks_metric_readiness=True,
            )
        )
    await db_session.commit()

    evidence, _counts, _reasons = await _first_class_analyzer_fact_rollup(
        db_session,
        brand_id=4242,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        target_response_ids=target_response_ids,
    )

    sentiment = evidence["sentiment"]
    # Required formula inputs are fully present (score + label per mention).
    assert sentiment["score_count"] == 8
    assert sentiment["label_count"] == 8
    # Driver evidence exists (auxiliary).
    assert sentiment["driver_count"] == 8
    # Auxiliary flag reason codes are preserved so the UI can render the
    # "Coverage partial" hover info.
    assert "malformed_sentiment_driver_dropped" in sentiment["reason_codes"]
    # Issue #948 follow-up: the value is computable from real evidence,
    # so the producer must emit ``formula_partial`` (not
    # ``missing_required_inputs``) — the frontend gate accepts ``partial``
    # since PR #960 and renders the value instead of ``—``.
    assert sentiment["formula_status"] == "partial"


@pytest.mark.asyncio
async def test_citation_formula_status_partial_when_attribution_complete_with_aux_flags(
    db_session: AsyncSession,
):
    """Issue #948 follow-up: citation KPI rendered ``—`` on
    ``/v1/projects/:id/overview`` and ``/metrics`` for BestCoffer even
    after PR #976 attributed 27 citations to the target brand. Root
    cause: ``_first_class_analyzer_fact_rollup`` set
    ``citation.formula_status = missing_required_inputs`` whenever the
    analyzer-side quality flags (``citation_unlinked``,
    ``malformed_citation_dropped``, ``evidence_quote_mismatch`` from
    ``analyzer_quality_flags``) were present, even when the citation
    formula's required inputs (``citation_total > 0`` AND
    ``attributed_citations > 0`` AND ``fact_link_count > 0``) were all
    satisfied.

    The fix: when those three inputs are complete AND no critical reason
    in ``_METRIC_BLOCKING_REASONS["citation"]`` /
    ``_COMMON_METRIC_BLOCKING_REASONS`` is present, downgrade to
    ``formula_partial`` instead of ``missing_required_inputs``. Auxiliary
    quality flags are preserved in ``reason_codes`` so the UI can render
    the "Coverage partial" hover info. Mirrors the SoV / MentionRate /
    GeoScore / Sentiment patterns from PR #953, #962, and #976 so the
    frontend gate ``canUseContractMetricValue('partial', { formula_status:
    'partial' })`` (added by PR #960) keeps surfacing the citation share.
    """
    today = datetime(2026, 5, 14, 12, 0, 0)
    brand_id = 4242
    target_response_ids: set[int] = set()
    for i in range(3):
        response_id = 9800 + i
        target_response_ids.add(response_id)
        run = AnalyzerRun(
            response_id=response_id,
            schema_version="analyzer_v4",
            status="done",
            trigger_source="test",
            validator_summary_json={"schema_version": "analyzer_v4"},
            started_at=today,
            completed_at=today,
        )
        db_session.add(run)
        await db_session.flush()

        # Target brand mention so the citation can be attributed via mention_id.
        mention = BrandMention(
            response_id=response_id,
            brand_id=brand_id,
            brand_name="BestCoffer",
            sentiment="positive",
            sentiment_score=0.3,
            mention_count=1,
            position_rank=2,
            created_at=today - timedelta(days=i),
        )
        db_session.add(mention)
        await db_session.flush()

        # Attributed citation: post PR #976 response-level proximity fallback,
        # orphan citations in a target-mentioning response carry mention_id
        # pointing at the target brand's BrandMention row.
        db_session.add(
            CitationSource(
                response_id=response_id,
                mention_id=mention.id,
                url=f"https://news.example.cn/article-{i}",
                domain="news.example.cn",
                title=f"Coverage of BestCoffer #{i}",
                source_type="news",
                citation_index=i + 1,
                created_at=today - timedelta(days=i),
            )
        )
        # fact_link_count > 0: at least one analysis_fact_links row for citation
        # facts on this run. Without it, line 377-378 of builder.py appends
        # ``unresolved_citation_attribution`` to citation_reasons, which IS in
        # the blocking set and correctly stays as missing_required_inputs.
        db_session.add(
            AnalysisFactLink(
                run_id=run.id,
                response_id=response_id,
                fact_type="citation",
                fact_key=f"citation_{i}",
                linked_fact_type="brand",
                linked_fact_key=f"brand_{brand_id}",
                link_type="supports",
                status="current",
                created_at=today,
            )
        )
        # Auxiliary analyzer-v4 quality flag: ``citation_unlinked`` is in
        # ``flag_reasons["citation"]`` per the v4 contract but NOT in the
        # citation blocking set. Without the fix, this single non-critical
        # flag pushes citation_status to missing_required_inputs even though
        # the formula inputs are complete.
        db_session.add(
            AnalyzerQualityFlag(
                run_id=run.id,
                response_id=response_id,
                flag_key=f"flag_citation_unlinked_{i}",
                severity="warning",
                code="citation_unlinked",
                message="Auxiliary citation flag — does not block attribution.",
                target_type="citation",
                target_key=f"citation_{i}",
                blocks_metric_readiness=True,
            )
        )
    await db_session.commit()

    evidence, _counts, _reasons = await _first_class_analyzer_fact_rollup(
        db_session,
        brand_id=brand_id,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        target_response_ids=target_response_ids,
    )

    citation = evidence["citation"]
    # All three citation formula inputs are complete.
    assert citation["citation_count"] == 3
    assert citation["attributed_count"] == 3
    assert citation["fact_link_count"] == 3
    # Auxiliary flag reason codes preserved so the UI can render the
    # "Coverage partial" hover info.
    assert "citation_unlinked" in citation["reason_codes"]
    # Issue #948 follow-up: with all formula inputs present and no critical
    # blocking reason, status downgrades to ``partial`` (not
    # ``missing_required_inputs``) — the frontend gate (PR #960) accepts
    # ``partial`` and renders the citation share value instead of ``—``.
    assert citation["formula_status"] == "partial"


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
