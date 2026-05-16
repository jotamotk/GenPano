"""build_contract_context orchestrator and its supporting helpers.

Final phase of Stage A in splitting `_analytics_contract.py`
(Epic #885, design #888). Hosts the analyzer-fact rollup pipeline
(`_first_class_analyzer_fact_rollup`, `_analyzer_fact_rollup`,
`_latest_runs_by_response`, `_quality_flag_reasons_by_metric`,
`_competitor_ids`, `_empty_evidence`) and the 489-LOC
`build_contract_context` orchestrator itself plus the tiny
`context_dump` / `context_update` helpers.

Stage B will decompose `build_contract_context` into smaller phases
(normalize → validate → assemble → diagnostics) — out of scope here.
"""

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
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    SentimentDriver,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._mention_rollups import (
    brand_mention_match_condition,
    brand_mention_names,
)
from app.api.v1.projects._topic_analysis_service import legacy_table_exists
from app.api.v1.projects.contracts.constants import (
    _BLOCKING_REASON_CODES,
    _COMMON_METRIC_BLOCKING_REASONS,
    _METRIC_BLOCKING_REASONS,
    ANALYSIS_MISSING_REASON,
    ANALYZER_FACT_PACKAGE_SOURCE,
    ANALYZER_FACT_PACKAGE_V3_SOURCE,
    FORMULA_MISSING_INPUTS_STATUS,
    FORMULA_NO_EVIDENCE_STATUS,
    FORMULA_OK_STATUS,
    FORMULA_PARTIAL_STATUS,
    FORMULA_PENDING_SOURCE,
    FORMULA_PENDING_STATUS,
    MISSING_PROJECT_BRAND_BINDING_REASON,
    NO_AGGREGATE_ROWS_REASON,
    PROJECT_UNBOUND_REASON,
)
from app.api.v1.projects.contracts.definitions import formula_diagnostics_for
from app.api.v1.projects.contracts.evidence import (
    _blocking_metric_evidence,
    _evidence_source_tables,
    _metric_evidence_template,
    _package_source_tables,
)
from app.api.v1.projects.contracts.evidence import (
    _unique_str as _unique,
)
from app.api.v1.projects.contracts.models import (
    AnalyticsContractContext,
    IdentityDiagnostics,
    ProjectScope,
)
from app.api.v1.projects.contracts.package import (
    _as_package,
    _package_date_in_window,
    _package_response_ids,
    _package_target_brand_id,
    _repair_entries,
)
from app.api.v1.projects.contracts.queries import _project_eligible_response_ids
from app.api.v1.projects.contracts.rollups import (
    _rollup_citations,
    _rollup_coverage,
    _rollup_pano_geo,
    _rollup_sentiment,
    _rollup_sov,
    _rollup_topic_product,
    _rollup_trend_30d,
)


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
    # Issue #948 follow-up: the sentiment METRIC formula is
    # `brand_scoped_sentiment_score_sum / target_mentions_with_sentiment_score_and_label`,
    # whose inputs are `score_count` and `label_count`. Sentiment-driver
    # rows (and the `malformed_sentiment_driver_dropped` /
    # `unsupported_sentiment_driver_type_dropped` flags emitted by
    # `geo_tracker/analyzer/v4_contract.py`) are AUXILIARY evidence for the
    # driver-type "why" breakdown; they do NOT invalidate the metric value.
    # When the numerator + denominator inputs are present, downgrade to
    # `partial` so the frontend gate (`canUseContractMetricValue` after
    # PR #960) keeps rendering the sentiment KPI value. Mirrors the SoV /
    # GeoScore / MentionRate pattern in PR #953 / PR #960.
    sentiment_has_formula_inputs = score_count > 0 and label_count > 0
    sentiment_critical_reasons = {
        reason
        for reason in sentiment_reasons
        if reason in _METRIC_BLOCKING_REASONS["sentiment"]
        or reason in _COMMON_METRIC_BLOCKING_REASONS
    }
    if not sentiment_reasons:
        sentiment_status = FORMULA_OK_STATUS
    elif sentiment_has_formula_inputs and not sentiment_critical_reasons:
        sentiment_status = FORMULA_PARTIAL_STATUS
    else:
        sentiment_status = FORMULA_MISSING_INPUTS_STATUS

    citation_reasons = list(flag_reasons["citation"])
    if citation_total <= 0:
        citation_reasons.append("citation_sources")
        citation_reasons.append("citation_empty")
    elif attributed_citations <= 0:
        citation_reasons.append("citation_sources.mention_id")
        citation_reasons.append("unresolved_citation_attribution")
    if citation_total > 0 and fact_link_count <= 0:
        citation_reasons.append("unresolved_citation_attribution")
    # Issue #948 follow-up: the citation METRIC formula is
    # `target_attributed_citations / eligible_project_citations`. When the
    # numerator + denominator inputs are present (`citation_total > 0` AND
    # `attributed_citations > 0` AND `fact_link_count > 0`), analyzer-side
    # auxiliary flags like `citation_unlinked` / `malformed_citation_dropped`
    # / `evidence_quote_mismatch` should not invalidate the metric value —
    # they describe quality issues on OTHER citations in the same response,
    # not on the attributed ones. Downgrade to `partial` so the frontend
    # gate (`canUseContractMetricValue` after PR #960) keeps rendering the
    # citation share. Mirrors the SoV / MentionRate / GeoScore / Sentiment
    # patterns landed by PR #953, PR #962, and PR #976.
    citation_has_formula_inputs = (
        citation_total > 0 and attributed_citations > 0 and fact_link_count > 0
    )
    citation_critical_reasons = {
        reason
        for reason in citation_reasons
        if reason in _METRIC_BLOCKING_REASONS["citation"]
        or reason in _COMMON_METRIC_BLOCKING_REASONS
    }
    if not citation_reasons:
        citation_status = FORMULA_OK_STATUS
    elif citation_has_formula_inputs and not citation_critical_reasons:
        citation_status = FORMULA_PARTIAL_STATUS
    else:
        citation_status = FORMULA_MISSING_INPUTS_STATUS

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


