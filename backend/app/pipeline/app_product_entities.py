"""Evidence-gated product entity extraction for App analytics backfills."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from genpano_models import BrandMention, ProductScoreDaily, ResponseAnalysis
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._topic_analysis_service import legacy_table_columns, legacy_table_exists

ESTEE_LAUDER_PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "Advanced Night Repair": (
        "advanced night repair",
        "advanced night repair serum",
        "小棕瓶",
        "第七代小棕瓶",
    ),
    "Double Wear": (
        "double wear",
        "double wear foundation",
        "持妆粉底",
        "dw粉底",
    ),
    "Micro Essence": (
        "micro essence",
        "micro essence treatment lotion",
        "微精华",
        "樱花水",
    ),
    "Re-Nutriv": (
        "re-nutriv",
        "renutriv",
        "白金级",
        "白金黑钻",
    ),
}

_SPACE_RE = re.compile(r"\s+")
_EDGE_RE = re.compile(r"^[\s\"',.:;()\[\]]+|[\s\"',.:;()\[\]]+$")
_GENERIC_PRODUCT_VALUES = {
    "",
    "brand",
    "beauty",
    "product",
    "products",
    "serum",
    "cream",
    "foundation",
    "雅诗兰黛",
    "estee lauder",
    "estée lauder",
}


@dataclass(frozen=True)
class ProductEntityBackfillConfig:
    canonical_brand_id: int
    source_brand_ids: tuple[int, ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    product_aliases: dict[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class ProductEntityBackfillResult:
    scanned_responses: int
    evidence_responses: int
    product_names: list[str]
    brand_mentions_updated: int
    product_score_rows_upserted: int
    dry_run: bool


@dataclass(frozen=True)
class _ResponseRow:
    response_id: int
    response_date: datetime
    target_llm: str
    intent: str | None
    evidence_text: str


@dataclass(frozen=True)
class _ProductEvidence:
    response_id: int
    response_date: datetime
    target_llm: str
    intent: str | None
    product_name: str
    position_rank: int | None
    sentiment_score: float | None
    geo_score: float | None


def normalize_product_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = _EDGE_RE.sub("", _SPACE_RE.sub(" ", value).strip())
    if not name or len(name) > 256:
        return None
    if name.casefold() in _GENERIC_PRODUCT_VALUES:
        return None
    return name


def _contains_alias(text_value: str, alias: str) -> bool:
    if not alias:
        return False
    text_folded = text_value.casefold()
    alias_folded = alias.casefold()
    if re.fullmatch(r"[a-z0-9][a-z0-9 .&+-]*", alias_folded):
        pattern = r"(?<![a-z0-9])" + re.escape(alias_folded) + r"(?![a-z0-9])"
        return re.search(pattern, text_folded) is not None
    return alias_folded in text_folded


def extract_product_names(
    evidence_text: str,
    product_aliases: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    aliases = product_aliases or ESTEE_LAUDER_PRODUCT_ALIASES
    found: list[str] = []
    seen: set[str] = set()
    for canonical_name, alias_values in aliases.items():
        if _contains_alias(evidence_text, canonical_name) or any(
            _contains_alias(evidence_text, alias) for alias in alias_values
        ):
            normalized = normalize_product_name(canonical_name)
            if normalized and normalized not in seen:
                found.append(normalized)
                seen.add(normalized)
    return found


async def _load_response_rows(
    session: AsyncSession,
    config: ProductEntityBackfillConfig,
) -> list[_ResponseRow]:
    required_tables = ("queries", "llm_responses")
    if not all([await legacy_table_exists(session, table) for table in required_tables]):
        return []

    query_cols = await legacy_table_columns(session, "queries")
    response_cols = await legacy_table_columns(session, "llm_responses")
    prompt_cols = await legacy_table_columns(session, "prompts")
    topic_cols = await legacy_table_columns(session, "topics")

    if "id" not in response_cols or "query_id" not in response_cols or "id" not in query_cols:
        return []

    response_text_cols = [
        col for col in ("raw_text", "content", "answer", "response_text") if col in response_cols
    ]
    query_text_cols = [col for col in ("query_text", "text") if col in query_cols]
    prompt_text_cols = [col for col in ("text", "prompt_text") if col in prompt_cols]
    topic_text_cols = [col for col in ("text", "title", "name") if col in topic_cols]

    text_parts = [f"r.{col}" for col in response_text_cols]
    text_parts.extend(f"q.{col}" for col in query_text_cols)
    text_parts.extend(f"p.{col}" for col in prompt_text_cols)
    text_parts.extend(f"t.{col}" for col in topic_text_cols)
    evidence_expr = " || ' ' || ".join(f"COALESCE({part}, '')" for part in text_parts) or "''"

    target_llm_expr = (
        "COALESCE(NULLIF(r.target_llm, ''), NULLIF(q.target_llm, ''), 'unknown')"
        if "target_llm" in response_cols and "target_llm" in query_cols
        else "COALESCE(NULLIF(q.target_llm, ''), 'unknown')"
        if "target_llm" in query_cols
        else "COALESCE(NULLIF(r.target_llm, ''), 'unknown')"
        if "target_llm" in response_cols
        else "'unknown'"
    )
    intent_expr = (
        "COALESCE(NULLIF(r.intent, ''), NULLIF(p.intent, ''), NULLIF(q.intent, ''))"
        if "intent" in response_cols and "intent" in prompt_cols and "intent" in query_cols
        else "COALESCE(NULLIF(r.intent, ''), NULLIF(p.intent, ''))"
        if "intent" in response_cols and "intent" in prompt_cols
        else "NULL"
    )

    date_candidates = []
    for alias, cols in (("r", response_cols), ("q", query_cols)):
        for col in ("collected_at", "finished_at", "created_at"):
            if col in cols:
                date_candidates.append(f"{alias}.{col}")
    date_expr = (
        f"COALESCE({', '.join(date_candidates)})" if date_candidates else "CURRENT_TIMESTAMP"
    )

    joins = ["JOIN queries q ON q.id = r.query_id"]
    if await legacy_table_exists(session, "prompts") and "prompt_id" in response_cols:
        joins.append("LEFT JOIN prompts p ON p.id = r.prompt_id")
    elif await legacy_table_exists(session, "prompts") and "prompt_id" in query_cols:
        joins.append("LEFT JOIN prompts p ON p.id = q.prompt_id")
    else:
        joins.append("LEFT JOIN (SELECT NULL AS id) p ON 1 = 0")

    if await legacy_table_exists(session, "topics") and "topic_id" in prompt_cols:
        joins.append("LEFT JOIN topics t ON t.id = p.topic_id")
    else:
        joins.append("LEFT JOIN (SELECT NULL AS id) t ON 1 = 0")

    scope_ids = (config.canonical_brand_id, *config.source_brand_ids)
    params: dict[str, Any] = {}
    placeholders: list[str] = []
    for idx, brand_id in enumerate(dict.fromkeys(scope_ids)):
        key = f"brand_id_{idx}"
        params[key] = brand_id
        placeholders.append(f":{key}")

    scope_conditions: list[str] = []
    if "brand_id" in query_cols:
        scope_conditions.append(f"q.brand_id IN ({', '.join(placeholders)})")
    if "brand_id" in topic_cols:
        scope_conditions.append(f"t.brand_id IN ({', '.join(placeholders)})")
    where = [f"({' OR '.join(scope_conditions)})"] if scope_conditions else ["1 = 1"]
    if config.date_from is not None:
        params["date_from"] = datetime.combine(config.date_from, time.min)
        where.append(f"{date_expr} >= :date_from")
    if config.date_to is not None:
        params["date_to"] = datetime.combine(config.date_to, time.max)
        where.append(f"{date_expr} <= :date_to")

    sql = text(
        f"""
        SELECT
          r.id AS response_id,
          {date_expr} AS response_date,
          {target_llm_expr} AS target_llm,
          {intent_expr} AS intent,
          {evidence_expr} AS evidence_text
        FROM llm_responses r
        {' '.join(joins)}
        WHERE {' AND '.join(where)}
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()

    response_rows: list[_ResponseRow] = []
    for row in rows:
        response_id = row.get("response_id")
        if response_id is None:
            continue
        response_date_raw = row.get("response_date")
        response_date = response_date_raw if isinstance(response_date_raw, datetime) else None
        if response_date is None and isinstance(response_date_raw, str):
            response_date = datetime.fromisoformat(
                response_date_raw.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        response_rows.append(
            _ResponseRow(
                response_id=int(response_id),
                response_date=response_date or datetime.now(),
                target_llm=str(row.get("target_llm") or "unknown"),
                intent=str(row.get("intent")) if row.get("intent") else None,
                evidence_text=str(row.get("evidence_text") or ""),
            )
        )
    return response_rows


async def _load_mentions(
    session: AsyncSession,
    response_ids: set[int],
    canonical_brand_id: int,
) -> dict[int, list[BrandMention]]:
    if not response_ids:
        return {}
    rows = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id.in_(sorted(response_ids)))
        )
    ).scalars().all()
    grouped: dict[int, list[BrandMention]] = defaultdict(list)
    for row in rows:
        if row.response_id is not None:
            grouped[int(row.response_id)].append(row)
    return grouped


