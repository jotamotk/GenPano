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

    resolved_formula_status = formula_status
    if resolved_formula_status is None:
        if not has_any_evidence:
            resolved_formula_status = FORMULA_NO_EVIDENCE_STATUS
        elif missing_inputs:
            resolved_formula_status = FORMULA_MISSING_INPUTS_STATUS
        else:
            resolved_formula_status = FORMULA_OK_STATUS

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
