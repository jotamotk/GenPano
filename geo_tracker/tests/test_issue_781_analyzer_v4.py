from __future__ import annotations

from collections.abc import AsyncGenerator
from copy import deepcopy
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer import cli as analyzer_cli
from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.citation_mapper import CitationMapping
from geo_tracker.analyzer.llm_analyzer import (
    BrandAnalysis,
    DimensionResult,
    DriverResult,
    LLMAnalysisResult,
    ProductFeatureResult,
)
from geo_tracker.analyzer.v4_contract import validate_analyzer_v4_package
from geo_tracker.db.models import (
    AnalysisFactLink,
    AnalysisStatus,
    AnalyzerQualityFlag,
    AnalyzerRun,
    Base,
    Brand,
    BrandMention,
    CitationSource,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    SentimentDriver,
    Topic,
)


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


async def _seed_response(session: AsyncSession) -> tuple[Brand, LLMResponse]:
    day = datetime(2026, 5, 13, 9, 0)
    target = Brand(
        id=7811,
        name="AcmeBeauty",
        aliases=["Acme"],
        industry="beauty",
        website="https://acme.example",
    )
    session.add_all(
        [
            target,
            Topic(id=7812, brand_id=7811, text="Acme serum", category="skincare"),
            Prompt(
                id=7813,
                topic_id=7812,
                text="Which serum fits sensitive skin?",
                intent="non_brand",
                language="en",
            ),
        ]
    )
    await session.flush()
    session.add(
        Query(
            id=7814,
            prompt_id=7813,
            brand_id=7811,
            query_text="Which serum fits sensitive skin?",
            target_llm="deepseek",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    await session.flush()
    response = LLMResponse(
        id=7815,
        query_id=7814,
        raw_text=(
            "AcmeBeauty Calm Serum is recommended for sensitive skin because "
            "it uses gentle ceramides. Acme official guidance supports the serum."
        ),
        citations_json=[
            {
                "url": "https://acme.example/calm-serum",
                "title": "Acme Calm Serum",
                "index": 1,
            }
        ],
        collected_at=day,
        analysis_status=AnalysisStatus.DONE.value,
    )
    session.add(response)
    await session.commit()
    return target, response


def _valid_v4_package(response_id: int = 7815, query_id: int = 7814) -> dict:
    return {
        "analysis_meta": {
            "schema_version": "analyzer_v4",
            "language": "en",
            "response_quality": "ok",
            "model": "test-model",
            "prompt_version": "issue-781-test",
            "input_response_id": response_id,
            "input_query_id": query_id,
            "created_at": "2026-05-13T09:00:00",
            "validator_status": "passed",
            "validator_errors": [],
        },
        "entities": [
            {
                "entity_key": "ent_brand_acme",
                "entity_type": "brand",
                "raw_name": "AcmeBeauty",
                "canonical_id": str(7811),
                "canonical_name": "AcmeBeauty",
                "canonicalization_status": "matched",
                "evidence_quote": "AcmeBeauty Calm Serum",
                "confidence": 0.97,
                "quality_flags": [],
            },
            {
                "entity_key": "ent_product_calm",
                "entity_type": "product",
                "raw_name": "Calm Serum",
                "canonical_id": None,
                "canonical_name": None,
                "canonicalization_status": "unresolved",
                "evidence_quote": "AcmeBeauty Calm Serum",
                "confidence": 0.88,
                "quality_flags": ["product_unresolved"],
            },
        ],
        "mentions": [
            {
                "mention_key": "mention_acme_calm",
                "entity_key": "ent_product_calm",
                "response_id": response_id,
                "raw_text": "AcmeBeauty Calm Serum",
                "normalized_text": "AcmeBeauty Calm Serum",
                "mention_type": "product",
                "position": "top",
                "sentiment_label": "positive",
                "sentiment_score": 0.72,
                "evidence_quote": "AcmeBeauty Calm Serum is recommended",
                "confidence": 0.93,
                "quality_flags": [],
            }
        ],
        "sentiment_drivers": [
            {
                "driver_key": "driver_sensitive",
                "mention_key": "mention_acme_calm",
                "target_entity_key": "ent_product_calm",
                "sentiment_label": "positive",
                "driver_type": "recommendation",
                "driver_summary": "Recommended for sensitive skin",
                "evidence_quote": "recommended for sensitive skin",
                "confidence": 0.91,
                "quality_flags": [],
            },
            {
                "driver_key": "driver_gentle",
                "mention_key": "mention_acme_calm",
                "target_entity_key": "ent_product_calm",
                "sentiment_label": "mixed",
                "driver_type": "uncertainty",
                "driver_summary": "Gentle but unresolved product canonicalization",
                "evidence_quote": "uses gentle ceramides",
                "confidence": 0.7,
                "quality_flags": ["mixed_sentiment"],
            },
        ],
        "product_features": [
            {
                "feature_key": "feature_ceramide",
                "product_entity_key": "ent_product_calm",
                "brand_entity_key": "ent_brand_acme",
                "feature_type": "ingredient",
                "feature_name": "ceramides",
                "feature_value": "gentle",
                "evidence_quote": "uses gentle ceramides",
                "confidence": 0.87,
                "quality_flags": [],
            }
        ],
        "relations": [
            {
                "relation_key": "relation_sensitive",
                "subject_entity_key": "ent_product_calm",
                "relation_type": "recommended_for",
                "object_entity_key": "ent_need_sensitive",
                "direction": "directed",
                "evidence_quote": "recommended for sensitive skin",
                "confidence": 0.9,
                "quality_flags": ["relation_unresolved"],
            }
        ],
        "citations": [
            {
                "citation_key": "citation_official",
                "url": "https://acme.example/calm-serum",
                "domain": "acme.example",
                "title": "Acme Calm Serum",
                "source_type": "official",
                "attribution_method": "official_domain",
                "mentioned_entity_keys": ["ent_brand_acme", "ent_product_calm"],
                "linked_fact_keys": ["mention_acme_calm", "relation_sensitive"],
                "evidence_quote": "Acme official guidance supports the serum",
                "confidence": 0.92,
                "quality_flags": [],
            }
        ],
        "quality_flags": [],
    }


def _legacy_projection(raw_package: dict) -> LLMAnalysisResult:
    return LLMAnalysisResult(
        brands=[
            BrandAnalysis(
                brand_name="AcmeBeauty",
                product_name="Calm Serum",
                position_type="first_recommendation",
                position_rank=1,
                detail_level="detailed",
                sentiment="positive",
                sentiment_score=0.72,
                sentiment_drivers=[
                    DriverResult(
                        driver_text="Recommended for sensitive skin",
                        polarity="positive",
                        category="recommendation",
                        strength=0.91,
                        source_quote="recommended for sensitive skin",
                    ),
                    DriverResult(
                        driver_text="Gentle ceramides",
                        polarity="mixed",
                        category="ingredient",
                        strength=0.7,
                        source_quote="uses gentle ceramides",
                    ),
                ],
                product_features=[
                    ProductFeatureResult(
                        feature_name="ceramides",
                        feature_sentiment="positive",
                        scenario="sensitive skin",
                        context_snippet="uses gentle ceramides",
                    )
                ],
            )
        ],
        dimension=DimensionResult(industry="beauty", product="serum", category="skincare"),
        raw_json=deepcopy(raw_package),
    )


class _FakeDetector:
    def detect(self, *_args, **_kwargs):
        return [
            DetectedBrand(
                brand_name="AcmeBeauty",
                brand_id=7811,
                is_target=True,
                mention_count=2,
                context_snippets=["AcmeBeauty Calm Serum is recommended"],
            )
        ]


class _StaticLLMAnalyzer:
    provider = "test-provider"
    model = "test-model"
    prompt_version = "issue-781-test"

    def __init__(self, result: LLMAnalysisResult):
        self._result = result

    async def analyze(self, *_args, **_kwargs):
        return self._result


class _FakeCitationMapper:
    def map_citations(self, *_args, **_kwargs):
        return [
            CitationMapping(
                url="https://acme.example/calm-serum",
                domain="acme.example",
                title="Acme Calm Serum",
                citation_index=1,
                source_type="official_site",
                brand_name="AcmeBeauty",
            )
        ]


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, result: LLMAnalysisResult) -> None:
    monkeypatch.setattr(analyzer_cli, "BrandDetector", lambda: _FakeDetector())
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", lambda: _StaticLLMAnalyzer(result))
    monkeypatch.setattr(analyzer_cli, "CitationMapper", lambda: _FakeCitationMapper())


@pytest.mark.asyncio
async def test_analyzer_v4_validator_accepts_full_package() -> None:
    package = _valid_v4_package()
    package["entities"][1]["canonical_id"] = "product-calm-serum"
    package["entities"][1]["canonical_name"] = "Calm Serum"
    package["entities"][1]["canonicalization_status"] = "matched"
    package["entities"][1]["quality_flags"] = []
    package["entities"].append(
        {
            "entity_key": "ent_need_sensitive",
            "entity_type": "need",
            "raw_name": "sensitive skin",
            "canonical_id": None,
            "canonical_name": None,
            "canonicalization_status": "not_applicable",
            "evidence_quote": "recommended for sensitive skin",
            "confidence": 0.86,
            "quality_flags": [],
        }
    )
    package["relations"][0]["quality_flags"] = []
    package["sentiment_drivers"][1]["sentiment_label"] = "positive"
    package["sentiment_drivers"][1]["quality_flags"] = []

    result = validate_analyzer_v4_package(
        package,
        response_text=(
            "AcmeBeauty Calm Serum is recommended for sensitive skin because "
            "it uses gentle ceramides. Acme official guidance supports the serum."
        ),
        response_id=7815,
        query_id=7814,
    )

    assert result.is_valid is True
    assert result.validator_status == "passed"
    assert result.errors == []
    assert result.package["analysis_meta"]["schema_version"] == "analyzer_v4"


@pytest.mark.asyncio
async def test_analyzer_v4_rejects_invalid_json_without_deleting_current_facts(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    old_analysis = ResponseAnalysis(
        response_id=response.id,
        total_brands_mentioned=1,
        target_brand_mentioned=True,
        raw_analysis_json={"legacy": "good"},
    )
    old_mention = BrandMention(
        response_id=response.id,
        brand_id=target.id,
        brand_name="AcmeBeauty",
        product_name="Calm Serum",
        is_target=True,
        mention_count=1,
    )
    session.add_all([old_analysis, old_mention])
    await session.flush()
    session.add_all(
        [
            SentimentDriver(
                mention_id=old_mention.id,
                response_id=response.id,
                brand_name="AcmeBeauty",
                driver_text="old good driver",
                polarity="positive",
                source_quote="old quote",
            ),
            CitationSource(
                response_id=response.id,
                mention_id=old_mention.id,
                url="https://acme.example/old",
            ),
        ]
    )
    await session.commit()

    invalid = LLMAnalysisResult(raw_json=None)
    invalid.parse_status = "invalid_json"
    invalid.parse_error = "Expecting value at line 1"
    invalid.raw_output = "{not-json"
    _patch_pipeline(monkeypatch, invalid)

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "failed"
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 1
    assert await session.scalar(select(func.count(BrandMention.id))) == 1
    assert await session.scalar(select(func.count(SentimentDriver.id))) == 1
    assert await session.scalar(select(func.count(CitationSource.id))) == 1
    run = await session.scalar(select(AnalyzerRun).where(AnalyzerRun.response_id == response.id))
    assert run is not None
    assert run.status == "failed"
    flag_codes = (
        await session.execute(
            select(AnalyzerQualityFlag.code).where(AnalyzerQualityFlag.response_id == response.id)
        )
    ).scalars().all()
    assert "invalid_json" in flag_codes


@pytest.mark.asyncio
async def test_analyzer_v4_flags_missing_evidence_and_unlinked_citation(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    package = _valid_v4_package(response.id, response.query_id)
    package["mentions"][0]["evidence_quote"] = ""
    package["citations"][0]["linked_fact_keys"] = []
    _patch_pipeline(monkeypatch, _legacy_projection(package))

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "done"
    run = await session.scalar(select(AnalyzerRun).where(AnalyzerRun.response_id == response.id))
    assert run is not None
    assert run.status == "partial"
    flag_codes = set(
        (
            await session.execute(
                select(AnalyzerQualityFlag.code).where(
                    AnalyzerQualityFlag.response_id == response.id
                )
            )
        ).scalars().all()
    )
    assert {"missing_evidence_quote", "citation_unlinked"} <= flag_codes
    analysis = await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
    )
    assert analysis is not None
    assert analysis.raw_analysis_json["analysis_meta"]["validator_status"] == "passed_with_flags"


@pytest.mark.asyncio
async def test_analyzer_v4_persists_relation_unresolved_without_kg_writes(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    package = _valid_v4_package(response.id, response.query_id)
    _patch_pipeline(monkeypatch, _legacy_projection(package))

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "done"
    relation = await session.scalar(
        select(ResponseRelationFact).where(ResponseRelationFact.response_id == response.id)
    )
    assert relation is not None
    assert relation.relation_key == "relation_sensitive"
    assert relation.status == "unresolved"
    assert relation.kg_candidate_id is None
    flag_codes = (
        await session.execute(
            select(AnalyzerQualityFlag.code).where(AnalyzerQualityFlag.response_id == response.id)
        )
    ).scalars().all()
    assert "relation_unresolved" in flag_codes


@pytest.mark.asyncio
async def test_analyzer_v4_persists_entities_relation_and_citation_fact_links(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    package = _valid_v4_package(response.id, response.query_id)
    _patch_pipeline(monkeypatch, _legacy_projection(package))

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert result["status"] == "done"
    assert await session.scalar(select(func.count(ResponseEntity.id))) == 2
    assert await session.scalar(select(func.count(ResponseRelationFact.id))) == 1
    links = (
        await session.execute(
            select(AnalysisFactLink).where(AnalysisFactLink.response_id == response.id)
        )
    ).scalars().all()
    assert {(link.fact_type, link.fact_key, link.linked_fact_key) for link in links} == {
        ("citation", "citation_official", "mention_acme_calm"),
        ("citation", "citation_official", "relation_sensitive"),
    }


@pytest.mark.asyncio
async def test_analyzer_v4_rerun_is_idempotent_for_current_facts(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, response = await _seed_response(session)
    package = _valid_v4_package(response.id, response.query_id)
    _patch_pipeline(monkeypatch, _legacy_projection(package))

    first = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )
    second = await analyzer_cli.analyze_single_response(
        session,
        response,
        target,
        [],
        "non_brand",
    )

    assert first["status"] == "done"
    assert second["status"] == "done"
    assert await session.scalar(select(func.count(AnalyzerRun.id))) == 2
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 1
    assert await session.scalar(select(func.count(BrandMention.id))) == 1
    assert await session.scalar(select(func.count(ResponseEntity.id))) == 2
    assert await session.scalar(select(func.count(ResponseRelationFact.id))) == 1
    assert await session.scalar(select(func.count(AnalysisFactLink.id))) == 2
