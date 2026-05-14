"""Shared App analytics contract metadata for project-scoped endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from genpano_models import (
    AnalysisFactLink,
    AnalyzerQualityFlag,
    AnalyzerRun,
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    ProjectTopicPin,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    SentimentDriver,
)
from sqlalchemy import and_, bindparam, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._mention_rollups import brand_mention_match_condition, brand_mention_names
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _fact_rows,
    legacy_table_columns,
    legacy_table_exists,
)
from app.api.v1.projects.contracts.constants import (
    _BLOCKING_REASON_CODES as _BLOCKING_REASON_CODES,
)
from app.api.v1.projects.contracts.constants import (
    _COMMON_METRIC_BLOCKING_REASONS as _COMMON_METRIC_BLOCKING_REASONS,
)
from app.api.v1.projects.contracts.constants import (
    _METRIC_BLOCKING_REASONS as _METRIC_BLOCKING_REASONS,
)
from app.api.v1.projects.contracts.constants import (
    ANALYSIS_MISSING_REASON as ANALYSIS_MISSING_REASON,
)
from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_SOURCE as ANALYZER_FACT_PACKAGE_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    ANALYZER_FACT_PACKAGE_V3_SOURCE as ANALYZER_FACT_PACKAGE_V3_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_MISSING_INPUTS_STATUS as FORMULA_MISSING_INPUTS_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_NO_EVIDENCE_STATUS as FORMULA_NO_EVIDENCE_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_OK_STATUS as FORMULA_OK_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PARTIAL_STATUS as FORMULA_PARTIAL_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PENDING_SOURCE as FORMULA_PENDING_SOURCE,
)
from app.api.v1.projects.contracts.constants import (
    FORMULA_PENDING_STATUS as FORMULA_PENDING_STATUS,
)
from app.api.v1.projects.contracts.constants import (
    MISSING_PROJECT_BRAND_BINDING_REASON as MISSING_PROJECT_BRAND_BINDING_REASON,
)
from app.api.v1.projects.contracts.constants import (
    NO_AGGREGATE_ROWS_REASON as NO_AGGREGATE_ROWS_REASON,
)
from app.api.v1.projects.contracts.constants import (
    PROJECT_UNBOUND_REASON as PROJECT_UNBOUND_REASON,
)
from app.api.v1.projects.contracts.definitions import (
    formula_diagnostics_for as formula_diagnostics_for,
)
from app.api.v1.projects.contracts.definitions import (
    metric_definition as metric_definition,
)
from app.api.v1.projects.contracts.definitions import (
    metric_definitions as metric_definitions,
)
from app.api.v1.projects.contracts.format import (
    percent_display as percent_display,
)
from app.api.v1.projects.contracts.format import (
    ratio_decimal as ratio_decimal,
)
from app.api.v1.projects.contracts.format import (
    score_0_100 as score_0_100,
)
from app.api.v1.projects.contracts.models import (
    AnalyticsContractContext as AnalyticsContractContext,
)
from app.api.v1.projects.contracts.models import (
    DataFreshness as DataFreshness,
)
from app.api.v1.projects.contracts.models import (
    FormulaDiagnostics as FormulaDiagnostics,
)
from app.api.v1.projects.contracts.models import (
    IdentityDiagnostics as IdentityDiagnostics,
)
from app.api.v1.projects.contracts.models import (
    MetricDefinition as MetricDefinition,
)
from app.api.v1.projects.contracts.models import (
    MetricValue as MetricValue,
)
from app.api.v1.projects.contracts.models import (
    ProjectScope as ProjectScope,
)
from app.api.v1.projects.contracts.models import (
    ValueRange as ValueRange,
)
from app.api.v1.projects.contracts.package import (
    _as_package as _as_package,
)
from app.api.v1.projects.contracts.package import (
    _as_v3_package as _as_v3_package,
)
from app.api.v1.projects.contracts.package import (
    _json_int as _json_int,
)
from app.api.v1.projects.contracts.package import (
    _merge_status as _merge_status,
)
from app.api.v1.projects.contracts.package import (
    _package_date_in_window as _package_date_in_window,
)
from app.api.v1.projects.contracts.package import (
    _package_reason_codes as _package_reason_codes,
)
from app.api.v1.projects.contracts.package import (
    _package_response_ids as _package_response_ids,
)
from app.api.v1.projects.contracts.package import (
    _package_target_brand_id as _package_target_brand_id,
)
from app.api.v1.projects.contracts.package import (
    _repair_entries as _repair_entries,
)
from app.api.v1.projects.contracts.package import (
    _status_from_package as _status_from_package,
)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _metric_evidence_template(metric_key: str, status: str) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "formula_status": status,
        "reason_codes": [],
        "sample_response_ids": [],
    }


def _package_source_tables(packages: list[dict[str, Any]] | None = None) -> list[str]:
    sources = [
        str(package.get("_package_source"))
        for package in packages or []
        if package.get("_package_source")
    ]
    return _unique(sources) or [ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE]


def _evidence_source_tables(metric_evidence: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for evidence in metric_evidence.values():
        if not isinstance(evidence, dict):
            continue
        tables = evidence.get("source_tables")
        if isinstance(tables, list):
            sources.extend(str(table) for table in tables if table)
    return _unique(sources) or _package_source_tables()


def _blocking_metric_evidence(
    reason_codes: list[str],
    *,
    source_tables: list[str],
    sample_response_ids: list[int] | None = None,
) -> dict[str, Any]:
    sample_ids = sorted({int(value) for value in sample_response_ids or []})[:20]
    reasons = _unique(reason_codes)
    return {
        key: {
            "metric_key": key,
            "formula_status": FORMULA_MISSING_INPUTS_STATUS,
            "reason_codes": reasons,
            "source_tables": source_tables,
            "fact_classes": [key],
            "sample_response_ids": sample_ids,
        }
        for key in ("coverage", "sov", "sentiment", "citation", "pano_geo")
    }


def _rollup_sov(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("sov", FORMULA_NO_EVIDENCE_STATUS)
    numerator = 0
    denominator = 0
    competitors: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    for package in packages:
        sov = package.get("sov")
        if not isinstance(sov, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(sov.get("formula_status") or sov.get("status") or FORMULA_NO_EVIDENCE_STATUS),
        )
        numerator += int(sov.get("numerator_target_mentions") or 0)
        denominator += int(sov.get("denominator_competitive_mentions") or 0)
        if isinstance(sov.get("competitors"), list):
            competitors.extend(item for item in sov["competitors"] if isinstance(item, dict))
        reason_codes.extend(_package_reason_codes(package, "sov"))
        evidence["sample_response_ids"].extend(sov.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    competitor_count = len(
        {
            (
                item.get("brand_id"),
                str(item.get("brand_name") or item.get("raw_name") or ""),
            )
            for item in competitors
        }
    )
    has_competitive_denominator = denominator > 0 and denominator > numerator
    if has_competitive_denominator:
        reason_codes = [
            reason
            for reason in reason_codes
            if reason
            not in {
                "missing_competitive_extraction",
                "target_only_sov",
                "sov_empty",
                "sov_missing_required_inputs",
            }
        ]
        blocking_reasons = [
            reason
            for reason in reason_codes
            if reason in _METRIC_BLOCKING_REASONS["sov"]
            or reason in _COMMON_METRIC_BLOCKING_REASONS
        ]
        if not blocking_reasons:
            evidence["formula_status"] = (
                FORMULA_PARTIAL_STATUS
                if "partial_analyzer_coverage" in reason_codes
                or "missing_analyzer_rows" in reason_codes
                else FORMULA_OK_STATUS
            )
    evidence.update(
        {
            "numerator_name": "target_competitive_mentions",
            "denominator_name": "all_competitive_mentions",
            "numerator_count": numerator,
            "denominator_count": denominator,
            "competitor_count": competitor_count,
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["sov", "entities"],
        }
    )
    evidence["reason_codes"] = _unique(reason_codes)
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_sentiment(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("sentiment", FORMULA_NO_EVIDENCE_STATUS)
    score_count = label_count = driver_count = quote_count = 0
    for package in packages:
        sentiment = package.get("sentiment")
        if not isinstance(sentiment, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                sentiment.get("formula_status")
                or sentiment.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        score_count += int(sentiment.get("score_count") or 0)
        label_count += int(sentiment.get("label_count") or 0)
        driver_count += int(sentiment.get("driver_count") or 0)
        quote_count += int(sentiment.get("quote_count") or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "sentiment"))
        evidence["sample_response_ids"].extend(sentiment.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "numerator_name": "brand_scoped_sentiment_score_sum",
            "denominator_name": "target_mentions_with_sentiment_score_and_label",
            "score_count": score_count,
            "label_count": label_count,
            "driver_count": driver_count,
            "quote_count": quote_count,
            "source_tables": [
                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                ANALYZER_FACT_PACKAGE_SOURCE,
                "brand_mentions",
                "sentiment_drivers",
            ],
            "fact_classes": ["sentiment"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_citations(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("citation", FORMULA_NO_EVIDENCE_STATUS)
    counts = {
        "citation_count": 0,
        "attributed_count": 0,
        "unresolved_count": 0,
    }
    source_type_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    unresolved_source_type_counts: dict[str, int] = {}
    unresolved_tier_counts: dict[str, int] = {}
    for package in packages:
        citations = package.get("citations")
        if not isinstance(citations, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                citations.get("formula_status")
                or citations.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        for key in counts:
            counts[key] += int(citations.get(key) or 0)
        for source, target in (
            ("source_type_counts", source_type_counts),
            ("tier_counts", tier_counts),
            ("unresolved_source_type_counts", unresolved_source_type_counts),
            ("unresolved_tier_counts", unresolved_tier_counts),
        ):
            source_counts = citations.get(source)
            if isinstance(source_counts, dict):
                for name, count in source_counts.items():
                    target[str(name)] = target.get(str(name), 0) + int(count or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "citations"))
        evidence["sample_response_ids"].extend(citations.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "numerator_name": "target_attributed_citations",
            "denominator_name": "eligible_project_citations",
            **counts,
            "source_type_counts": source_type_counts,
            "tier_counts": tier_counts,
            "unresolved_source_type_counts": unresolved_source_type_counts,
            "unresolved_tier_counts": unresolved_tier_counts,
            "source_tables": [
                ANALYZER_FACT_PACKAGE_V3_SOURCE,
                ANALYZER_FACT_PACKAGE_SOURCE,
                "citation_sources",
            ],
            "fact_classes": ["citations"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(
        {int(value) for value in evidence["sample_response_ids"]}
    )
    return evidence


def _rollup_coverage(
    packages: list[dict[str, Any]],
    *,
    target_response_ids: set[int],
) -> dict[str, Any]:
    evidence = _metric_evidence_template("coverage", FORMULA_NO_EVIDENCE_STATUS)
    package_response_ids: set[int] = set()
    eligible = analyzed = failed = missing = 0
    for package in packages:
        coverage = package.get("coverage")
        if not isinstance(coverage, dict):
            continue
        package_response_ids.update(_package_response_ids(package))
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(
                coverage.get("formula_status")
                or coverage.get("status")
                or FORMULA_NO_EVIDENCE_STATUS
            ),
        )
        eligible += int(coverage.get("eligible_count") or 0)
        analyzed += int(coverage.get("analyzed_count") or 0)
        failed += int(coverage.get("failed_count") or 0)
        missing += int(coverage.get("missing_analyzer_count") or 0)
        evidence["reason_codes"].extend(_package_reason_codes(package, "coverage"))
    missing_ids = sorted(target_response_ids - package_response_ids)
    if missing_ids:
        evidence["formula_status"] = FORMULA_PARTIAL_STATUS
        evidence["reason_codes"].append("missing_analyzer_rows")
        missing += len(missing_ids)
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_OK_STATUS
    evidence.update(
        {
            "eligible_response_count": max(eligible, len(target_response_ids)),
            "analyzed_response_count": analyzed,
            "failed_response_count": failed,
            "missing_response_count": missing,
            "missing_response_ids": missing_ids[:20],
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["coverage"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
    evidence["sample_response_ids"] = sorted(package_response_ids)[:20]
    return evidence


def _rollup_pano_geo(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("pano_geo", FORMULA_NO_EVIDENCE_STATUS)
    readiness: dict[str, str] = {}
    for package in packages:
        pano = package.get("geo_pano") or package.get("pano_geo")
        if not isinstance(pano, dict):
            continue
        evidence["formula_status"] = _merge_status(
            evidence["formula_status"],
            str(pano.get("formula_status") or pano.get("status") or FORMULA_NO_EVIDENCE_STATUS),
        )
        component_readiness = pano.get("component_readiness")
        if isinstance(component_readiness, dict):
            for key, status in component_readiness.items():
                readiness[str(key)] = _merge_status(
                    readiness.get(str(key), FORMULA_OK_STATUS), str(status)
                )
        evidence["reason_codes"].extend(
            _package_reason_codes(package, "geo_pano") or _package_reason_codes(package, "pano_geo")
        )
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "component_readiness": readiness,
            "source_tables": _package_source_tables(packages),
            "fact_classes": ["pano_geo"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
    return evidence


def _latest_runs_by_response(
    runs: list[AnalyzerRun],
    target_response_ids: set[int],
) -> dict[int, AnalyzerRun]:
    latest: dict[int, AnalyzerRun] = {}
    for run in runs:
        response_id = int(run.response_id)
        if response_id not in target_response_ids:
            continue
        current = latest.get(response_id)
        if current is None:
            latest[response_id] = run
            continue
        current_ts = current.completed_at or current.started_at or datetime.min
        run_ts = run.completed_at or run.started_at or datetime.min
        if (run_ts, int(run.id or 0)) >= (current_ts, int(current.id or 0)):
            latest[response_id] = run
    return latest


def _quality_flag_reasons_by_metric(
    flags: list[AnalyzerQualityFlag],
) -> dict[str, list[str]]:
    reasons: dict[str, list[str]] = {
        "coverage": [],
        "sov": [],
        "sentiment": [],
        "citation": [],
        "pano_geo": [],
    }
    for flag in flags:
        code = str(flag.code or "partial_output")
        target_type = str(flag.target_type or "analysis")
        if target_type in {"citation"} or "citation" in code:
            reasons["citation"].append(code)
        elif target_type in {"driver", "sentiment", "mention"} and "sentiment" in code:
            reasons["sentiment"].append(code)
        elif target_type in {"entity", "mention", "brand"} and (
            "brand" in code or "entity" in code
        ):
            reasons["sov"].append(code)
        elif target_type in {"relation", "product", "feature"}:
            reasons["pano_geo"].append(code)
        else:
            reasons["coverage"].append(code)
    return {key: _unique(values) for key, values in reasons.items()}


async def _first_class_analyzer_fact_rollup(
    session: AsyncSession,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    target_response_ids: set[int],
) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    if not target_response_ids:
        return {}, {}, []

    run_rows = (
        (
            await session.execute(
                select(AnalyzerRun).where(
                    and_(
                        AnalyzerRun.response_id.in_(target_response_ids),
                        AnalyzerRun.schema_version == "analyzer_v4",
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    latest_runs = _latest_runs_by_response(list(run_rows), target_response_ids)
    if not latest_runs:
        return {}, {}, []

    latest_run_ids = {int(run.id) for run in latest_runs.values() if run.id is not None}
    analyzed_response_ids = {
        response_id
        for response_id, run in latest_runs.items()
        if str(run.status or "").lower() in {"done", "partial"}
    }
    failed_response_ids = {
        response_id
        for response_id, run in latest_runs.items()
        if str(run.status or "").lower() == "failed"
    }
    missing_response_ids = sorted(target_response_ids - set(latest_runs))

    brand_filter = await brand_mention_match_condition(session, brand_id)
    target_mentions = int(
        (
            await session.execute(
                select(
                    func.coalesce(func.sum(func.coalesce(BrandMention.mention_count, 1)), 0)
                ).where(
                    and_(
                        brand_filter,
                        BrandMention.response_id.in_(target_response_ids),
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    all_mentions = int(
        (
            await session.execute(
                select(
                    func.coalesce(func.sum(func.coalesce(BrandMention.mention_count, 1)), 0)
                ).where(BrandMention.response_id.in_(target_response_ids))
            )
        ).scalar_one()
        or 0
    )
    sentiment_row = (
        await session.execute(
            select(
                func.count(BrandMention.sentiment_score),
                func.count(BrandMention.sentiment),
                func.count(SentimentDriver.id),
                func.count(SentimentDriver.source_quote),
            )
            .select_from(BrandMention)
            .join(SentimentDriver, SentimentDriver.mention_id == BrandMention.id, isouter=True)
            .where(
                and_(
                    brand_filter,
                    BrandMention.response_id.in_(target_response_ids),
                )
            )
        )
    ).one()
    citation_total = int(
        (
            await session.execute(
                select(func.count(CitationSource.id)).where(
                    CitationSource.response_id.in_(target_response_ids)
                )
            )
        ).scalar_one()
        or 0
    )
    attributed_citations = int(
        (
            await session.execute(
                select(func.count(CitationSource.id))
                .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(
                    and_(
                        brand_filter,
                        BrandMention.response_id.in_(target_response_ids),
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    fact_link_count = 0
    relation_link_count = 0
    if latest_run_ids:
        fact_link_rows = (
            await session.execute(
                select(AnalysisFactLink.linked_fact_type).where(
                    and_(
                        AnalysisFactLink.run_id.in_(latest_run_ids),
                        AnalysisFactLink.fact_type == "citation",
                        AnalysisFactLink.status == "current",
                    )
                )
            )
        ).all()
        fact_link_count = len(fact_link_rows)
        relation_link_count = sum(1 for row in fact_link_rows if row[0] == "relation")

    entity_rows: list[ResponseEntity] = []
    relation_rows: list[ResponseRelationFact] = []
    blocking_flags: list[AnalyzerQualityFlag] = []
    if latest_run_ids:
        entity_rows = list(
            (
                await session.execute(
                    select(ResponseEntity).where(ResponseEntity.run_id.in_(latest_run_ids))
                )
            )
            .scalars()
            .all()
        )
        relation_rows = list(
            (
                await session.execute(
                    select(ResponseRelationFact).where(
                        and_(
                            ResponseRelationFact.run_id.in_(latest_run_ids),
                            ResponseRelationFact.status == "current",
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        blocking_flags = list(
            (
                await session.execute(
                    select(AnalyzerQualityFlag).where(
                        and_(
                            AnalyzerQualityFlag.run_id.in_(latest_run_ids),
                            AnalyzerQualityFlag.blocks_metric_readiness.is_(True),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
    flag_reasons = _quality_flag_reasons_by_metric(blocking_flags)

    coverage_reasons = list(flag_reasons["coverage"])
    if missing_response_ids:
        coverage_reasons.append("missing_analyzer_rows")
    if failed_response_ids:
        coverage_reasons.append("partial_analyzer_coverage")
    coverage_status = FORMULA_OK_STATUS if not coverage_reasons else FORMULA_PARTIAL_STATUS

    competitor_entities = {
        (
            entity.canonical_id,
            (entity.canonical_name or entity.raw_name or "").strip().lower(),
        )
        for entity in entity_rows
        if entity.entity_type == "brand"
        and entity.canonicalization_status == "matched"
        and str(entity.canonical_id or "") != str(brand_id)
    }
    sov_reasons = list(flag_reasons["sov"])
    if all_mentions <= 0:
        sov_reasons.append("sov_empty")
    elif all_mentions <= target_mentions:
        sov_reasons.append("target_only_sov")
    sov_status = FORMULA_OK_STATUS if not sov_reasons else FORMULA_MISSING_INPUTS_STATUS

    score_count = int(sentiment_row[0] or 0)
    label_count = int(sentiment_row[1] or 0)
    driver_count = int(sentiment_row[2] or 0)
    quote_count = int(sentiment_row[3] or 0)
    sentiment_reasons = list(flag_reasons["sentiment"])
    if target_mentions > 0 and score_count <= 0:
        sentiment_reasons.append("missing_sentiment_score_or_label")
    if target_mentions > 0 and label_count <= 0:
        sentiment_reasons.append("missing_sentiment_label")
    if driver_count > 0 and quote_count <= 0:
        sentiment_reasons.append("missing_sentiment_driver_quote")
    sentiment_status = FORMULA_OK_STATUS if not sentiment_reasons else FORMULA_MISSING_INPUTS_STATUS

    citation_reasons = list(flag_reasons["citation"])
    if citation_total <= 0:
        citation_reasons.append("citation_sources")
        citation_reasons.append("citation_empty")
    elif attributed_citations <= 0:
        citation_reasons.append("citation_sources.mention_id")
        citation_reasons.append("unresolved_citation_attribution")
    if citation_total > 0 and fact_link_count <= 0:
        citation_reasons.append("unresolved_citation_attribution")
    citation_status = FORMULA_OK_STATUS if not citation_reasons else FORMULA_MISSING_INPUTS_STATUS

    pano_reasons = list(flag_reasons["pano_geo"])
    if coverage_status != FORMULA_OK_STATUS:
        pano_reasons.extend(coverage_reasons)
    if sov_status != FORMULA_OK_STATUS:
        pano_reasons.extend(sov_reasons)
    if sentiment_status != FORMULA_OK_STATUS:
        pano_reasons.extend(sentiment_reasons)
    if citation_status != FORMULA_OK_STATUS:
        pano_reasons.extend(citation_reasons)
    pano_status = FORMULA_OK_STATUS if not pano_reasons else FORMULA_PARTIAL_STATUS

    metric_evidence = {
        "coverage": {
            **_metric_evidence_template("coverage", coverage_status),
            "eligible_response_count": len(target_response_ids),
            "analyzed_response_count": len(analyzed_response_ids),
            "failed_response_count": len(failed_response_ids),
            "missing_response_count": len(missing_response_ids),
            "missing_response_ids": missing_response_ids[:20],
            "reason_codes": _unique(coverage_reasons),
            "sample_response_ids": sorted(analyzed_response_ids)[:20],
            "source_tables": ["analyzer_runs"],
            "fact_classes": ["coverage"],
        },
        "sov": {
            **_metric_evidence_template("sov", sov_status),
            "numerator_name": "target_competitive_mentions",
            "denominator_name": "all_competitive_mentions",
            "numerator_count": target_mentions,
            "denominator_count": all_mentions,
            "competitor_count": len(competitor_entities),
            "reason_codes": _unique(sov_reasons),
            "sample_response_ids": sorted(analyzed_response_ids)[:20],
            "source_tables": ["brand_mentions", "response_entities"],
            "fact_classes": ["sov", "entities"],
        },
        "sentiment": {
            **_metric_evidence_template("sentiment", sentiment_status),
            "numerator_name": "brand_scoped_sentiment_score_sum",
            "denominator_name": "target_mentions_with_sentiment_score_and_label",
            "score_count": score_count,
            "label_count": label_count,
            "driver_count": driver_count,
            "quote_count": quote_count,
            "reason_codes": _unique(sentiment_reasons),
            "sample_response_ids": sorted(analyzed_response_ids)[:20],
            "source_tables": ["brand_mentions", "sentiment_drivers"],
            "fact_classes": ["sentiment"],
        },
        "citation": {
            **_metric_evidence_template("citation", citation_status),
            "numerator_name": "target_attributed_citations",
            "denominator_name": "eligible_project_citations",
            "citation_count": citation_total,
            "attributed_count": attributed_citations,
            "unresolved_count": max(citation_total - attributed_citations, 0),
            "fact_link_count": fact_link_count,
            "relation_link_count": relation_link_count,
            "reason_codes": _unique(citation_reasons),
            "sample_response_ids": sorted(analyzed_response_ids)[:20],
            "source_tables": ["citation_sources", "analysis_fact_links"],
            "fact_classes": ["citations"],
        },
        "pano_geo": {
            **_metric_evidence_template("pano_geo", pano_status),
            "component_readiness": {
                "coverage": coverage_status,
                "sov": sov_status,
                "sentiment": sentiment_status,
                "citation": citation_status,
            },
            "relation_fact_count": len(relation_rows),
            "reason_codes": _unique(pano_reasons),
            "sample_response_ids": sorted(analyzed_response_ids)[:20],
            "source_tables": [
                "analyzer_runs",
                "response_relation_facts",
                "analyzer_quality_flags",
            ],
            "fact_classes": ["pano_geo", "relations", "quality_flags"],
        },
    }
    reason_codes = _unique(
        [
            reason
            for evidence in metric_evidence.values()
            for reason in evidence.get("reason_codes", [])
        ]
    )
    counts = {
        "analyzer_run_count": len(latest_runs),
        "analyzer_entity_count": len(entity_rows),
        "analyzer_relation_fact_count": len(relation_rows),
        "analyzer_fact_link_count": fact_link_count,
        "analyzer_quality_flag_count": len(blocking_flags),
        "analyzer_blocking_quality_flag_count": len(blocking_flags),
        "analyzer_eligible_response_count": len(target_response_ids),
        "analyzer_analyzed_response_count": len(analyzed_response_ids),
        "analyzer_missing_response_count": len(missing_response_ids),
        "analyzer_failed_response_count": len(failed_response_ids),
        "analyzer_sov_numerator_target_mentions": target_mentions,
        "analyzer_sov_denominator_competitive_mentions": all_mentions,
        "analyzer_sov_competitor_count": len(competitor_entities),
        "analyzer_sentiment_score_count": score_count,
        "analyzer_sentiment_label_count": label_count,
        "analyzer_sentiment_driver_count": driver_count,
        "analyzer_sentiment_quote_count": quote_count,
        "analyzer_citation_count": citation_total,
        "analyzer_attributed_citation_count": attributed_citations,
        "analyzer_unresolved_citation_count": max(citation_total - attributed_citations, 0),
    }
    return metric_evidence, counts, reason_codes


async def _target_response_ids(
    session: AsyncSession,
    brand_id: int,
    *,
    from_dt: datetime,
    to_dt: datetime,
) -> set[int]:
    brand_filter = await brand_mention_match_condition(session, brand_id)
    rows = (
        await session.execute(
            select(BrandMention.response_id).where(
                and_(
                    brand_filter,
                    BrandMention.created_at >= from_dt,
                    BrandMention.created_at <= to_dt,
                )
            )
        )
    ).all()
    return {int(row[0]) for row in rows if row[0] is not None}


async def _pinned_topic_response_ids(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date,
    to_date: date,
) -> set[int] | None:
    if not all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
            await legacy_table_exists(session, "llm_responses"),
        ]
    ):
        return None
    topic_ids = [
        int(row[0])
        for row in (
            await session.execute(
                select(ProjectTopicPin.topic_id).where(
                    and_(
                        ProjectTopicPin.project_id == project.id,
                        ProjectTopicPin.state != "ignored",
                    )
                )
            )
        ).all()
        if row[0] is not None
    ]
    if not topic_ids:
        return None

    topic_cols = await legacy_table_columns(session, "topics")
    prompt_cols = await legacy_table_columns(session, "prompts")
    query_cols = await legacy_table_columns(session, "queries")
    response_cols = await legacy_table_columns(session, "llm_responses")
    if not (
        {"id"}.issubset(topic_cols)
        and {"id", "topic_id"}.issubset(prompt_cols)
        and {"id", "prompt_id"}.issubset(query_cols)
        and "id" in response_cols
    ):
        return set()

    response_on: list[str] = []
    if "query_id" in response_cols:
        response_on.append("r.query_id = q.id")
    if not response_on and "prompt_id" in response_cols:
        response_on.append("r.prompt_id = p.id")
    if not response_on:
        return set()

    predicates = ["t.id IN :topic_ids"]
    params: dict[str, Any] = {
        "topic_ids": topic_ids,
        "from_dt": datetime.combine(from_date, datetime.min.time()),
        "to_dt": datetime.combine(to_date, datetime.max.time()),
    }
    if "status" in topic_cols:
        predicates.append("COALESCE(t.status, 'active') <> 'archived'")
    if "status" in prompt_cols:
        predicates.append("COALESCE(p.status, 'active') <> 'archived'")
    if "status" in query_cols:
        predicates.append(
            "LOWER(COALESCE(q.status, 'done')) IN ('done', 'success', 'succeeded', 'completed')"
        )
    if "created_at" in query_cols:
        predicates.append("q.created_at >= :from_dt")
        predicates.append("q.created_at <= :to_dt")
    elif "created_at" in response_cols:
        predicates.append("r.created_at >= :from_dt")
        predicates.append("r.created_at <= :to_dt")

    rows = (
        await session.execute(
            text(
                f"""
                SELECT DISTINCT r.id
                FROM topics t
                JOIN prompts p ON p.topic_id = t.id
                JOIN queries q ON q.prompt_id = p.id
                JOIN llm_responses r ON {" OR ".join(response_on)}
                WHERE {" AND ".join(predicates)}
                """
            ).bindparams(bindparam("topic_ids", expanding=True)),
            params,
        )
    ).all()
    return {int(row[0]) for row in rows if row[0] is not None}


async def _project_eligible_response_ids(
    session: AsyncSession,
    project: Project,
    brand_id: int,
    *,
    from_date: date,
    to_date: date,
    from_dt: datetime,
    to_dt: datetime,
) -> set[int]:
    pinned_response_ids = await _pinned_topic_response_ids(
        session,
        project,
        from_date=from_date,
        to_date=to_date,
    )
    if pinned_response_ids is not None:
        if project.primary_brand_id is None or int(project.primary_brand_id) != int(brand_id):
            rows = await _fact_rows(
                session,
                project,
                filters=AnalysisFilters(from_date=from_date, to_date=to_date),
                brand_id_override=brand_id,
            )
            scoped_response_ids = {
                int(response_id)
                for row in rows
                if (response_id := row.get("response_id")) is not None
            }
            return pinned_response_ids & scoped_response_ids
        return pinned_response_ids
    if all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
        ]
    ):
        rows = await _fact_rows(
            session,
            project,
            filters=AnalysisFilters(from_date=from_date, to_date=to_date),
            brand_id_override=brand_id,
        )
        return {
            int(response_id) for row in rows if (response_id := row.get("response_id")) is not None
        }
    return await _target_response_ids(
        session,
        brand_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )


async def _analyzer_fact_rollup(
    session: AsyncSession,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    target_response_ids: set[int],
) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    if not target_response_ids:
        return {}, {}, []
    first_class = await _first_class_analyzer_fact_rollup(
        session,
        brand_id=brand_id,
        from_date=from_date,
        to_date=to_date,
        target_response_ids=target_response_ids,
    )
    if first_class[0]:
        return first_class
    rows = (
        await session.execute(
            select(ResponseAnalysis.raw_analysis_json).where(
                and_(
                    ResponseAnalysis.response_id.in_(target_response_ids),
                    ResponseAnalysis.raw_analysis_json.isnot(None),
                )
            )
        )
    ).all()
    packages: list[dict[str, Any]] = []
    for row in rows:
        package = _as_package(row[0])
        if package is None:
            continue
        package_response_ids = _package_response_ids(package)
        if not package_response_ids or not (package_response_ids & target_response_ids):
            continue
        target_brand_id = _package_target_brand_id(package)
        if target_brand_id is not None and target_brand_id != brand_id:
            continue
        if not _package_date_in_window(package, from_date, to_date):
            continue
        packages.append(package)

    if not packages:
        return {}, {}, []

    metric_evidence = {
        "coverage": _rollup_coverage(packages, target_response_ids=target_response_ids),
        "sov": _rollup_sov(packages),
        "sentiment": _rollup_sentiment(packages),
        "citation": _rollup_citations(packages),
        "pano_geo": _rollup_pano_geo(packages),
    }
    reason_codes = _unique(
        [
            reason
            for evidence in metric_evidence.values()
            for reason in evidence.get("reason_codes", [])
        ]
    )
    counts = {
        "analyzer_package_count": len(packages),
        "analyzer_eligible_response_count": int(
            metric_evidence["coverage"].get("eligible_response_count") or 0
        ),
        "analyzer_analyzed_response_count": int(
            metric_evidence["coverage"].get("analyzed_response_count") or 0
        ),
        "analyzer_missing_response_count": int(
            metric_evidence["coverage"].get("missing_response_count") or 0
        ),
        "analyzer_failed_response_count": int(
            metric_evidence["coverage"].get("failed_response_count") or 0
        ),
        "analyzer_sov_numerator_target_mentions": int(
            metric_evidence["sov"].get("numerator_count") or 0
        ),
        "analyzer_sov_denominator_competitive_mentions": int(
            metric_evidence["sov"].get("denominator_count") or 0
        ),
        "analyzer_sov_competitor_count": int(metric_evidence["sov"].get("competitor_count") or 0),
        "analyzer_sentiment_score_count": int(metric_evidence["sentiment"].get("score_count") or 0),
        "analyzer_sentiment_label_count": int(metric_evidence["sentiment"].get("label_count") or 0),
        "analyzer_sentiment_driver_count": int(
            metric_evidence["sentiment"].get("driver_count") or 0
        ),
        "analyzer_sentiment_quote_count": int(metric_evidence["sentiment"].get("quote_count") or 0),
        "analyzer_citation_count": int(metric_evidence["citation"].get("citation_count") or 0),
        "analyzer_attributed_citation_count": int(
            metric_evidence["citation"].get("attributed_count") or 0
        ),
        "analyzer_unresolved_citation_count": int(
            metric_evidence["citation"].get("unresolved_count") or 0
        ),
    }
    return metric_evidence, counts, reason_codes


def metric_evidence_for(
    context: AnalyticsContractContext, metric_key: str | None
) -> dict[str, Any] | None:
    if not metric_key:
        return None
    if metric_key in {"sov", "avg_sov"}:
        return context.metric_formula_evidence.get("sov")
    if metric_key in {"sentiment", "avg_sentiment"}:
        return context.metric_formula_evidence.get("sentiment")
    if metric_key in {"citation", "citation_rate", "avg_citation_rate"}:
        return context.metric_formula_evidence.get("citation")
    if metric_key in {"geo_score", "avg_geo_score", "pano_score", "final_geo_score"}:
        return context.metric_formula_evidence.get("pano_geo")
    if metric_key in {"mention_rate", "avg_mention_rate"}:
        return context.metric_formula_evidence.get("coverage")
    return None


def metric_formula_status(
    context: AnalyticsContractContext,
    metric_key: str | None,
    default: str | None = None,
) -> str | None:
    evidence = metric_evidence_for(context, metric_key)
    if not evidence:
        return default
    return str(evidence.get("formula_status") or default or FORMULA_NO_EVIDENCE_STATUS)


def metric_blocking_inputs_from_evidence(
    metric_key: str | None,
    evidence: dict[str, Any] | None,
) -> list[str]:
    if not metric_key or not evidence:
        return []
    status = str(evidence.get("formula_status") or FORMULA_NO_EVIDENCE_STATUS)
    if status == FORMULA_OK_STATUS:
        return []
    evidence_key = (
        "sov"
        if metric_key in {"sov", "avg_sov"}
        else "sentiment"
        if metric_key in {"sentiment", "avg_sentiment"}
        else "citation"
        if metric_key in {"citation", "citation_rate", "avg_citation_rate"}
        else "pano_geo"
        if metric_key in {"geo_score", "avg_geo_score", "pano_score", "final_geo_score"}
        else "coverage"
        if metric_key in {"mention_rate", "avg_mention_rate"}
        else metric_key
    )
    blocking_reasons = {
        *_COMMON_METRIC_BLOCKING_REASONS,
        *_METRIC_BLOCKING_REASONS.get(evidence_key, set()),
    }
    reasons = [str(reason) for reason in evidence.get("reason_codes", []) if reason]
    if evidence_key == "sov":
        denominator = int(evidence.get("denominator_count") or 0)
        numerator = int(evidence.get("numerator_count") or 0)
        if denominator > numerator:
            blocking_reasons = {
                reason
                for reason in blocking_reasons
                if reason
                not in {
                    "missing_competitive_extraction",
                    "target_only_sov",
                    "sov_empty",
                    "sov_missing_required_inputs",
                }
            }
    return _unique([reason for reason in reasons if reason in blocking_reasons])


def metric_missing_inputs(
    context: AnalyticsContractContext,
    metric_key: str | None,
) -> list[str]:
    evidence = metric_evidence_for(context, metric_key)
    return metric_blocking_inputs_from_evidence(metric_key, evidence)


async def _competitor_ids(session: AsyncSession, project: Project) -> list[int]:
    rows = (
        await session.execute(
            select(ProjectCompetitor.brand_id)
            .where(ProjectCompetitor.project_id == project.id)
            .order_by(ProjectCompetitor.brand_id)
        )
    ).all()
    return [int(row[0]) for row in rows if row[0] is not None]


async def build_contract_context(
    session: AsyncSession,
    project: Project,
    *,
    brand_id: int | None,
    from_date: date,
    to_date: date,
    has_data: bool,
    base_state: str,
    base_state_reason: str | None = None,
    base_missing_sources: list[str] | None = None,
    base_missing_inputs: list[str] | None = None,
    base_missing_reasons: list[str] | None = None,
    formula_status: str | None = None,
    selected_filters: dict[str, Any] | None = None,
    source_provenance: list[str] | None = None,
    target_response_ids: set[int] | None = None,
) -> AnalyticsContractContext:
    competitor_ids = await _competitor_ids(session, project)
    missing_sources = list(base_missing_sources or [])
    missing_inputs = list(base_missing_inputs or [])
    missing_reasons = list(base_missing_reasons or [])
    scope_missing_reason: str | None = None
    if brand_id is not None and project.primary_brand_id is None:
        scope_missing_reason = MISSING_PROJECT_BRAND_BINDING_REASON
        missing_inputs.append("project.primary_brand_id")
        missing_sources.append("project.primary_brand_id")
        missing_reasons.extend([PROJECT_UNBOUND_REASON, MISSING_PROJECT_BRAND_BINDING_REASON])
        if not competitor_ids:
            missing_inputs.append("project_competitors.brand_id")
            missing_sources.append("project_competitors.brand_id")
    filters_payload: dict[str, Any] = {
        "project_id": project.id,
        "brand_id": brand_id,
        "date_range": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "competitor_brand_ids": competitor_ids,
    }
    if selected_filters:
        filters_payload.update(selected_filters)
    provenance = list(
        source_provenance
        or [
            "geo_score_daily",
            "brand_mentions",
            "response_analyses",
            "citation_sources",
        ]
    )

    if brand_id is None:
        missing_sources.append("project.primary_brand_id")
        missing_inputs.append("project.primary_brand_id")
        reason = "no_primary_brand"
        return AnalyticsContractContext(
            project_scope=ProjectScope(
                exists=True,
                project_id=project.id,
                primary_brand_id=project.primary_brand_id,
                requested_brand_id=None,
                competitor_brand_ids=competitor_ids,
                missing_reason=reason,
            ),
            state="empty",
            state_reason=reason,
            state_detail="Project has no primary brand configured.",
            missing_inputs=_unique(missing_inputs),
            missing_sources=_unique(missing_sources),
            missing_reasons=_unique(missing_reasons or [reason]),
            evidence_counts=_empty_evidence(competitor_ids),
            formula_diagnostics=formula_diagnostics_for(FORMULA_NO_EVIDENCE_STATUS),
            formula_status=FORMULA_NO_EVIDENCE_STATUS,
            selected_filters=filters_payload,
            source_provenance=provenance,
        )

    from_dt = datetime.combine(from_date, datetime.min.time())
    to_dt = datetime.combine(to_date, datetime.max.time())
    brand_filter = await brand_mention_match_condition(session, brand_id)

    geo_rows = int(
        (
            await session.execute(
                select(func.count(GeoScoreDaily.id)).where(
                    and_(
                        GeoScoreDaily.brand_id == brand_id,
                        GeoScoreDaily.date >= from_dt,
                        GeoScoreDaily.date <= to_dt,
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    eligible_response_count = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(GeoScoreDaily.total_queries), 0)).where(
                    and_(
                        GeoScoreDaily.brand_id == brand_id,
                        GeoScoreDaily.date >= from_dt,
                        GeoScoreDaily.date <= to_dt,
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    mention_row = (
        await session.execute(
            select(
                func.count(BrandMention.id),
                func.count(func.distinct(BrandMention.response_id)),
                func.coalesce(func.sum(func.coalesce(BrandMention.mention_count, 1)), 0),
            ).where(
                and_(
                    brand_filter,
                    BrandMention.created_at >= from_dt,
                    BrandMention.created_at <= to_dt,
                )
            )
        )
    ).one()
    mention_count = int(mention_row[0] or 0)
    mentioned_response_count = int(mention_row[1] or 0)
    normalized_mentions = int(mention_row[2] or 0)

    has_admin_chain = all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
        ]
    )
    target_response_ids = (
        set(target_response_ids)
        if target_response_ids is not None
        else await _project_eligible_response_ids(
            session,
            project,
            brand_id,
            from_date=from_date,
            to_date=to_date,
            from_dt=from_dt,
            to_dt=to_dt,
        )
    )
    analysis_rows = (
        await session.execute(
            select(ResponseAnalysis.raw_analysis_json).where(
                ResponseAnalysis.response_id.in_(target_response_ids)
            )
        )
    ).all()
    admin_fact_response_count = len(target_response_ids)
    target_mention_count = 0
    target_citation_count = 0
    if target_response_ids:
        target_mention_count = int(
            (
                await session.execute(
                    select(func.count(BrandMention.id)).where(
                        and_(
                            brand_filter,
                            BrandMention.response_id.in_(target_response_ids),
                        )
                    )
                )
            ).scalar_one()
            or 0
        )
        target_citation_count = int(
            (
                await session.execute(
                    select(func.count(CitationSource.id))
                    .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                    .where(
                        and_(
                            brand_filter,
                            BrandMention.response_id.in_(target_response_ids),
                        )
                    )
                )
            ).scalar_one()
            or 0
        )

    repair_count = 0
    owner_brand_ids: set[int] = set()
    repair_missing: list[str] = []
    for row in analysis_rows:
        for repair in _repair_entries(row[0]):
            repair_brand_id = repair.get("brand_id")
            if repair_brand_id is not None and int(repair_brand_id) != brand_id:
                continue
            repair_count += 1
            owner_id = repair.get("owner_brand_id")
            if owner_id is not None:
                owner_brand_ids.add(int(owner_id))
            sources = repair.get("missing_sources")
            if isinstance(sources, list):
                repair_missing.extend(str(source) for source in sources if source)
            if repair.get("state") and str(repair.get("state")).lower() != "ok":
                repair_missing.append("canonical_alias_repair.partial")

    citation_count = int(
        (
            await session.execute(
                select(func.count(CitationSource.id))
                .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(
                    and_(
                        brand_filter,
                        CitationSource.created_at >= from_dt,
                        CitationSource.created_at <= to_dt,
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    raw_response_without_app_facts = (
        has_admin_chain
        and admin_fact_response_count > 0
        and (project.primary_brand_id is None or project.primary_brand_id == brand_id)
        and len(analysis_rows) == 0
        and target_mention_count == 0
        and target_citation_count == 0
    )
    analysis_missing = raw_response_without_app_facts
    no_aggregate_rows = raw_response_without_app_facts and geo_rows == 0
    if analysis_missing:
        missing_inputs.extend(
            ["response_analyses", ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE]
        )
        missing_sources.extend(
            ["response_analyses", ANALYZER_FACT_PACKAGE_V3_SOURCE, ANALYZER_FACT_PACKAGE_SOURCE]
        )
        missing_reasons.append(ANALYSIS_MISSING_REASON)
    if no_aggregate_rows:
        missing_inputs.append("geo_score_daily")
        missing_sources.append("geo_score_daily")
        missing_reasons.append(NO_AGGREGATE_ROWS_REASON)

    aliases = sorted(await brand_mention_names(session, brand_id))
    name_value = func.lower(func.trim(BrandMention.brand_name))
    name_only_competitor_conditions = [
        BrandMention.brand_id.is_(None),
        BrandMention.brand_name.isnot(None),
        name_value != "",
    ]
    if aliases:
        name_only_competitor_conditions.append(~name_value.in_(aliases))

    competitive_mention_count = int(
        (
            await session.execute(
                select(func.count(BrandMention.id)).where(
                    and_(
                        or_(
                            and_(
                                BrandMention.brand_id.isnot(None),
                                BrandMention.brand_id != brand_id,
                            ),
                            and_(*name_only_competitor_conditions),
                        ),
                        BrandMention.created_at >= from_dt,
                        BrandMention.created_at <= to_dt,
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    if repair_missing:
        missing_inputs.extend(repair_missing)
        missing_sources.extend(repair_missing)
        missing_reasons.append("canonical alias repair has partial analyzer evidence")

    if scope_missing_reason is not None:
        state = "empty"
        state_reason = scope_missing_reason
    elif repair_missing:
        state = "partial"
        state_reason = "partial_analyzer_data"
    elif analysis_missing:
        state = "partial"
        state_reason = ANALYSIS_MISSING_REASON
    elif no_aggregate_rows and not has_data:
        state = "partial"
        state_reason = NO_AGGREGATE_ROWS_REASON
    elif not has_data or base_state == "empty":
        state = "empty"
        state_reason = base_state_reason or "no_metric_data"
    elif base_state == "partial":
        state = "partial"
        state_reason = base_state_reason or "partial_data"
    else:
        state = "ok"
        state_reason = base_state_reason or "data_available"

    evidence_counts = {
        "geo_score_daily_rows": geo_rows,
        "brand_mention_count": mention_count,
        "brand_mentioned_response_count": mentioned_response_count,
        "normalized_brand_mention_count": normalized_mentions,
        "response_analysis_count": len(analysis_rows),
        "citation_source_count": citation_count,
        "competitor_brand_count": len(competitor_ids),
        "eligible_response_count": eligible_response_count,
        "admin_fact_response_count": admin_fact_response_count,
        "competitive_mention_count": competitive_mention_count,
        "canonical_alias_repair_count": repair_count,
    }
    has_any_evidence = has_data or any(
        count > 0
        for key, count in evidence_counts.items()
        if key
        in {
            "geo_score_daily_rows",
            "brand_mention_count",
            "brand_mentioned_response_count",
            "normalized_brand_mention_count",
            "response_analysis_count",
            "citation_source_count",
            "admin_fact_response_count",
        }
    )

    requires_geo_denominator = "geo_score_daily" in provenance
    if has_any_evidence and requires_geo_denominator and eligible_response_count <= 0:
        missing_inputs.append("eligible_response_denominator")
        missing_sources.append("eligible_response_denominator")
        if geo_rows:
            missing_inputs.append("geo_score_daily.total_queries")
            missing_sources.append("geo_score_daily.total_queries")
    if has_any_evidence and normalized_mentions > 0 and competitive_mention_count <= 0:
        missing_inputs.append("brand_mentions.competitive_set")
        missing_sources.append("brand_mentions.competitive_set")

    metric_formula_evidence, analyzer_counts, analyzer_reason_codes = await _analyzer_fact_rollup(
        session,
        brand_id=brand_id,
        from_date=from_date,
        to_date=to_date,
        target_response_ids=target_response_ids,
    )
    if has_admin_chain and not metric_formula_evidence and admin_fact_response_count > 0:
        package_sources = _package_source_tables()
        missing_inputs.extend(package_sources)
        missing_sources.extend(package_sources)
        missing_reasons.append("missing_analyzer_fact_packages")
        metric_formula_evidence = _blocking_metric_evidence(
            ["missing_analyzer_fact_packages"],
            source_tables=package_sources,
            sample_response_ids=sorted(target_response_ids),
        )
        for evidence in metric_formula_evidence.values():
            evidence["formula_status"] = FORMULA_PARTIAL_STATUS
    if metric_formula_evidence:
        analyzer_source_tables = _evidence_source_tables(metric_formula_evidence)
        evidence_counts.update(analyzer_counts)
        missing_reasons.extend(analyzer_reason_codes)
        missing_inputs.extend(analyzer_reason_codes)
        missing_sources.extend(analyzer_source_tables)
        provenance.extend(analyzer_source_tables)
    blocking_reasons = [
        reason
        for reason in [
            scope_missing_reason,
            ANALYSIS_MISSING_REASON if analysis_missing else None,
            NO_AGGREGATE_ROWS_REASON if no_aggregate_rows else None,
        ]
        if reason
    ]
    if scope_missing_reason:
        blocking_reasons.insert(0, PROJECT_UNBOUND_REASON)
    if blocking_reasons:
        metric_formula_evidence = {
            **metric_formula_evidence,
            **_blocking_metric_evidence(
                blocking_reasons,
                source_tables=_unique(
                    [
                        "projects.primary_brand_id" if scope_missing_reason else "",
                        "project_competitors"
                        if scope_missing_reason and not competitor_ids
                        else "",
                        "response_analyses" if analysis_missing else "",
                        "geo_score_daily" if no_aggregate_rows else "",
                    ]
                ),
                sample_response_ids=sorted(target_response_ids),
            ),
        }

    resolved_formula_status = formula_status
    if resolved_formula_status is None:
        if not has_any_evidence:
            resolved_formula_status = FORMULA_NO_EVIDENCE_STATUS
        elif missing_inputs:
            resolved_formula_status = FORMULA_MISSING_INPUTS_STATUS
        else:
            resolved_formula_status = FORMULA_OK_STATUS

    if metric_formula_evidence:
        metric_statuses = [
            str(evidence.get("formula_status") or FORMULA_NO_EVIDENCE_STATUS)
            for evidence in metric_formula_evidence.values()
        ]
        metric_reason_codes = {
            str(reason)
            for evidence in metric_formula_evidence.values()
            for reason in evidence.get("reason_codes", [])
            if reason
        }
        if metric_reason_codes & _BLOCKING_REASON_CODES:
            resolved_formula_status = FORMULA_MISSING_INPUTS_STATUS
        elif any(status != FORMULA_OK_STATUS for status in metric_statuses):
            resolved_formula_status = FORMULA_PARTIAL_STATUS

    if resolved_formula_status == FORMULA_MISSING_INPUTS_STATUS and not missing_reasons:
        missing_reasons.append("required formula inputs are missing")
    if (
        resolved_formula_status == FORMULA_PENDING_STATUS
        and FORMULA_PENDING_SOURCE not in missing_sources
    ):
        missing_sources.append(FORMULA_PENDING_SOURCE)
    if resolved_formula_status != FORMULA_OK_STATUS:
        if scope_missing_reason is not None:
            state = "empty"
            state_reason = scope_missing_reason
        elif has_any_evidence:
            state = "partial"
            if state_reason in {"data_available", "no_metric_data"}:
                state_reason = (
                    "missing_formula_inputs"
                    if resolved_formula_status == FORMULA_MISSING_INPUTS_STATUS
                    else "partial_analyzer_data"
                    if resolved_formula_status == FORMULA_PARTIAL_STATUS
                    else "formula_pending_upstream"
                )
        else:
            state = "empty"
            state_reason = base_state_reason or "no_metric_data"

    return AnalyticsContractContext(
        project_scope=ProjectScope(
            exists=True,
            project_id=project.id,
            primary_brand_id=project.primary_brand_id,
            requested_brand_id=brand_id,
            competitor_brand_ids=competitor_ids,
            missing_reason=scope_missing_reason,
        ),
        brand_aliases=aliases,
        state=state,
        state_reason=state_reason,
        state_detail=(
            "Project is not bound to the requested brand; configure project.primary_brand_id "
            "before accepting App analytics metrics."
            if scope_missing_reason
            else None
            if state != "partial"
            else "Some analyzer evidence is partial."
        ),
        missing_inputs=_unique(missing_inputs),
        missing_sources=_unique(missing_sources),
        missing_reasons=_unique(missing_reasons),
        evidence_counts=evidence_counts,
        identity_diagnostics=IdentityDiagnostics(
            canonical_brand_id=brand_id,
            normalized_brand_mention_count=normalized_mentions,
            brand_mentioned_response_count=mentioned_response_count,
            response_analysis_count=len(analysis_rows),
            canonical_alias_repair_count=repair_count,
            raw_text_owner_brand_ids=sorted(owner_brand_ids),
            repair_missing_sources=_unique(repair_missing),
        ),
        formula_diagnostics=formula_diagnostics_for(
            resolved_formula_status,
            missing_inputs=_unique(missing_inputs),
        ),
        formula_status=resolved_formula_status,
        metric_formula_evidence=metric_formula_evidence,
        selected_filters=filters_payload,
        source_provenance=provenance,
    )


def _empty_evidence(competitor_ids: list[int]) -> dict[str, int]:
    return {
        "geo_score_daily_rows": 0,
        "brand_mention_count": 0,
        "brand_mentioned_response_count": 0,
        "normalized_brand_mention_count": 0,
        "response_analysis_count": 0,
        "citation_source_count": 0,
        "competitor_brand_count": len(competitor_ids),
        "eligible_response_count": 0,
        "admin_fact_response_count": 0,
        "competitive_mention_count": 0,
        "canonical_alias_repair_count": 0,
    }


def context_dump(context: AnalyticsContractContext) -> dict[str, Any]:
    return context.model_dump()


def context_update(context: AnalyticsContractContext) -> dict[str, Any]:
    return {name: getattr(context, name) for name in AnalyticsContractContext.model_fields}
