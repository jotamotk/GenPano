"""Brand context assembly and snapshot persistence.

The context pack is the shared Topic -> Prompt -> Query input. It combines
search-backed facts with local brand/product data and stores a versioned
snapshot so downstream generated rows can be audited against the exact context
used at generation time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import BrandContextSnapshot
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _clean_text(value: Any, *, limit: int = 300) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _clean_list(value: Any, *, limit: int = 10, item_limit: int = 160) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    for item in raw_items:
        text = _clean_text(item, limit=item_limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _dedupe_named(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        name = _clean_text(item.get("name"), limit=256)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        item["name"] = name
        out.append(item)
    return out


def _product_from_local(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _clean_text(row.get("name"), limit=256),
        "category": _clean_text(row.get("category"), limit=128) or None,
        "aliases": _clean_list(row.get("aliases"), limit=8),
        "key_features": [],
        "specs": {},
        "use_cases": [],
        "target_users": [],
        "price_positioning": None,
        "description": _clean_text(row.get("description"), limit=400) or None,
    }


def _product_from_search(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _clean_text(row.get("name"), limit=256),
        "category": _clean_text(row.get("category"), limit=128) or None,
        "aliases": _clean_list(row.get("aliases"), limit=8),
        "key_features": _clean_list(row.get("key_features") or row.get("features"), limit=12),
        "specs": row.get("specs") if isinstance(row.get("specs"), dict) else {},
        "use_cases": _clean_list(row.get("use_cases"), limit=12),
        "target_users": _clean_list(row.get("target_users") or row.get("audiences"), limit=8),
        "price_positioning": _clean_text(row.get("price_positioning"), limit=80) or None,
        "description": _clean_text(row.get("description"), limit=400) or None,
    }


def _source_notes(value: Any) -> list[dict[str, str]]:
    notes = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title"), limit=160)
            url = _clean_text(item.get("url"), limit=400)
            snippet = _clean_text(item.get("snippet"), limit=300)
            if title or url or snippet:
                notes.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "source_type": _clean_text(item.get("source_type"), limit=40)
                        or "web_search",
                    }
                )
    return notes[:20]


def assemble_brand_context_pack(
    *,
    brand: dict[str, Any],
    search_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize local brand data plus search output into one context pack."""
    search_context = search_context or {}
    products: list[dict[str, Any]] = [
        _product_from_local(item) for item in (brand.get("products") or []) if item.get("name")
    ]
    search_products = search_context.get("products")
    if isinstance(search_products, list):
        products.extend(
            _product_from_search(item) for item in search_products if isinstance(item, dict)
        )
    for name in _clean_list(search_context.get("product_lines"), limit=12):
        products.append(
            {
                "name": name,
                "category": None,
                "aliases": [],
                "key_features": [],
                "specs": {},
                "use_cases": [],
                "target_users": [],
                "price_positioning": None,
                "description": None,
            }
        )

    scenarios: list[dict[str, Any]] = []
    raw_scenarios = search_context.get("scenarios")
    if isinstance(raw_scenarios, list):
        for item in raw_scenarios:
            if isinstance(item, dict):
                scenarios.append(
                    {
                        "name": _clean_text(item.get("name"), limit=160),
                        "pain_points": _clean_list(item.get("pain_points"), limit=8),
                        "decision_criteria": _clean_list(item.get("decision_criteria"), limit=8),
                        "buying_stage": _clean_text(item.get("buying_stage"), limit=80) or None,
                    }
                )
            else:
                scenarios.append(
                    {
                        "name": _clean_text(item, limit=160),
                        "pain_points": [],
                        "decision_criteria": [],
                        "buying_stage": None,
                    }
                )
    for name in _clean_list(search_context.get("shopping_scenarios"), limit=12):
        scenarios.append(
            {
                "name": name,
                "pain_points": [],
                "decision_criteria": [],
                "buying_stage": None,
            }
        )

    competitors: list[dict[str, Any]] = []
    raw_competitors = search_context.get("competitors")
    if isinstance(raw_competitors, list):
        for item in raw_competitors:
            if not isinstance(item, dict):
                continue
            competitors.append(
                {
                    "name": _clean_text(item.get("name"), limit=256),
                    "competitor_type": _clean_text(
                        item.get("competitor_type") or item.get("type"), limit=40
                    )
                    or "direct",
                    "overlap_category": _clean_text(item.get("overlap_category"), limit=120)
                    or None,
                    "comparison_axes": _clean_list(
                        item.get("comparison_axes") or item.get("axes"), limit=8
                    ),
                    "relation_reason": _clean_text(item.get("relation_reason"), limit=240) or None,
                }
            )

    audience_hypotheses: list[dict[str, Any]] = []
    raw_audience = search_context.get("audience_hypotheses")
    if isinstance(raw_audience, list):
        for item in raw_audience:
            if isinstance(item, dict):
                audience_hypotheses.append(
                    {
                        "segment_name": _clean_text(item.get("segment_name"), limit=160),
                        "needs": _clean_list(item.get("needs"), limit=8),
                        "regions": _clean_list(item.get("regions"), limit=8),
                        "buying_stage": _clean_text(item.get("buying_stage"), limit=80) or None,
                    }
                )
    for name in _clean_list(search_context.get("target_audiences"), limit=8):
        audience_hypotheses.append(
            {"segment_name": name, "needs": [], "regions": [], "buying_stage": None}
        )

    raw_claims = search_context.get("claims")
    claims: dict[str, Any] = raw_claims if isinstance(raw_claims, dict) else {}
    return {
        "brand": {
            "name": _clean_text(brand.get("name"), limit=256),
            "aliases": _clean_list(brand.get("aliases"), limit=12),
            "industry": _clean_text(
                search_context.get("industry")
                or brand.get("industry")
                or brand.get("industry_name"),
                limit=160,
            ),
            "positioning": _clean_text(search_context.get("positioning"), limit=300) or None,
            "official_domains": _clean_list(search_context.get("official_domains"), limit=6),
            "description": _clean_text(
                search_context.get("description") or brand.get("description"), limit=700
            )
            or None,
        },
        "products": _dedupe_named(products),
        "scenarios": _dedupe_named(scenarios),
        "competitors": _dedupe_named(competitors),
        "audience_hypotheses": [item for item in audience_hypotheses if item.get("segment_name")][
            :12
        ],
        "claims": {
            "pros": _clean_list(claims.get("pros"), limit=12),
            "cons": _clean_list(claims.get("cons"), limit=12),
            "best_for": _clean_list(claims.get("best_for"), limit=12),
            "not_fit_for": _clean_list(claims.get("not_fit_for"), limit=12),
            "risks": _clean_list(claims.get("risks"), limit=12),
            "price_perception": _clean_list(claims.get("price_perception"), limit=8),
        },
        "source_notes": _source_notes(search_context.get("source_notes")),
    }


