from collections.abc import AsyncGenerator
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.analyzer import cli as analyzer_cli
from geo_tracker.analyzer import llm_analyzer as llm_analyzer_module
from geo_tracker.analyzer.brand_detector import DetectedBrand
from geo_tracker.analyzer.llm_analyzer import LLMAnalysisResult, LLMAnalyzer
from geo_tracker.db.models import (
    AnalysisStatus,
    AnalyzerQualityFlag,
    AnalyzerRun,
    Base,
    Brand,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
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
    day = datetime(2026, 5, 14, 8, 0)
    brand = Brand(
        id=8441, name="BestCoffer", aliases=["Best Coffer"], industry="coffee"
    )
    session.add_all(
        [
            brand,
            Topic(
                id=8442,
                brand_id=8441,
                text="BestCoffer alternatives",
                category="coffee",
            ),
            Prompt(
                id=8443,
                topic_id=8442,
                text="Which coffee brand is best for office teams?",
                intent="non_brand",
                language="en",
            ),
        ]
    )
    await session.flush()
    session.add(
        Query(
            id=8444,
            prompt_id=8443,
            brand_id=8441,
            query_text="Which coffee brand is best for office teams?",
            target_llm="deepseek",
            status=QueryStatus.DONE.value,
            created_at=day,
        )
    )
    await session.flush()
    response = LLMResponse(
        id=8445,
        query_id=8444,
        raw_text="BestCoffer is mentioned in the response.",
        citations_json=[],
        collected_at=day,
        analysis_status=AnalysisStatus.PENDING.value,
    )
    session.add(response)
    await session.commit()
    return brand, response


class _FakeDetector:
    def detect(self, *_args, **_kwargs):
        return [
            DetectedBrand(
                brand_name="BestCoffer",
                brand_id=8441,
                is_target=True,
                mention_count=1,
                context_snippets=["BestCoffer is mentioned"],
            )
        ]


class _FakeCitationMapper:
    def map_citations(self, *_args, **_kwargs):
        return []


class _StaticLLMAnalyzer:
    provider = "ark"
    model = "test-model"
    prompt_version = "issue-844-test"

    def __init__(self, result: LLMAnalysisResult):
        self._result = result

    async def analyze(self, *_args, **_kwargs):
        return self._result


class _FailingCompletions:
    async def create(self, *_args, **_kwargs):
        raise RuntimeError("provider exploded")


class _InvalidJsonCompletions:
    async def create(self, *_args, **_kwargs):
        return SimpleNamespace(
            usage={"total_tokens": 10},
            choices=[SimpleNamespace(message=SimpleNamespace(content="{not-json"))],
        )


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, result: LLMAnalysisResult) -> None:
    monkeypatch.setattr(analyzer_cli, "BrandDetector", lambda: _FakeDetector())
    monkeypatch.setattr(analyzer_cli, "LLMAnalyzer", lambda: _StaticLLMAnalyzer(result))
    monkeypatch.setattr(analyzer_cli, "CitationMapper", lambda: _FakeCitationMapper())


def _llm_analyzer_with_client(client) -> LLMAnalyzer:
    analyzer = object.__new__(LLMAnalyzer)
    analyzer.client = client
    analyzer.model = "test-model"
    return analyzer


@pytest.mark.asyncio
async def test_llm_analyzer_missing_provider_config_returns_typed_failure() -> None:
    analyzer = _llm_analyzer_with_client(SimpleNamespace(api_key=""))

    result = await analyzer.analyze(
        response_text="BestCoffer answer",
        detected_brands=[],
        intent="non_brand",
        target_brand="BestCoffer",
    )

    assert result.parse_status == "missing_provider_config"
    assert result.parse_error == "ARK_API_KEY not set"
    assert result.raw_json is None


@pytest.mark.asyncio
async def test_llm_analyzer_provider_exception_returns_typed_failure() -> None:
    analyzer = _llm_analyzer_with_client(
        SimpleNamespace(
            api_key="test-key",
            chat=SimpleNamespace(completions=_FailingCompletions()),
        )
    )

    result = await analyzer.analyze(
        response_text="BestCoffer answer",
        detected_brands=[],
        intent="non_brand",
        target_brand="BestCoffer",
    )

    assert result.parse_status == "provider_failed"
    assert "provider exploded" in (result.parse_error or "")
    assert result.raw_json is None


