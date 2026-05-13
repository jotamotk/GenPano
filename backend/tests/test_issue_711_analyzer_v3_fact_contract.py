"""Issue #711 analyzer v3 fact package contract tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FACT_CONTRACT_PATH = REPO_ROOT / "geo_tracker" / "analyzer" / "fact_contract.py"
_SPEC = importlib.util.spec_from_file_location("issue_711_fact_contract", FACT_CONTRACT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
fact_contract = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = fact_contract
_SPEC.loader.exec_module(fact_contract)

AnalyzerCitationInput = fact_contract.AnalyzerCitationInput
AnalyzerMentionInput = fact_contract.AnalyzerMentionInput
AnalyzerResponseInput = fact_contract.AnalyzerResponseInput
build_response_fact_package_v3 = fact_contract.build_response_fact_package_v3
validate_response_fact_package_v3 = fact_contract.validate_response_fact_package_v3


def _response(
    *,
    response_id: int = 71101,
    raw_text: str = "BestCoffer beats AcmeGrind for quiet office coffee.",
    has_analysis: bool = True,
    analysis_status: str = "done",
    mentions: list[AnalyzerMentionInput] | None = None,
    citations: list[AnalyzerCitationInput] | None = None,
) -> AnalyzerResponseInput:
    return AnalyzerResponseInput(
        response_id=response_id,
        query_id=72101,
        prompt_id=73101,
        topic_id=74101,
        project_brand_id=24,
        engine="chatgpt",
        profile_id="pf-711",
        collected_at="2026-05-12T00:00:00",
        analysis_status=analysis_status,
        has_analysis=has_analysis,
        raw_text=raw_text,
        mentions=mentions or [],
        citations=citations or [],
    )


def _mention(
    *,
    mention_id: int,
    brand_id: int | None,
    brand_name: str,
    is_target: bool = False,
    mention_count: int = 1,
    product_name: str | None = None,
    position_type: str | None = None,
    position_rank: int | None = None,
    sentiment: str | None = None,
    sentiment_score: float | None = None,
    drivers: list[dict] | None = None,
) -> AnalyzerMentionInput:
    return AnalyzerMentionInput(
        mention_id=mention_id,
        response_id=71101,
        brand_id=brand_id,
        brand_name=brand_name,
        raw_name=brand_name,
        is_target=is_target,
        mention_count=mention_count,
        context_snippet=f"{brand_name} quoted evidence",
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        sentiment_drivers=drivers or [],
        product_name=product_name,
        position_type=position_type,
        position_rank=position_rank,
        provenance="test",
    )


def test_v3_package_contains_locked_contract_fields_and_validates() -> None:
    target = _mention(
        mention_id=1,
        brand_id=24,
        brand_name="BestCoffer",
        is_target=True,
        product_name="Brew Max",
        position_type="ranked_list",
        position_rank=1,
        sentiment="positive",
        sentiment_score=0.8,
        drivers=[
            {
                "driver_text": "quiet grinder",
                "polarity": "positive",
                "source_quote": "BestCoffer is the quiet grinder pick",
            }
        ],
    )
    competitor = _mention(
        mention_id=2,
        brand_id=25,
        brand_name="AcmeGrind",
        mention_count=2,
        position_type="ranked_list",
        position_rank=2,
    )
    package = build_response_fact_package_v3(
        _response(
            mentions=[target, competitor],
            citations=[
                AnalyzerCitationInput(
                    citation_id=10,
                    response_id=71101,
                    mention_id=1,
                    url="https://coffee.example/review",
                    domain="coffee.example",
                    source_type="publisher",
                    tier=1,
                    title="Office coffee review",
                )
            ],
        ),
        target_brand_id=24,
        target_brand_name="BestCoffer",
        target_aliases=["Best Coffer"],
        configured_competitors=[
            {"brand_id": 25, "brand_name": "AcmeGrind", "aliases": ["Acme Grind"]},
        ],
        source_brand_id=24,
        provider="openai",
        model="gpt-4.1-mini",
        prompt_version="issue-711-test",
        raw_output={"brands": ["BestCoffer", "AcmeGrind"]},
        topic_name="Office grinder shortlist",
        topic_dimension="category",
    )

    assert package["analyzer_version"] == "v3"
    assert package["response_id"] == 71101
    assert package["provider"] == "openai"
    assert package["model"] == "gpt-4.1-mini"
    assert package["raw_output_sha256"]
    assert package["idempotency_key"].startswith("71101:v3:")
    assert package["coverage"]["parse_status"] == "ok"
    assert package["entities"]["target"]["mentioned"] is True
    assert package["entities"]["configured_competitors"][0]["mentioned"] is True
    assert package["sov"]["formula_status"] == "ok"
    assert package["sentiment"]["source_quotes"] == ["BestCoffer is the quiet grinder pick"]
    assert package["citations"]["attributed_citations"][0]["domain"] == "coffee.example"
    assert package["citations"]["unresolved_citations"] == []
    assert package["topic"]["topic_name"] == "Office grinder shortlist"
    assert package["products"][0]["product_name"] == "Brew Max"
    assert package["geo_pano"]["formula_status"] == "ok"
    assert validate_response_fact_package_v3(package) == []


def test_v3_package_marks_target_only_sov_unresolved_citations_and_parse_failure() -> None:
    package = build_response_fact_package_v3(
        _response(
            has_analysis=False,
            analysis_status="failed",
            mentions=[
                _mention(
                    mention_id=1,
                    brand_id=24,
                    brand_name="BestCoffer",
                    is_target=True,
                    sentiment="positive",
                    sentiment_score=0.5,
                )
            ],
            citations=[
                AnalyzerCitationInput(
                    citation_id=11,
                    response_id=71101,
                    mention_id=None,
                    url="https://unknown.example/post",
                    domain="unknown.example",
                    source_type="social",
                )
            ],
        ),
        target_brand_id=24,
        target_brand_name="BestCoffer",
        target_aliases=[],
        configured_competitors=[],
        provider="openai",
        model="gpt-4.1-mini",
        prompt_version="issue-711-test",
        raw_output={"error": "json_parse_error"},
        parse_status="failed",
        validation_errors=["json_parse_error"],
    )

    assert package["coverage"]["parse_status"] == "failed"
    assert "json_parse_error" in package["coverage"]["validation_errors"]
    assert package["sov"]["formula_status"] == "partial"
    assert "target_only_sov" in package["sov"]["reason_codes"]
    assert package["sentiment"]["formula_status"] == "partial"
    assert "missing_sentiment_quote" in package["sentiment"]["reason_codes"]
    assert package["citations"]["formula_status"] == "partial"
    assert package["citations"]["unresolved_citations"][0]["domain"] == "unknown.example"
    assert "unresolved_citation_attribution" in package["citations"]["reason_codes"]
    assert package["geo_pano"]["formula_status"] == "partial"
    assert validate_response_fact_package_v3(package) == []


def test_v3_topic_metrics_do_not_treat_competitor_only_evidence_as_visibility() -> None:
    package = build_response_fact_package_v3(
        _response(
            mentions=[
                _mention(
                    mention_id=2,
                    brand_id=25,
                    brand_name="AcmeGrind",
                    position_type="ranked_list",
                    position_rank=1,
                )
            ],
        ),
        target_brand_id=24,
        target_brand_name="BestCoffer",
        target_aliases=[],
        configured_competitors=[
            {"brand_id": 25, "brand_name": "AcmeGrind", "aliases": ["Acme Grind"]},
        ],
        provider="openai",
        model="gpt-4.1-mini",
        prompt_version="issue-711-test",
        raw_output={"brands": ["AcmeGrind"]},
    )

    assert package["visibility"]["is_visible"] is False
    assert package["rank"]["rank_basis"] is None
    assert package["topic_metrics"]["visible"] is False
    assert package["topic_metrics"]["rank_basis"] == 0
    assert package["topic_metrics"]["formula_status"] == "partial"
    assert "missing_target_visibility_evidence" in package["topic_metrics"]["reason_codes"]
