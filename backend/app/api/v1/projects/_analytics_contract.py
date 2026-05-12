"""Shared App analytics contract metadata for project-scoped endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
)
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._mention_rollups import brand_mention_match_condition, brand_mention_names

FORMULA_OK_STATUS = "ok"
FORMULA_PARTIAL_STATUS = "partial"
FORMULA_PENDING_STATUS = "formula_pending_upstream"
FORMULA_MISSING_INPUTS_STATUS = "missing_required_inputs"
FORMULA_NO_EVIDENCE_STATUS = "no_evidence"
FORMULA_PENDING_SOURCE = "upstream_formula_provenance"


class ValueRange(BaseModel):
    min: float
    max: float


class DataFreshness(BaseModel):
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


class ProjectScope(BaseModel):
    exists: bool = True
    project_id: str
    primary_brand_id: int | None
    requested_brand_id: int | None
    competitor_brand_ids: list[int] = Field(default_factory=list)
    missing_reason: str | None = None


class MetricDefinition(BaseModel):
    metric_key: str
    unit: str
    value_scale: str
    value_range: ValueRange
    denominator_label: str | None = None
    numerator_label: str | None = None
    source: str | None = None
    formula_status: str | None = None


class MetricValue(BaseModel):
    value: float | None
    unit: str
    value_scale: str
    value_range: ValueRange
    source: str | None = None
    formula_status: str | None = None


class FormulaDiagnostics(BaseModel):
    status: str = "not_applicable"
    pending_sources: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class IdentityDiagnostics(BaseModel):
    canonical_brand_id: int | None = None
    normalized_brand_mention_count: int = 0
    brand_mentioned_response_count: int = 0
    response_analysis_count: int = 0
    canonical_alias_repair_count: int = 0
    raw_text_owner_brand_ids: list[int] = Field(default_factory=list)
    repair_missing_sources: list[str] = Field(default_factory=list)


class AnalyticsContractContext(BaseModel):
    project_scope: ProjectScope
    brand_aliases: list[str] = Field(default_factory=list)
    state: str
    state_reason: str
    state_detail: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    formula_status: str = FORMULA_NO_EVIDENCE_STATUS
    metric_formula_evidence: dict[str, Any] = Field(default_factory=dict)
    selected_filters: dict[str, Any] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def ratio_decimal(value: float | int | None) -> float | None:
    """Normalize ratio-like values to 0..1.

    Legacy aggregate rows may already store percent-like values such as 38.4.
    The project APIs expose ratio series as decimals, so those are converted to
    0.384 while existing decimal rows remain unchanged.
    """
    if value is None:
        return None
    raw = float(value)
    if abs(raw) > 1.0 and abs(raw) <= 100.0:
        raw = raw / 100.0
    return round(raw, 4)


def percent_display(value: float | int | None) -> float:
    if value is None:
        return 0.0
    raw = float(value)
    if abs(raw) > 100.0 and abs(raw) <= 10000.0:
        raw = raw / 100.0
    decimal = ratio_decimal(raw)
    if decimal is None:
        return 0.0
    return round(decimal * 100.0, 1)


def score_0_100(value: float | int | None) -> float | None:
    if value is None:
        return None
    raw = float(value)
    if 0.0 <= raw <= 1.0:
        raw *= 100.0
    return round(raw, 2)


def metric_definition(metric_key: str, *, display_percent: bool = False) -> MetricDefinition:
    source = "geo_score_daily"
    formula_status = FORMULA_OK_STATUS
    if metric_key in {"mention_rate", "avg_mention_rate"}:
        unit = "percent" if display_percent else "ratio"
        value_scale = "percent" if display_percent else "decimal"
        value_range = ValueRange(min=0.0, max=100.0 if display_percent else 1.0)
        return MetricDefinition(
            metric_key=metric_key,
            unit=unit,
            value_scale=value_scale,
            value_range=value_range,
            numerator_label="target brand mentioned eligible responses",
            denominator_label="eligible non-brand/category responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"sov", "avg_sov"}:
        unit = "percent" if display_percent else "ratio"
        value_scale = "percent" if display_percent else "decimal"
        value_range = ValueRange(min=0.0, max=100.0 if display_percent else 1.0)
        return MetricDefinition(
            metric_key=metric_key,
            unit=unit,
            value_scale=value_scale,
            value_range=value_range,
            numerator_label="target brand mentioned competitive-set responses",
            denominator_label="competitive-set brand-mentioned responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"citation", "citation_rate", "avg_citation_rate"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="ratio",
            value_scale="decimal",
            value_range=ValueRange(min=0.0, max=1.0),
            numerator_label="citation-backed brand mentions/responses",
            denominator_label="eligible brand mentions/responses",
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"geo_score", "avg_geo_score", "pano_score"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="score_0_100",
            value_range=ValueRange(min=0.0, max=100.0),
            source=source,
            formula_status=formula_status,
        )
    if metric_key in {"rank", "avg_position_rank"}:
        return MetricDefinition(
            metric_key=metric_key,
            unit="rank",
            value_scale="ordinal",
            value_range=ValueRange(min=1.0, max=1000.0),
            numerator_label="mentioned responses only",
            denominator_label="mentioned responses only",
            source=source,
            formula_status=formula_status,
        )
    if metric_key == "avg_sentiment":
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="score_0_100",
            value_range=ValueRange(min=0.0, max=100.0),
            source="geo_score_daily.avg_sentiment",
            formula_status=formula_status,
        )
    if metric_key == "sentiment":
        return MetricDefinition(
            metric_key=metric_key,
            unit="score",
            value_scale="raw_-1_1",
            value_range=ValueRange(min=-1.0, max=1.0),
            source="response_analyses.sentiment_score",
            formula_status=formula_status,
        )
    return MetricDefinition(
        metric_key=metric_key,
        unit="value",
        value_scale="raw",
        value_range=ValueRange(min=0.0, max=1.0),
        source=source,
        formula_status=formula_status,
    )


def metric_definitions(
    metric_keys: list[str],
    *,
    display_percent: bool = False,
) -> dict[str, MetricDefinition]:
    return {key: metric_definition(key, display_percent=display_percent) for key in metric_keys}


def formula_diagnostics_for(
    status: str,
    *,
    missing_inputs: list[str] | None = None,
) -> FormulaDiagnostics:
    if status == FORMULA_OK_STATUS:
        return FormulaDiagnostics(status=FORMULA_OK_STATUS)
    if status == FORMULA_NO_EVIDENCE_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_NO_EVIDENCE_STATUS,
            details=["No eligible evidence exists for the selected analytics filters."],
        )
    if status == FORMULA_MISSING_INPUTS_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_MISSING_INPUTS_STATUS,
            pending_sources=list(missing_inputs or []),
            details=["Required formula inputs are missing; metric values are withheld."],
        )
    if status == FORMULA_PARTIAL_STATUS:
        return FormulaDiagnostics(
            status=FORMULA_PARTIAL_STATUS,
            pending_sources=list(missing_inputs or []),
            details=[
                "Analyzer fact packages are present, but at least one metric has "
                "partial or missing formula proof."
            ],
        )
    return FormulaDiagnostics(
        status=FORMULA_PENDING_STATUS,
        pending_sources=[FORMULA_PENDING_SOURCE],
        details=[
            "Upstream aggregate provenance is pending review for PRD mention-rate "
            "and SoV denominators.",
            "Treat geo_score_daily ratio values as formula-pending until analyzer/data "
            "PRs are patched.",
        ],
    )


def _repair_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    repairs = payload.get("canonical_alias_repairs")
    if not isinstance(repairs, list):
        return []
    return [entry for entry in repairs if isinstance(entry, dict)]


def _as_package(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    packages = payload.get("analyzer_fact_packages")
    if not isinstance(packages, dict):
        return None
    if packages.get("version") != "issue_602_v1":
        return None
    return packages


def _status_from_package(package: dict[str, Any], key: str) -> str:
    value = package.get(key)
    if not isinstance(value, dict):
        return FORMULA_NO_EVIDENCE_STATUS
    return str(value.get("formula_status") or value.get("status") or FORMULA_NO_EVIDENCE_STATUS)


def _merge_status(current: str, candidate: str) -> str:
    order = {
        FORMULA_NO_EVIDENCE_STATUS: 0,
        FORMULA_OK_STATUS: 1,
        FORMULA_PARTIAL_STATUS: 2,
        FORMULA_MISSING_INPUTS_STATUS: 3,
    }
    if candidate == FORMULA_MISSING_INPUTS_STATUS:
        return candidate
    if current == FORMULA_MISSING_INPUTS_STATUS:
        return current
    if candidate == FORMULA_PARTIAL_STATUS or current == FORMULA_PARTIAL_STATUS:
        return FORMULA_PARTIAL_STATUS
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def _package_reason_codes(package: dict[str, Any], key: str) -> list[str]:
    value = package.get(key)
    if not isinstance(value, dict):
        return []
    reasons = value.get("reason_codes")
    if not isinstance(reasons, list):
        return []
    return [str(reason) for reason in reasons if reason]


def _package_response_ids(package: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    coverage = package.get("coverage")
    if isinstance(coverage, dict):
        for field in (
            "eligible_response_ids",
            "analyzed_response_ids",
            "missing_analyzer_response_ids",
            "failed_response_ids",
        ):
            values = coverage.get(field)
            if isinstance(values, list):
                ids.update(int(value) for value in values if value is not None)
    for key in ("sov", "sentiment", "citations"):
        value = package.get(key)
        if isinstance(value, dict) and isinstance(value.get("sample_response_ids"), list):
            ids.update(int(value) for value in value["sample_response_ids"] if value is not None)
    return ids


def _package_target_brand_id(package: dict[str, Any]) -> int | None:
    entities = package.get("entities")
    if isinstance(entities, dict) and entities.get("target_brand_id") is not None:
        return int(entities["target_brand_id"])
    return None


def _package_date_in_window(package: dict[str, Any], from_date: date, to_date: date) -> bool:
    coverage = package.get("coverage")
    if not isinstance(coverage, dict):
        return True
    chains = coverage.get("chains")
    if not isinstance(chains, list) or not chains:
        return True
    saw_date = False
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        raw = chain.get("collected_at")
        if not raw:
            continue
        try:
            collected = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        saw_date = True
        if from_date <= collected <= to_date:
            return True
    return not saw_date


def _metric_evidence_template(metric_key: str, status: str) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "formula_status": status,
        "reason_codes": [],
        "sample_response_ids": [],
    }


def _rollup_sov(packages: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = _metric_evidence_template("sov", FORMULA_NO_EVIDENCE_STATUS)
    numerator = 0
    denominator = 0
    competitors: list[dict[str, Any]] = []
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
        evidence["reason_codes"].extend(_package_reason_codes(package, "sov"))
        evidence["sample_response_ids"].extend(sov.get("sample_response_ids") or [])
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "numerator_name": "target_competitive_mentions",
            "denominator_name": "all_competitive_mentions",
            "numerator_count": numerator,
            "denominator_count": denominator,
            "competitor_count": len(
                {
                    (
                        item.get("brand_id"),
                        str(item.get("brand_name") or item.get("raw_name") or ""),
                    )
                    for item in competitors
                }
            ),
            "source_tables": ["response_analyses.raw_analysis_json.analyzer_fact_packages"],
            "fact_classes": ["sov", "entities"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
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
                "response_analyses.raw_analysis_json.analyzer_fact_packages",
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
                "response_analyses.raw_analysis_json.analyzer_fact_packages",
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
            "source_tables": ["response_analyses.raw_analysis_json.analyzer_fact_packages"],
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
        pano = package.get("pano_geo")
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
        evidence["reason_codes"].extend(_package_reason_codes(package, "pano_geo"))
    if packages and evidence["formula_status"] == FORMULA_NO_EVIDENCE_STATUS:
        evidence["formula_status"] = FORMULA_MISSING_INPUTS_STATUS
    evidence.update(
        {
            "component_readiness": readiness,
            "source_tables": ["response_analyses.raw_analysis_json.analyzer_fact_packages"],
            "fact_classes": ["pano_geo"],
        }
    )
    evidence["reason_codes"] = _unique(evidence["reason_codes"])
    return evidence


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


async def _analyzer_fact_rollup(
    session: AsyncSession,
    *,
    brand_id: int,
    from_date: date,
    to_date: date,
    target_response_ids: set[int],
) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    rows = (
        await session.execute(
            select(ResponseAnalysis.raw_analysis_json).where(
                ResponseAnalysis.raw_analysis_json.isnot(None)
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


def metric_missing_inputs(
    context: AnalyticsContractContext,
    metric_key: str | None,
) -> list[str]:
    evidence = metric_evidence_for(context, metric_key)
    if not evidence:
        return []
    status = str(evidence.get("formula_status") or FORMULA_NO_EVIDENCE_STATUS)
    if status == FORMULA_OK_STATUS:
        return []
    return _unique([str(reason) for reason in evidence.get("reason_codes", []) if reason])


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
) -> AnalyticsContractContext:
    competitor_ids = await _competitor_ids(session, project)
    missing_sources = list(base_missing_sources or [])
    missing_inputs = list(base_missing_inputs or [])
    missing_reasons = list(base_missing_reasons or [])
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

    response_ids = (
        select(BrandMention.response_id)
        .where(
            and_(
                brand_filter,
                BrandMention.created_at >= from_dt,
                BrandMention.created_at <= to_dt,
            )
        )
        .distinct()
    )
    target_response_ids = await _target_response_ids(
        session,
        brand_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    analysis_rows = (
        await session.execute(
            select(ResponseAnalysis.raw_analysis_json).where(
                ResponseAnalysis.response_id.in_(response_ids)
            )
        )
    ).all()

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

    if repair_missing:
        state = "partial"
        state_reason = "partial_analyzer_data"
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
        }
    )

    if has_any_evidence and eligible_response_count <= 0:
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
    if metric_formula_evidence:
        evidence_counts.update(analyzer_counts)
        missing_reasons.extend(analyzer_reason_codes)
        missing_inputs.extend(analyzer_reason_codes)
        missing_sources.append("response_analyses.raw_analysis_json.analyzer_fact_packages")
        provenance.append("response_analyses.raw_analysis_json.analyzer_fact_packages")

    resolved_formula_status = formula_status
    if resolved_formula_status is None:
        if not has_any_evidence:
            resolved_formula_status = FORMULA_NO_EVIDENCE_STATUS
        elif missing_inputs:
            resolved_formula_status = FORMULA_MISSING_INPUTS_STATUS
        else:
            resolved_formula_status = FORMULA_OK_STATUS

    if metric_formula_evidence and any(
        evidence.get("formula_status") != FORMULA_OK_STATUS
        for evidence in metric_formula_evidence.values()
    ):
        resolved_formula_status = FORMULA_PARTIAL_STATUS

    if resolved_formula_status == FORMULA_MISSING_INPUTS_STATUS and not missing_reasons:
        missing_reasons.append("required formula inputs are missing")
    if (
        resolved_formula_status == FORMULA_PENDING_STATUS
        and FORMULA_PENDING_SOURCE not in missing_sources
    ):
        missing_sources.append(FORMULA_PENDING_SOURCE)
    if resolved_formula_status != FORMULA_OK_STATUS:
        if has_any_evidence:
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
            missing_reason=None,
        ),
        brand_aliases=aliases,
        state=state,
        state_reason=state_reason,
        state_detail=None if state != "partial" else "Some analyzer evidence is partial.",
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
        "competitive_mention_count": 0,
        "canonical_alias_repair_count": 0,
    }


def context_dump(context: AnalyticsContractContext) -> dict[str, Any]:
    return context.model_dump()


def context_update(context: AnalyticsContractContext) -> dict[str, Any]:
    return {name: getattr(context, name) for name in AnalyticsContractContext.model_fields}