@pytest.mark.asyncio
async def test_llm_analyzer_invalid_json_returns_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_analyzer_module, "HAS_JSON_REPAIR", False)
    analyzer = _llm_analyzer_with_client(
        SimpleNamespace(
            api_key="test-key",
            chat=SimpleNamespace(completions=_InvalidJsonCompletions()),
        )
    )

    result = await analyzer.analyze(
        response_text="BestCoffer answer",
        detected_brands=[],
        intent="non_brand",
        target_brand="BestCoffer",
    )

    assert result.parse_status == "invalid_json"
    assert "Expecting property name" in (result.parse_error or "")
    assert result.raw_json is None


@pytest.mark.asyncio
async def test_ok_status_without_raw_analyzer_json_is_not_persisted_as_done(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brand, response = await _seed_response(session)
    _patch_pipeline(monkeypatch, LLMAnalysisResult(parse_status="ok", raw_json=None))

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "non_brand",
    )

    assert result["status"] == "failed"
    assert result["error"] == "missing_raw_analyzer_json"
    await session.refresh(response)
    assert response.analysis_status == AnalysisStatus.FAILED.value
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 0
    run = await session.scalar(
        select(AnalyzerRun).where(AnalyzerRun.response_id == response.id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.failure_code == "missing_raw_analyzer_json"
    flag_codes = (
        (
            await session.execute(
                select(AnalyzerQualityFlag.code).where(
                    AnalyzerQualityFlag.response_id == response.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert "missing_raw_analyzer_json" in flag_codes


@pytest.mark.asyncio
async def test_ok_status_with_non_analyzer_json_is_not_legacy_packaged_as_done(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brand, response = await _seed_response(session)
    raw_json = {"error": "rate limit"}
    _patch_pipeline(
        monkeypatch, LLMAnalysisResult(parse_status="ok", raw_json=raw_json)
    )

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "non_brand",
    )

    assert result["status"] == "failed"
    assert result["error"] == "invalid_analyzer_schema"
    await session.refresh(response)
    assert response.analysis_status == AnalysisStatus.FAILED.value
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 0
    run = await session.scalar(
        select(AnalyzerRun).where(AnalyzerRun.response_id == response.id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.failure_code == "invalid_analyzer_schema"
    assert (
        run.raw_output_sha256
        == hashlib.sha256(
            json.dumps(
                raw_json, sort_keys=True, ensure_ascii=False, default=str
            ).encode("utf-8")
        ).hexdigest()
    )
    flag_codes = (
        (
            await session.execute(
                select(AnalyzerQualityFlag.code).where(
                    AnalyzerQualityFlag.response_id == response.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert "invalid_analyzer_schema" in flag_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parse_status", "parse_error", "expected_code"),
    [
        ("missing_provider_config", "ARK_API_KEY not set", "missing_provider_config"),
        ("provider_failed", "provider exploded", "provider_failed"),
        ("invalid_json", "Expecting value", "invalid_json"),
    ],
)
async def test_provider_and_parse_failures_are_not_persisted_as_done(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    parse_status: str,
    parse_error: str,
    expected_code: str,
) -> None:
    brand, response = await _seed_response(session)
    _patch_pipeline(
        monkeypatch,
        LLMAnalysisResult(
            parse_status=parse_status,
            parse_error=parse_error,
            raw_json=None,
            raw_output="not-json" if parse_status == "invalid_json" else None,
        ),
    )

    result = await analyzer_cli.analyze_single_response(
        session,
        response,
        brand,
        [],
        "non_brand",
    )

    assert result["status"] == "failed"
    await session.refresh(response)
    assert response.analysis_status == AnalysisStatus.FAILED.value
    assert await session.scalar(select(func.count(ResponseAnalysis.id))) == 0
    run = await session.scalar(
        select(AnalyzerRun).where(AnalyzerRun.response_id == response.id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.failure_code == expected_code
    if parse_status == "invalid_json":
        assert run.raw_output_sha256 == hashlib.sha256(b"not-json").hexdigest()
    else:
        assert run.raw_output_sha256 is None
