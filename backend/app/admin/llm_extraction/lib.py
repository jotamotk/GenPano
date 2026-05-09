"""LLM response extraction candidate storage and review helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from genpano_models import (
    BrandContextSnapshot,
    KgBrand,
    KGEntityAttribute,
    KGEntityClaim,
    KgProduct,
    KgRelationCandidate,
    LLMAttributeCandidate,
    LLMClaimCandidate,
    LLMEntityCandidate,
    Profile,
    Segment,
)
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ExtractionKind = Literal["entity", "attribute", "claim"]
VALID_STATUSES = {"pending", "approved", "rejected", "all"}
VALID_ENTITY_TYPES = {"brand", "product", "competitor", "segment", "profile", "scenario"}


class LLMExtractionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def normalize_text(value: Any, *, limit: int = 700) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def normalize_key_part(value: Any, *, limit: int = 220) -> str:
    return normalize_text(value, limit=limit).casefold()


def _clean_list(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    out: list[str] = []
    for item in raw:
        text_value = normalize_text(item, limit=300)
        if text_value and text_value not in out:
            out.append(text_value)
        if len(out) >= limit:
            break
    return out


def _source_notes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    notes = payload.get("source_notes")
    if not isinstance(notes, list):
        return []
    out: list[dict[str, Any]] = []
    for item in notes:
        if not isinstance(item, dict):
            continue
        title = normalize_text(item.get("title"), limit=180)
        url = normalize_text(item.get("url"), limit=500)
        snippet = normalize_text(item.get("snippet"), limit=320)
        source_type = normalize_text(item.get("source_type") or "web_search", limit=64)
        if title or url or snippet:
            out.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source_type": source_type,
                }
            )
    return out[:20]


def entity_candidate_key(
    *,
    entity_type: str,
    name: str,
    parent_brand_id: int | None = None,
    domain: str | None = None,
) -> str:
    parent = str(parent_brand_id or normalize_key_part(domain or "global"))
    return f"entity:{entity_type}:{normalize_key_part(name)}:{parent}"


def attribute_candidate_key(
    *,
    entity_kind: str,
    entity_id: str | None,
    entity_name: str,
    attribute_key: str,
    value: str,
) -> str:
    entity_ref = entity_id or normalize_key_part(entity_name)
    return (
        f"attribute:{entity_kind}:{entity_ref}:"
        f"{normalize_key_part(attribute_key)}:{normalize_key_part(value, limit=420)}"
    )


def claim_candidate_key(
    *,
    entity_kind: str,
    entity_id: str | None,
    entity_name: str,
    claim_type: str,
    text_value: str,
    scenario: str | None,
) -> str:
    entity_ref = entity_id or normalize_key_part(entity_name)
    return (
        f"claim:{entity_kind}:{entity_ref}:{normalize_key_part(claim_type)}:"
        f"{normalize_key_part(text_value, limit=520)}:{normalize_key_part(scenario or '')}"
    )


def _append_unique(out: list[dict[str, Any]], item: dict[str, Any]) -> None:
    key = item.get("candidate_key")
    if key and all(existing.get("candidate_key") != key for existing in out):
        out.append(item)


def _entity_item(
    *,
    brand_id: int | None,
    version: str | None,
    entity_type: str,
    name: str,
    parent_brand_id: int | None,
    parent_brand_name: str | None,
    domain: str | None,
    attributes: dict[str, Any] | None,
    source_notes: list[dict[str, Any]],
    confidence: float = 0.75,
) -> dict[str, Any] | None:
    clean_name = normalize_text(name, limit=256)
    if not clean_name or entity_type not in VALID_ENTITY_TYPES:
        return None
    return {
        "id": _new_uuid(),
        "brand_id": brand_id,
        "brand_context_version": version,
        "entity_type": entity_type,
        "name": clean_name,
        "normalized_name": normalize_key_part(clean_name, limit=256),
        "parent_brand_id": parent_brand_id,
        "parent_brand_name": parent_brand_name,
        "domain": domain,
        "candidate_key": entity_candidate_key(
            entity_type=entity_type,
            name=clean_name,
            parent_brand_id=parent_brand_id,
            domain=domain,
        ),
        "source": "llm_search",
        "confidence": confidence,
        "attributes_json": attributes or {},
        "evidence_json": {"source": "brand_context_pack"},
        "source_notes_json": source_notes,
        "status": "pending",
    }


def _attribute_items_for_entity(
    *,
    brand_id: int | None,
    version: str | None,
    entity_kind: str,
    entity_id: str | None,
    entity_name: str,
    attrs: dict[str, Any],
    source_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, value in attrs.items():
        if key in {"name", "aliases"}:
            continue
        values: list[str] = []
        if isinstance(value, list):
            values = _clean_list(value, limit=20)
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                text_value = normalize_text(sub_value, limit=240)
                if text_value:
                    values.append(f"{sub_key}: {text_value}")
        else:
            text_value = normalize_text(value, limit=320)
            if text_value:
                values.append(text_value)
        for text_value in values:
            candidate_key = attribute_candidate_key(
                entity_kind=entity_kind,
                entity_id=entity_id,
                entity_name=entity_name,
                attribute_key=key,
                value=text_value,
            )
            _append_unique(
                out,
                {
                    "id": _new_uuid(),
                    "brand_id": brand_id,
                    "brand_context_version": version,
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "attribute_key": normalize_text(key, limit=128),
                    "attribute_value": text_value,
                    "normalized_value": normalize_key_part(text_value, limit=512),
                    "candidate_key": candidate_key,
                    "source": "llm_search",
                    "confidence": 0.75,
                    "evidence_json": {"source": "brand_context_pack"},
                    "source_notes_json": source_notes,
                    "status": "pending",
                },
            )
    return out


def extract_candidates_from_context_payload(
    *,
    brand_id: int | None,
    brand_context_version: str | None,
    payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Extract reviewable entity / attribute / claim candidates from a context pack."""
    source_notes = _source_notes(payload)
    raw_brand = payload.get("brand")
    brand: dict[str, Any] = raw_brand if isinstance(raw_brand, dict) else {}
    brand_name = normalize_text(brand.get("name"), limit=256)
    domains = _clean_list(brand.get("official_domains"), limit=1)
    domain = domains[0] if domains else None
    entities: list[dict[str, Any]] = []
    attributes: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []

    brand_entity = _entity_item(
        brand_id=brand_id,
        version=brand_context_version,
        entity_type="brand",
        name=brand_name,
        parent_brand_id=None,
        parent_brand_name=None,
        domain=domain,
        attributes=brand,
        source_notes=source_notes,
        confidence=0.82,
    )
    if brand_entity:
        _append_unique(entities, brand_entity)
        attributes.extend(
            _attribute_items_for_entity(
                brand_id=brand_id,
                version=brand_context_version,
                entity_kind="brand",
                entity_id=str(brand_id) if brand_id is not None else None,
                entity_name=brand_name,
                attrs=brand,
                source_notes=source_notes,
            )
        )

    for product in payload.get("products") or []:
        if not isinstance(product, dict):
            continue
        name = normalize_text(product.get("name"), limit=256)
        item = _entity_item(
            brand_id=brand_id,
            version=brand_context_version,
            entity_type="product",
            name=name,
            parent_brand_id=brand_id,
            parent_brand_name=brand_name,
            domain=domain,
            attributes=product,
            source_notes=source_notes,
        )
        if item:
            _append_unique(entities, item)
            attributes.extend(
                _attribute_items_for_entity(
                    brand_id=brand_id,
                    version=brand_context_version,
                    entity_kind="product",
                    entity_id=None,
                    entity_name=name,
                    attrs=product,
                    source_notes=source_notes,
                )
            )

    for competitor in payload.get("competitors") or []:
        if not isinstance(competitor, dict):
            continue
        name = normalize_text(competitor.get("name"), limit=256)
        item = _entity_item(
            brand_id=brand_id,
            version=brand_context_version,
            entity_type="competitor",
            name=name,
            parent_brand_id=brand_id,
            parent_brand_name=brand_name,
            domain=domain,
            attributes=competitor,
            source_notes=source_notes,
        )
        if item:
            _append_unique(entities, item)
            attributes.extend(
                _attribute_items_for_entity(
                    brand_id=brand_id,
                    version=brand_context_version,
                    entity_kind="competitor",
                    entity_id=None,
                    entity_name=name,
                    attrs=competitor,
                    source_notes=source_notes,
                )
            )

    for scenario in payload.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        name = normalize_text(scenario.get("name"), limit=256)
        item = _entity_item(
            brand_id=brand_id,
            version=brand_context_version,
            entity_type="scenario",
            name=name,
            parent_brand_id=brand_id,
            parent_brand_name=brand_name,
            domain=domain,
            attributes=scenario,
            source_notes=source_notes,
        )
        if item:
            _append_unique(entities, item)
            attributes.extend(
                _attribute_items_for_entity(
                    brand_id=brand_id,
                    version=brand_context_version,
                    entity_kind="scenario",
                    entity_id=None,
                    entity_name=name,
                    attrs=scenario,
                    source_notes=source_notes,
                )
            )

    for segment in payload.get("audience_hypotheses") or []:
        if not isinstance(segment, dict):
            continue
        name = normalize_text(segment.get("segment_name") or segment.get("name"), limit=256)
        attrs = {k: v for k, v in segment.items() if k != "segment_name"}
        attrs["name"] = name
        item = _entity_item(
            brand_id=brand_id,
            version=brand_context_version,
            entity_type="segment",
            name=name,
            parent_brand_id=brand_id,
            parent_brand_name=brand_name,
            domain=domain,
            attributes=attrs,
            source_notes=source_notes,
        )
        if item:
            _append_unique(entities, item)
            attributes.extend(
                _attribute_items_for_entity(
                    brand_id=brand_id,
                    version=brand_context_version,
                    entity_kind="segment",
                    entity_id=None,
                    entity_name=name,
                    attrs=attrs,
                    source_notes=source_notes,
                )
            )

    raw_claims = payload.get("claims")
    claims_dict = raw_claims if isinstance(raw_claims, dict) else {}
    for claim_type, values in claims_dict.items():
        for text_value in _clean_list(values, limit=40):
            candidate_key = claim_candidate_key(
                entity_kind="brand",
                entity_id=str(brand_id) if brand_id is not None else None,
                entity_name=brand_name,
                claim_type=str(claim_type),
                text_value=text_value,
                scenario=None,
            )
            _append_unique(
                claims,
                {
                    "id": _new_uuid(),
                    "brand_id": brand_id,
                    "brand_context_version": brand_context_version,
                    "entity_kind": "brand",
                    "entity_id": str(brand_id) if brand_id is not None else None,
                    "entity_name": brand_name,
                    "claim_type": normalize_text(claim_type, limit=64),
                    "text": text_value,
                    "normalized_text": normalize_key_part(text_value, limit=700),
                    "scenario": None,
                    "candidate_key": candidate_key,
                    "source": "llm_search",
                    "confidence": 0.72,
                    "evidence_json": {"source": "brand_context_pack"},
                    "source_notes_json": source_notes,
                    "status": "pending",
                },
            )
    return {"entities": entities, "attributes": attributes, "claims": claims}


