"""Issue #602 analyzer fact package contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from geo_tracker.analyzer.fact_contract import (  # noqa: E402
    AnalyzerCitationInput,
    AnalyzerMentionInput,
    AnalyzerResponseInput,
    build_response_fact_packages,
)


def _response(
    *,
    response_id: int = 1,
    raw_text: str = "Estee Lauder is mentioned without competitors.",
    has_analysis: bool = True,
    analysis_status: str = "done",
    mentions: list[AnalyzerMentionInput] | None = None,
    citations: list[AnalyzerCitationInput] | None = None,
) -> AnalyzerResponseInput:
    return AnalyzerResponseInput(
        response_id=response_id,
        query_id=10 + response_id,
        prompt_id=20 + response_id,
        topic_id=30 + response_id,
        project_brand_id=12,
        engine="chatgpt",
        profile_id="pf-test",
        collected_at="2026-05-12T00:00:00",
        analysis_status=analysis_status,
        has_analysis=has_analysis,
        raw_text=raw_text,
        mentions=mentions or [],
        citations=citations or [],
    )


def _mention(
    *,
    brand_id: int | None,
    brand_name: str,
    raw_name: str | None = None,
    is_target: bool = False,
    mention_count: int = 1,
    sentiment: str | None = None,
    sentiment_score: float | None = None,
    drivers: list[dict] | None = None,
) -> AnalyzerMentionInput:
    return AnalyzerMentionInput(
        mention_id=100 + (brand_id or 0),
        response_id=1,
        brand_id=brand_id,
        brand_name=brand_name,
        raw_name=raw_name or brand_name,
        is_target=is_target,
        mention_count=mention_count,
        context_snippet=f"{brand_name} context",
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        sentiment_drivers=drivers or [],
        provenance="test",
    )


def test_target_only_responses_do_not_yield_sov_ok() -> None:
    packages = build_response_fact_packages(
        [_response(mentions=[_mention(brand_id=12, brand_name="Estee Lauder", is_target=True)])],
        target_brand_id=12,
        target_brand_name="Estee Lauder",
        target_aliases=["雅诗兰黛"],
        configured_competitors=[],
    )

    assert packages["sov"]["status"] == "missing_required_inputs"
    assert packages["sov"]["numerator_target_mentions"] == 1
    assert packages["sov"]["denominator_competitive_mentions"] == 1
    assert "target_only_sov" in packages["sov"]["reason_codes"]


def test_competitor_text_without_structured_mentions_is_extracted_as_partial_evidence() -> None:
    packages = build_response_fact_packages(
        [
            _response(
                raw_text="雅诗兰黛 and Clinique are compared, but only 雅诗兰黛 is structured.",
                mentions=[_mention(brand_id=12, brand_name="雅诗兰黛", is_target=True)],
            )
        ],
        target_brand_id=12,
        target_brand_name="雅诗兰黛",
        target_aliases=["Estee Lauder"],
        configured_competitors=[
            {"brand_id": 99, "brand_name": "Clinique", "aliases": ["倩碧"]},
        ],
    )

    clinique = next(
        fact for fact in packages["entities"]["facts"] if fact["raw_name"] == "Clinique"
    )
    assert clinique["entity_role"] == "configured_competitor"
    assert clinique["source"] == "text_configured_competitor"
    assert "brand_mentions" in clinique["missing_inputs"]
    assert packages["sov"]["status"] == "partial"
    assert "competitor_text_without_structured_brand_mentions" in packages["sov"]["reason_codes"]


def test_sentiment_score_only_remains_partial_for_explanatory_modules() -> None:
    packages = build_response_fact_packages(
        [
            _response(
                mentions=[
                    _mention(
                        brand_id=12,
                        brand_name="Estee Lauder",
                        is_target=True,
                        sentiment="positive",
                        sentiment_score=0.8,
                    ),
                    _mention(brand_id=99, brand_name="Clinique"),
                ],
            )
        ],
        target_brand_id=12,
        target_brand_name="Estee Lauder",
        target_aliases=[],
        configured_competitors=[],
    )

    assert packages["sentiment"]["status"] == "partial"
    assert packages["sentiment"]["score_count"] == 1
    assert packages["sentiment"]["driver_count"] == 0
    assert packages["sentiment"]["quote_count"] == 0
    assert "missing_sentiment_driver_quote" in packages["sentiment"]["reason_codes"]


def test_missing_analyzer_rows_block_ok_and_do_not_become_zero() -> None:
    packages = build_response_fact_packages(
        [
            _response(
                response_id=1,
                has_analysis=True,
                mentions=[_mention(brand_id=12, brand_name="Estee Lauder", is_target=True)],
            ),
            _response(
                response_id=2,
                has_analysis=False,
                analysis_status="done",
                mentions=[],
            ),
        ],
        target_brand_id=12,
        target_brand_name="Estee Lauder",
        target_aliases=[],
        configured_competitors=[],
    )

    assert packages["coverage"]["eligible_count"] == 2
    assert packages["coverage"]["analyzed_count"] == 1
    assert packages["coverage"]["missing_analyzer_count"] == 1
    assert packages["coverage"]["status"] == "partial"
    assert packages["pano_geo"]["status"] == "missing_required_inputs"
    assert packages["pano_geo"]["component_readiness"]["coverage"] == "partial"
    assert packages["sov"]["numerator_target_mentions"] == 1
    assert packages["sentiment"]["score_count"] is None


def test_fact_package_generation_is_idempotent_for_reruns() -> None:
    response = _response(
        mentions=[
            _mention(
                brand_id=12,
                brand_name="Estee Lauder",
                is_target=True,
                sentiment="positive",
                sentiment_score=0.7,
                drivers=[
                    {
                        "driver_text": "strong hydration",
                        "polarity": "positive",
                        "source_quote": "strong hydration",
                    }
                ],
            ),
            _mention(brand_id=99, brand_name="Clinique", mention_count=2),
        ],
        citations=[
            AnalyzerCitationInput(
                citation_id=1,
                response_id=1,
                mention_id=112,
                url="https://example.com/a",
                domain="Example.COM",
                source_type="publisher",
                tier=2,
            )
        ],
    )

    first = build_response_fact_packages(
        [response],
        target_brand_id=12,
        target_brand_name="Estee Lauder",
        target_aliases=[],
        configured_competitors=[],
    )
    second = build_response_fact_packages(
        [response],
        target_brand_id=12,
        target_brand_name="Estee Lauder",
        target_aliases=[],
        configured_competitors=[],
    )

    assert second == first
    assert first["sov"]["status"] == "ok"
    assert first["sentiment"]["status"] == "ok"
    assert first["citations"]["status"] == "ok"