async def persist_brand_context_snapshot(
    session: AsyncSession,
    *,
    brand_id: int,
    payload: dict[str, Any],
    created_from_run_id: str | None = None,
    ttl_days: int = 7,
) -> str:
    version = f"bcx-{brand_id}-{uuid.uuid4().hex[:12]}"
    now = _now()
    row = BrandContextSnapshot(
        id=str(uuid.uuid4()),
        brand_id=int(brand_id),
        version=version,
        payload_json=payload,
        source_notes_json=payload.get("source_notes") or [],
        search_as_of=now,
        expires_at=now + timedelta(days=max(1, int(ttl_days or 7))),
        status="active",
        created_from_run_id=created_from_run_id,
    )
    session.add(row)
    await session.flush()
    return version


async def persist_brand_context_snapshots(
    session: AsyncSession,
    *,
    brands: list[dict[str, Any]],
    context_packs_by_name: dict[str, dict[str, Any]],
    created_from_run_id: str,
) -> tuple[dict[int, str], dict[int, dict[str, Any]]]:
    versions: dict[int, str] = {}
    packs_by_brand_id: dict[int, dict[str, Any]] = {}
    for brand in brands:
        name = _clean_text(brand.get("name"), limit=256)
        pack = context_packs_by_name.get(name)
        if not pack:
            continue
        brand_id = int(brand["id"])
        versions[brand_id] = await persist_brand_context_snapshot(
            session,
            brand_id=brand_id,
            payload=pack,
            created_from_run_id=created_from_run_id,
        )
        packs_by_brand_id[brand_id] = pack
    return versions, packs_by_brand_id


def topic_context_refs(
    *,
    topic_dimension: str,
    product_name: str | None,
    context_pack: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any]]:
    if not context_pack:
        return (topic_dimension or None), {}
    axis = (topic_dimension or "").strip() or None
    refs: dict[str, Any] = {}
    if product_name:
        refs["products"] = [product_name]
        return "product", refs
    if axis == "scenario":
        scenarios = [s.get("name") for s in context_pack.get("scenarios") or [] if s.get("name")]
        if scenarios:
            refs["scenarios"] = scenarios[:1]
    elif axis == "category":
        products = [
            p.get("category") for p in context_pack.get("products") or [] if p.get("category")
        ]
        if products:
            refs["product_categories"] = list(dict.fromkeys(products))[:3]
    elif axis == "question":
        raw_claims = context_pack.get("claims")
        claims: dict[str, Any] = raw_claims if isinstance(raw_claims, dict) else {}
        values: list[str] = []
        for key in ("pros", "cons", "best_for", "risks"):
            values.extend(claims.get(key) or [])
        if values:
            refs["claims"] = values[:3]
    return axis, refs