async def _load_in_scope_packages(
    session: AsyncSession,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    target_response_ids: set[int],
) -> list[dict[str, Any]]:
    """Fetch analyzer fact packages for in-scope responses.

    Shared by the first-class and legacy rollup paths so both can surface
    package-derived evidence (e.g. `topic_product`, issue #1039) without
    duplicating the filter/scope logic.
    """
    if not target_response_ids:
        return []
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
    return packages


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
    packages = await _load_in_scope_packages(
        session,
        brand_id=brand_id,
        from_date=from_date,
        to_date=to_date,
        target_response_ids=target_response_ids,
    )
    if first_class[0]:
        # Issue #1039: the SQL-driven first-class rollup does not have a
        # native `topic_product` source yet, so surface it from the package
        # payload when available. Without this entry the frontend product
        # gate (`canUseMetricEvidence(data, 'product')`) keeps the products
        # page empty.
        metric_evidence, counts, reason_codes = first_class
        topic_product_evidence = _rollup_topic_product(packages) if packages else None
        if topic_product_evidence is not None:
            metric_evidence = {**metric_evidence, "topic_product": topic_product_evidence}
            counts = {
                **counts,
                "analyzer_topic_chain_count": int(
                    topic_product_evidence.get("topic_chain_count") or 0
                ),
                "analyzer_product_fact_count": int(
                    topic_product_evidence.get("product_fact_count") or 0
                ),
            }
            reason_codes = _unique(
                list(reason_codes) + list(topic_product_evidence.get("reason_codes") or [])
            )
        # Issue #1031: same omit-when-None pattern for `trend_30d` so the
        # frontend `canUseMetricEvidence(data, 'trend_30d')` gate
        # (BrandProductsPage.tsx:99) passes when the underlying packages
        # carry trend evidence — without it, every `p.trend = null` and
        # the BCG matrix drops every row.
        trend_30d_evidence = _rollup_trend_30d(packages) if packages else None
        if trend_30d_evidence is not None:
            metric_evidence = {**metric_evidence, "trend_30d": trend_30d_evidence}
            counts = {
                **counts,
                "analyzer_trend_30d_data_point_count": int(
                    trend_30d_evidence.get("data_point_count") or 0
                ),
                "analyzer_trend_30d_product_data_point_count": int(
                    trend_30d_evidence.get("product_data_point_count") or 0
                ),
            }
            reason_codes = _unique(
                list(reason_codes) + list(trend_30d_evidence.get("reason_codes") or [])
            )
        return metric_evidence, counts, reason_codes

    if not packages:
        return {}, {}, []

    metric_evidence = {
        "coverage": _rollup_coverage(packages, target_response_ids=target_response_ids),
        "sov": _rollup_sov(packages),
        "sentiment": _rollup_sentiment(packages),
        "citation": _rollup_citations(packages),
        "pano_geo": _rollup_pano_geo(packages),
    }
    # Issue #1039: include `topic_product` only when at least one package
    # carries it (older v3 / issue_602_v1 fixtures without the key keep
    # their pre-existing metric-evidence shape unchanged).
    topic_product_evidence = _rollup_topic_product(packages)
    if topic_product_evidence is not None:
        metric_evidence["topic_product"] = topic_product_evidence
    # Issue #1031: same omit-when-None semantics for `trend_30d` so older
    # fixtures without the per-package signal keep their pre-existing
    # metric-evidence shape unchanged (regression risk caught by
    # `test_issue_687_bestcoffer_app_api_contract`).
    trend_30d_evidence = _rollup_trend_30d(packages)
    if trend_30d_evidence is not None:
        metric_evidence["trend_30d"] = trend_30d_evidence
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
    if topic_product_evidence is not None:
        counts["analyzer_topic_chain_count"] = int(
            topic_product_evidence.get("topic_chain_count") or 0
        )
        counts["analyzer_product_fact_count"] = int(
            topic_product_evidence.get("product_fact_count") or 0
        )
    if trend_30d_evidence is not None:
        counts["analyzer_trend_30d_data_point_count"] = int(
            trend_30d_evidence.get("data_point_count") or 0
        )
        counts["analyzer_trend_30d_product_data_point_count"] = int(
            trend_30d_evidence.get("product_data_point_count") or 0
        )
    return metric_evidence, counts, reason_codes


async def _competitor_ids(session: AsyncSession, project: Project) -> list[int]:
    rows = (
        await session.execute(
            select(ProjectCompetitor.brand_id)
            .where(ProjectCompetitor.project_id == project.id)
            .order_by(ProjectCompetitor.brand_id)
        )
    ).all()
    return [int(row[0]) for row in rows if row[0] is not None]


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


def context_dump(context: AnalyticsContractContext) -> dict[str, Any]:
    return context.model_dump()


def context_update(context: AnalyticsContractContext) -> dict[str, Any]:
    return {name: getattr(context, name) for name in AnalyticsContractContext.model_fields}