async def _load_analyses(
    session: AsyncSession,
    response_ids: set[int],
) -> dict[int, ResponseAnalysis]:
    if not response_ids:
        return {}
    rows = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id.in_(sorted(response_ids)))
        )
    ).scalars().all()
    return {int(row.response_id): row for row in rows if row.response_id is not None}


def _direct_product_names(mentions: list[BrandMention]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for mention in mentions:
        normalized = normalize_product_name(mention.product_name)
        if normalized and normalized not in seen:
            found.append(normalized)
            seen.add(normalized)
    return found


def _best_mention_values(
    mentions: list[BrandMention],
    canonical_brand_id: int,
) -> tuple[int | None, float | None]:
    candidates = [
        mention
        for mention in mentions
        if mention.brand_id == canonical_brand_id or str(mention.brand_name or "").strip()
    ]
    ranks = [mention.position_rank for mention in candidates if mention.position_rank is not None]
    sentiments = [
        float(mention.sentiment_score)
        for mention in candidates
        if mention.sentiment_score is not None
    ]
    return (
        min(ranks) if ranks else None,
        round(sum(sentiments) / len(sentiments), 4) if sentiments else None,
    )


def _analysis_scores(analysis: ResponseAnalysis | None) -> tuple[float | None, float | None]:
    if analysis is None:
        return None, None
    sentiment = float(analysis.sentiment_score) if analysis.sentiment_score is not None else None
    geo = float(analysis.geo_score) if analysis.geo_score is not None else None
    if geo is not None and 0 <= geo <= 1:
        geo = round(geo * 100, 4)
    return sentiment, geo


def _collect_evidence(
    responses: list[_ResponseRow],
    mentions_by_response: dict[int, list[BrandMention]],
    analyses_by_response: dict[int, ResponseAnalysis],
    config: ProductEntityBackfillConfig,
) -> list[_ProductEvidence]:
    evidence: list[_ProductEvidence] = []
    for response in responses:
        mentions = mentions_by_response.get(response.response_id, [])
        product_names = [
            *_direct_product_names(mentions),
            *extract_product_names(response.evidence_text, config.product_aliases),
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for product_name in product_names:
            if product_name not in seen:
                deduped.append(product_name)
                seen.add(product_name)
        if not deduped:
            continue
        rank, mention_sentiment = _best_mention_values(mentions, config.canonical_brand_id)
        analysis_sentiment, geo_score = _analysis_scores(
            analyses_by_response.get(response.response_id)
        )
        for product_name in deduped:
            evidence.append(
                _ProductEvidence(
                    response_id=response.response_id,
                    response_date=datetime.combine(response.response_date.date(), time.min),
                    target_llm=response.target_llm or "unknown",
                    intent=response.intent,
                    product_name=product_name,
                    position_rank=rank,
                    sentiment_score=(
                        mention_sentiment
                        if mention_sentiment is not None
                        else analysis_sentiment
                    ),
                    geo_score=geo_score,
                )
            )
    return evidence


async def _update_brand_mentions(
    session: AsyncSession,
    evidence: list[_ProductEvidence],
    canonical_brand_id: int,
    *,
    dry_run: bool,
) -> int:
    product_by_response: dict[int, str] = {}
    for item in evidence:
        product_by_response.setdefault(item.response_id, item.product_name)
    if not product_by_response:
        return 0
    mentions = (
        await session.execute(
            select(BrandMention).where(
                and_(
                    BrandMention.response_id.in_(sorted(product_by_response)),
                    BrandMention.brand_id == canonical_brand_id,
                )
            )
        )
    ).scalars().all()
    updated = 0
    for mention in mentions:
        product_name = product_by_response.get(int(mention.response_id))
        if product_name and not normalize_product_name(mention.product_name):
            updated += 1
            if not dry_run:
                mention.product_name = product_name
    return updated


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


async def _upsert_product_scores(
    session: AsyncSession,
    evidence: list[_ProductEvidence],
    denominators: dict[tuple[datetime, str], int],
    canonical_brand_id: int,
    *,
    dry_run: bool,
) -> int:
    grouped: dict[tuple[str, datetime, str], list[_ProductEvidence]] = defaultdict(list)
    for item in evidence:
        grouped[(item.product_name, item.response_date, item.target_llm)].append(item)

    upserts = 0
    for (product_name, response_date, target_llm), items in sorted(grouped.items()):
        denominator = denominators.get((response_date, target_llm), 0)
        response_count = len({item.response_id for item in items})
        ranks = [float(item.position_rank) for item in items if item.position_rank is not None]
        sentiments = [item.sentiment_score for item in items if item.sentiment_score is not None]
        geo_scores = [item.geo_score for item in items if item.geo_score is not None]
        existing = (
            await session.execute(
                select(ProductScoreDaily).where(
                    and_(
                        ProductScoreDaily.brand_id == canonical_brand_id,
                        ProductScoreDaily.product_name == product_name,
                        ProductScoreDaily.date == response_date,
                        ProductScoreDaily.target_llm == target_llm,
                    )
                )
            )
        ).scalar_one_or_none()
        values = {
            "brand_id": canonical_brand_id,
            "product_name": product_name,
            "date": response_date,
            "target_llm": target_llm,
            "total_queries": denominator,
            "mention_count": response_count,
            "mention_rate": round(response_count / denominator, 4) if denominator else 0.0,
            "avg_position_rank": _avg(ranks),
            "first_place_count": sum(1 for rank in ranks if rank == 1),
            "first_place_rate": round(sum(1 for rank in ranks if rank == 1) / response_count, 4)
            if response_count
            else 0.0,
            "avg_sentiment_score": _avg(sentiments),
            "avg_geo_score": _avg(geo_scores),
            "updated_at": datetime.now(),
        }
        upserts += 1
        if dry_run:
            continue
        if existing is None:
            session.add(ProductScoreDaily(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    return upserts


def _denominators(responses: list[_ResponseRow]) -> dict[tuple[datetime, str], int]:
    grouped: dict[tuple[datetime, str], set[int]] = defaultdict(set)
    for response in responses:
        response_date = datetime.combine(response.response_date.date(), time.min)
        grouped[(response_date, response.target_llm or "unknown")].add(response.response_id)
    return {key: len(value) for key, value in grouped.items()}


async def backfill_product_entities(
    session: AsyncSession,
    *,
    config: ProductEntityBackfillConfig,
    dry_run: bool = True,
) -> ProductEntityBackfillResult:
    responses = await _load_response_rows(session, config)
    response_ids = {row.response_id for row in responses}
    mentions_by_response = await _load_mentions(session, response_ids, config.canonical_brand_id)
    analyses_by_response = await _load_analyses(session, response_ids)
    evidence = _collect_evidence(responses, mentions_by_response, analyses_by_response, config)

    updated_mentions = await _update_brand_mentions(
        session,
        evidence,
        config.canonical_brand_id,
        dry_run=dry_run,
    )
    score_upserts = await _upsert_product_scores(
        session,
        evidence,
        _denominators(responses),
        config.canonical_brand_id,
        dry_run=dry_run,
    )
    if not dry_run:
        await session.commit()

    product_names = sorted({item.product_name for item in evidence})
    return ProductEntityBackfillResult(
        scanned_responses=len(response_ids),
        evidence_responses=len({item.response_id for item in evidence}),
        product_names=product_names,
        brand_mentions_updated=updated_mentions,
        product_score_rows_upserted=score_upserts,
        dry_run=dry_run,
    )