def _entity_row(row: LLMEntityCandidate) -> dict[str, Any]:
    return {
        "id": row.id,
        "brand_id": row.brand_id,
        "brand_context_version": row.brand_context_version,
        "entity_type": row.entity_type,
        "name": row.name,
        "normalized_name": row.normalized_name,
        "parent_brand_id": row.parent_brand_id,
        "parent_brand_name": row.parent_brand_name,
        "domain": row.domain,
        "candidate_key": row.candidate_key,
        "source": row.source,
        "confidence": row.confidence,
        "attributes": row.attributes_json or {},
        "evidence": row.evidence_json or {},
        "source_notes": row.source_notes_json or [],
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_reason": row.review_reason,
        "mapped_entity_kind": row.mapped_entity_kind,
        "mapped_entity_id": row.mapped_entity_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _attribute_row(row: LLMAttributeCandidate) -> dict[str, Any]:
    return {
        "id": row.id,
        "brand_id": row.brand_id,
        "brand_context_version": row.brand_context_version,
        "entity_kind": row.entity_kind,
        "entity_id": row.entity_id,
        "entity_name": row.entity_name,
        "attribute_key": row.attribute_key,
        "attribute_value": row.attribute_value,
        "normalized_value": row.normalized_value,
        "candidate_key": row.candidate_key,
        "source": row.source,
        "confidence": row.confidence,
        "evidence": row.evidence_json or {},
        "source_notes": row.source_notes_json or [],
        "status": row.status,
        "mapped_attribute_id": row.mapped_attribute_id,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_reason": row.review_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _claim_row(row: LLMClaimCandidate) -> dict[str, Any]:
    return {
        "id": row.id,
        "brand_id": row.brand_id,
        "brand_context_version": row.brand_context_version,
        "entity_kind": row.entity_kind,
        "entity_id": row.entity_id,
        "entity_name": row.entity_name,
        "claim_type": row.claim_type,
        "text": row.text,
        "normalized_text": row.normalized_text,
        "scenario": row.scenario,
        "candidate_key": row.candidate_key,
        "source": row.source,
        "confidence": row.confidence,
        "evidence": row.evidence_json or {},
        "source_notes": row.source_notes_json or [],
        "status": row.status,
        "mapped_claim_id": row.mapped_claim_id,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_reason": row.review_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_entity_candidates(
    session: AsyncSession,
    *,
    status: str = "pending",
    entity_type: str | None = None,
    brand_id: int | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(LLMEntityCandidate)
    count_stmt = select(LLMEntityCandidate.id)
    if status != "all":
        stmt = stmt.where(LLMEntityCandidate.status == status)
        count_stmt = count_stmt.where(LLMEntityCandidate.status == status)
    if entity_type:
        stmt = stmt.where(LLMEntityCandidate.entity_type == entity_type)
        count_stmt = count_stmt.where(LLMEntityCandidate.entity_type == entity_type)
    if brand_id is not None:
        stmt = stmt.where(LLMEntityCandidate.brand_id == brand_id)
        count_stmt = count_stmt.where(LLMEntityCandidate.brand_id == brand_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(LLMEntityCandidate.name.ilike(like))
        count_stmt = count_stmt.where(LLMEntityCandidate.name.ilike(like))
    total = len((await session.execute(count_stmt)).all())
    rows = list(
        (
            await session.execute(
                stmt.order_by(desc(LLMEntityCandidate.created_at)).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [_entity_row(row) for row in rows], total


async def list_attribute_candidates(
    session: AsyncSession,
    *,
    status: str = "pending",
    entity_kind: str | None = None,
    brand_id: int | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(LLMAttributeCandidate)
    count_stmt = select(LLMAttributeCandidate.id)
    if status != "all":
        stmt = stmt.where(LLMAttributeCandidate.status == status)
        count_stmt = count_stmt.where(LLMAttributeCandidate.status == status)
    if entity_kind:
        stmt = stmt.where(LLMAttributeCandidate.entity_kind == entity_kind)
        count_stmt = count_stmt.where(LLMAttributeCandidate.entity_kind == entity_kind)
    if brand_id is not None:
        stmt = stmt.where(LLMAttributeCandidate.brand_id == brand_id)
        count_stmt = count_stmt.where(LLMAttributeCandidate.brand_id == brand_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(LLMAttributeCandidate.entity_name.ilike(like))
        count_stmt = count_stmt.where(LLMAttributeCandidate.entity_name.ilike(like))
    total = len((await session.execute(count_stmt)).all())
    rows = list(
        (
            await session.execute(
                stmt.order_by(desc(LLMAttributeCandidate.created_at)).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [_attribute_row(row) for row in rows], total


async def list_claim_candidates(
    session: AsyncSession,
    *,
    status: str = "pending",
    entity_kind: str | None = None,
    brand_id: int | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(LLMClaimCandidate)
    count_stmt = select(LLMClaimCandidate.id)
    if status != "all":
        stmt = stmt.where(LLMClaimCandidate.status == status)
        count_stmt = count_stmt.where(LLMClaimCandidate.status == status)
    if entity_kind:
        stmt = stmt.where(LLMClaimCandidate.entity_kind == entity_kind)
        count_stmt = count_stmt.where(LLMClaimCandidate.entity_kind == entity_kind)
    if brand_id is not None:
        stmt = stmt.where(LLMClaimCandidate.brand_id == brand_id)
        count_stmt = count_stmt.where(LLMClaimCandidate.brand_id == brand_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(LLMClaimCandidate.text.ilike(like))
        count_stmt = count_stmt.where(LLMClaimCandidate.text.ilike(like))
    total = len((await session.execute(count_stmt)).all())
    rows = list(
        (
            await session.execute(
                stmt.order_by(desc(LLMClaimCandidate.created_at)).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [_claim_row(row) for row in rows], total


async def _load_pending_entity(session: AsyncSession, candidate_id: str) -> LLMEntityCandidate:
    row = (
        await session.execute(
            select(LLMEntityCandidate).where(LLMEntityCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise LLMExtractionError("candidate_not_found", "candidate not found")
    if row.status != "pending":
        raise LLMExtractionError("invalid_state", f"candidate already {row.status}")
    return row


async def _load_pending_attribute(
    session: AsyncSession, candidate_id: str
) -> LLMAttributeCandidate:
    row = (
        await session.execute(
            select(LLMAttributeCandidate).where(LLMAttributeCandidate.id == candidate_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise LLMExtractionError("candidate_not_found", "candidate not found")
    if row.status != "pending":
        raise LLMExtractionError("invalid_state", f"candidate already {row.status}")
    return row


async def _load_pending_claim(session: AsyncSession, candidate_id: str) -> LLMClaimCandidate:
    row = (
        await session.execute(select(LLMClaimCandidate).where(LLMClaimCandidate.id == candidate_id))
    ).scalar_one_or_none()
    if row is None:
        raise LLMExtractionError("candidate_not_found", "candidate not found")
    if row.status != "pending":
        raise LLMExtractionError("invalid_state", f"candidate already {row.status}")
    return row


def _entity_ref_key(entity_kind: str, entity_id: str | None, entity_name: str | None) -> str:
    if entity_id:
        return f"{entity_kind}:{entity_id}"
    return f"{entity_kind}:name:{normalize_key_part(entity_name or '')}"


async def _table_exists(session: AsyncSession, name: str) -> bool:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :n"
                ),
                {"n": name},
            )
        ).all()
    except Exception:
        return set()
    return {str(row[0]) for row in rows}


async def _upsert_brand_row(
    session: AsyncSession,
    *,
    name: str,
    attrs: dict[str, Any],
    admin_id: str,
) -> int | None:
    if not await _table_exists(session, "brands"):
        return None
    cols = await _table_columns(session, "brands")
    if "name" not in cols:
        return None
    existing = (
        await session.execute(
            text("SELECT id FROM brands WHERE LOWER(name) = LOWER(:name) LIMIT 1"),
            {"name": name},
        )
    ).first()
    if existing:
        return int(existing[0])
    fields: list[str] = []
    values: list[str] = []
    params: dict[str, Any] = {}

    def add(col: str, value: Any, *, jsonb: bool = False) -> None:
        if col not in cols:
            return
        fields.append(col)
        values.append(f"CAST(:{col} AS jsonb)" if jsonb else f":{col}")
        params[col] = json.dumps(value or [], ensure_ascii=False) if jsonb else value

    add("name", name)
    add("industry", attrs.get("industry"))
    add("description", attrs.get("description"))
    add("positioning", attrs.get("positioning"))
    add("aliases", attrs.get("aliases") or [], jsonb=True)
    add("official_domains", attrs.get("official_domains") or [], jsonb=True)
    add("status", "active")
    add("source", "llm_extraction")
    add("created_by", admin_id)
    if not fields:
        return None
    row = (
        await session.execute(
            text(
                f"INSERT INTO brands ({', '.join(fields)}) "
                f"VALUES ({', '.join(values)}) RETURNING id"
            ),
            params,
        )
    ).first()
    return int(row[0]) if row else None


async def _upsert_product_row(
    session: AsyncSession,
    *,
    brand_id: int | None,
    name: str,
    attrs: dict[str, Any],
) -> int | None:
    if brand_id is None or not await _table_exists(session, "products"):
        return None
    existing = (
        await session.execute(
            text(
                "SELECT id FROM products "
                "WHERE brand_id = :brand_id AND LOWER(name) = LOWER(:name) LIMIT 1"
            ),
            {"brand_id": brand_id, "name": name},
        )
    ).first()
    if existing:
        return int(existing[0])
    row = (
        await session.execute(
            text(
                """
                INSERT INTO products
                    (brand_id, name, category, description, aliases, status)
                VALUES
                    (:brand_id, :name, :category, :description,
                     CAST(:aliases AS jsonb), 'active')
                RETURNING id
                """
            ),
            {
                "brand_id": brand_id,
                "name": name,
                "category": attrs.get("category"),
                "description": attrs.get("description"),
                "aliases": json.dumps(attrs.get("aliases") or [], ensure_ascii=False),
            },
        )
    ).first()
    return int(row[0]) if row else None


async def _ensure_kg_brand(
    session: AsyncSession,
    *,
    brand_id: int | None,
    name: str,
    attrs: dict[str, Any],
) -> None:
    if brand_id is None:
        return
    existing = (
        await session.execute(select(KgBrand).where(KgBrand.brand_id == brand_id))
    ).scalar_one_or_none()
    if existing:
        existing.primary_name = name or existing.primary_name
        existing.aliases = attrs.get("aliases") or existing.aliases
        existing.official_domains = attrs.get("official_domains") or existing.official_domains
        existing.updated_at = _now()
        return
    session.add(
        KgBrand(
            brand_id=brand_id,
            primary_name=name,
            name_zh=attrs.get("name_zh"),
            name_en=attrs.get("name_en"),
            aliases=attrs.get("aliases") or [],
            official_domains=attrs.get("official_domains") or [],
            positioning=attrs.get("positioning"),
            status="approved",
        )
    )


async def _ensure_kg_product(
    session: AsyncSession,
    *,
    product_id: int | None,
    brand_id: int | None,
    name: str,
    attrs: dict[str, Any],
) -> None:
    if product_id is None or brand_id is None:
        return
    existing = (
        await session.execute(select(KgProduct).where(KgProduct.product_id == product_id))
    ).scalar_one_or_none()
    if existing:
        existing.primary_name = name or existing.primary_name
        existing.aliases = attrs.get("aliases") or existing.aliases
        existing.updated_at = _now()
        return
    session.add(
        KgProduct(
            product_id=product_id,
            brand_id=brand_id,
            primary_name=name,
            aliases=attrs.get("aliases") or [],
            status="approved",
        )
    )


async def approve_entity_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_entity(session, candidate_id)
    attrs = row.attributes_json if isinstance(row.attributes_json, dict) else {}
    mapped_kind = row.entity_type
    mapped_id: str | None = None

    if row.entity_type in {"brand", "competitor"}:
        brand_row_id = await _upsert_brand_row(
            session,
            name=row.name,
            attrs=attrs,
            admin_id=admin_id,
        )
        mapped_id = str(brand_row_id) if brand_row_id is not None else None
        await _ensure_kg_brand(
            session,
            brand_id=brand_row_id,
            name=row.name,
            attrs=attrs,
        )
        if row.entity_type == "competitor" and row.brand_id and brand_row_id:
            a_id, b_id = sorted([int(row.brand_id), int(brand_row_id)])
            existing = (
                await session.execute(
                    select(KgRelationCandidate).where(
                        KgRelationCandidate.entity_kind == "brand",
                        KgRelationCandidate.a_id == a_id,
                        KgRelationCandidate.b_id == b_id,
                        KgRelationCandidate.type == "COMPETES_WITH",
                    )
                )
            ).scalar_one_or_none()
            if existing is None and a_id != b_id:
                session.add(
                    KgRelationCandidate(
                        entity_kind="brand",
                        a_id=a_id,
                        b_id=b_id,
                        type="COMPETES_WITH",
                        confidence=row.confidence,
                        evidence={
                            "source": "llm_entity_candidate",
                            "candidate_id": row.id,
                            "candidate_name": row.name,
                        },
                        status="pending",
                        llm_model="llm_search",
                    )
                )
    elif row.entity_type == "product":
        product_id = await _upsert_product_row(
            session,
            brand_id=row.parent_brand_id or row.brand_id,
            name=row.name,
            attrs=attrs,
        )
        mapped_id = str(product_id) if product_id is not None else None
        await _ensure_kg_product(
            session,
            product_id=product_id,
            brand_id=row.parent_brand_id or row.brand_id,
            name=row.name,
            attrs=attrs,
        )
    elif row.entity_type == "segment":
        seg_id = f"SEG-LLM-{uuid.uuid4().hex[:10].upper()}"
        session.add(
            Segment(
                id=seg_id,
                code=seg_id,
                brand_id=str(row.brand_id) if row.brand_id is not None else None,
                brand_name=row.parent_brand_name,
                name=row.name,
                status="draft",
                note="Created from approved LLM extraction candidate",
                created_by=admin_id,
                updated_by=admin_id,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        mapped_id = seg_id
    elif row.entity_type == "profile":
        profile_id = f"PF-LLM-{uuid.uuid4().hex[:10].upper()}"
        session.add(
            Profile(
                id=profile_id,
                brand_id=str(row.brand_id) if row.brand_id is not None else None,
                brand_name=row.parent_brand_name,
                name=row.name,
                need=normalize_text(attrs.get("need") or attrs.get("needs"), limit=500),
                status="draft",
                persona_json=attrs,
                created_by=admin_id,
                updated_by=admin_id,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        mapped_id = profile_id
    else:
        mapped_id = row.id

    row.status = "approved"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.mapped_entity_kind = mapped_kind
    row.mapped_entity_id = mapped_id
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _entity_row(row)


async def reject_entity_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_entity(session, candidate_id)
    row.status = "rejected"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _entity_row(row)


async def approve_attribute_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_attribute(session, candidate_id)
    entity_ref_key = _entity_ref_key(row.entity_kind, row.entity_id, row.entity_name)
    existing = (
        await session.execute(
            select(KGEntityAttribute).where(
                KGEntityAttribute.entity_ref_key == entity_ref_key,
                KGEntityAttribute.attribute_key == row.attribute_key,
                KGEntityAttribute.normalized_value == row.normalized_value,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = KGEntityAttribute(
            id=_new_uuid(),
            entity_kind=row.entity_kind,
            entity_id=row.entity_id,
            entity_name=row.entity_name,
            entity_ref_key=entity_ref_key,
            attribute_key=row.attribute_key,
            attribute_value=row.attribute_value,
            normalized_value=row.normalized_value,
            source="llm_extraction",
            evidence=row.evidence_json,
            status="active",
            approved_from_candidate_id=row.id,
            reviewed_by=admin_id,
            reviewed_at=_now(),
        )
        session.add(existing)
    else:
        existing.status = "active"
        existing.reviewed_by = admin_id
        existing.reviewed_at = _now()
    row.status = "approved"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.mapped_attribute_id = existing.id
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _attribute_row(row)


async def reject_attribute_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_attribute(session, candidate_id)
    row.status = "rejected"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _attribute_row(row)


async def approve_claim_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_claim(session, candidate_id)
    entity_ref_key = _entity_ref_key(row.entity_kind, row.entity_id, row.entity_name)
    scenario = row.scenario or ""
    existing = (
        await session.execute(
            select(KGEntityClaim).where(
                KGEntityClaim.entity_ref_key == entity_ref_key,
                KGEntityClaim.claim_type == row.claim_type,
                KGEntityClaim.normalized_text == row.normalized_text,
                KGEntityClaim.scenario == scenario,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = KGEntityClaim(
            id=_new_uuid(),
            entity_kind=row.entity_kind,
            entity_id=row.entity_id,
            entity_name=row.entity_name,
            entity_ref_key=entity_ref_key,
            claim_type=row.claim_type,
            text=row.text,
            normalized_text=row.normalized_text,
            scenario=scenario,
            source="llm_extraction",
            evidence=row.evidence_json,
            status="active",
            approved_from_candidate_id=row.id,
            reviewed_by=admin_id,
            reviewed_at=_now(),
        )
        session.add(existing)
    else:
        existing.status = "active"
        existing.reviewed_by = admin_id
        existing.reviewed_at = _now()
    row.status = "approved"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.mapped_claim_id = existing.id
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _claim_row(row)


async def reject_claim_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    admin_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    row = await _load_pending_claim(session, candidate_id)
    row.status = "rejected"
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    row.review_reason = reason
    row.updated_at = _now()
    await session.commit()
    await session.refresh(row)
    return _claim_row(row)


async def backfill_extraction_candidates(
    session: AsyncSession,
    *,
    brand_id: int | None = None,
    brand_context_version: str | None = None,
    limit: int = 50,
) -> dict[str, int]:
    stmt = select(BrandContextSnapshot).where(BrandContextSnapshot.status == "active")
    if brand_id is not None:
        stmt = stmt.where(BrandContextSnapshot.brand_id == brand_id)
    if brand_context_version:
        stmt = stmt.where(BrandContextSnapshot.version == brand_context_version)
    stmt = stmt.order_by(desc(BrandContextSnapshot.created_at)).limit(max(1, min(limit, 500)))
    snapshots = list((await session.execute(stmt)).scalars().all())

    existing_entity_keys = {
        str(key)
        for key in (await session.execute(select(LLMEntityCandidate.candidate_key))).scalars()
    }
    existing_attribute_keys = {
        str(key)
        for key in (await session.execute(select(LLMAttributeCandidate.candidate_key))).scalars()
    }
    existing_claim_keys = {
        str(key)
        for key in (await session.execute(select(LLMClaimCandidate.candidate_key))).scalars()
    }
    summary = {
        "snapshots_scanned": len(snapshots),
        "entities_created": 0,
        "attributes_created": 0,
        "claims_created": 0,
        "duplicates_skipped": 0,
    }
    for snapshot in snapshots:
        payload = snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {}
        extracted = extract_candidates_from_context_payload(
            brand_id=int(snapshot.brand_id),
            brand_context_version=snapshot.version,
            payload=payload,
        )
        for item in extracted["entities"]:
            if item["candidate_key"] in existing_entity_keys:
                summary["duplicates_skipped"] += 1
                continue
            session.add(LLMEntityCandidate(**item))
            existing_entity_keys.add(item["candidate_key"])
            summary["entities_created"] += 1
        for item in extracted["attributes"]:
            if item["candidate_key"] in existing_attribute_keys:
                summary["duplicates_skipped"] += 1
                continue
            session.add(LLMAttributeCandidate(**item))
            existing_attribute_keys.add(item["candidate_key"])
            summary["attributes_created"] += 1
        for item in extracted["claims"]:
            if item["candidate_key"] in existing_claim_keys:
                summary["duplicates_skipped"] += 1
                continue
            session.add(LLMClaimCandidate(**item))
            existing_claim_keys.add(item["candidate_key"])
            summary["claims_created"] += 1
    await session.commit()
    return summary
