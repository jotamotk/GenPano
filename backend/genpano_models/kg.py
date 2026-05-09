"""Knowledge Graph ORMs (Phase K) — 6 tables per ADR-011 / ADR-012."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class KgCategory(Base):
    """Category taxonomy node (industry → category tree)."""

    __tablename__ = "kg_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("kg_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name_zh: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="approved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KgBrand(Base):
    """1:1 mapping to existing `brands` (ADR-011)."""

    __tablename__ = "kg_brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    industry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_name: Mapped[str] = mapped_column(String(256), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(256), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    aliases: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    official_domains: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positioning: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="approved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KgProduct(Base):
    """1:1 mapping to existing `products` (ADR-011)."""

    __tablename__ = "kg_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    brand_id: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_name: Mapped[str] = mapped_column(String(256), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(256), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    aliases: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="approved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KgBrandRelation(Base):
    """Brand-to-brand edge (COMPETES_WITH | SAME_GROUP)."""

    __tablename__ = "kg_brand_relations"
    __table_args__ = (
        UniqueConstraint(
            "brand_a_id", "brand_b_id", "type", name="uq_kg_brand_relations_pair_type"
        ),
        CheckConstraint(
            "type IN ('COMPETES_WITH', 'SAME_GROUP')",
            name="ck_kg_brand_relations_type",
        ),
        CheckConstraint(
            "source IN ('analyzer', 'admin', 'import')",
            name="ck_kg_brand_relations_source",
        ),
        CheckConstraint("brand_a_id < brand_b_id", name="ck_kg_brand_relations_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    brand_a_id: Mapped[int] = mapped_column(Integer, nullable=False)
    brand_b_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KgProductRelation(Base):
    """Product-to-product edge.

    Types: COMPETES_WITH | SUBSTITUTES | UPGRADES_TO | BUDGET_ALT_OF | PAIRS_WITH.
    """

    __tablename__ = "kg_product_relations"
    __table_args__ = (
        UniqueConstraint(
            "product_a_id",
            "product_b_id",
            "type",
            name="uq_kg_product_relations_pair_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    product_a_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_b_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KgRelationCandidate(Base):
    """Staging for LLM-inferred relation edges (ADR-012)."""

    __tablename__ = "kg_relation_candidates"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('brand', 'product')",
            name="ck_kg_relation_candidates_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'merged')",
            name="ck_kg_relation_candidates_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    entity_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    a_id: Mapped[int] = mapped_column(Integer, nullable=False)
    b_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    merged_into_relation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KGEntityAttribute(Base):
    """Approved structured attributes extracted from search-backed LLM context."""

    __tablename__ = "kg_entity_attributes"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('brand','product','competitor','segment','profile','scenario')",
            name="ck_kg_entity_attributes_kind",
        ),
        CheckConstraint(
            "status IN ('active','archived')",
            name="ck_kg_entity_attributes_status",
        ),
        UniqueConstraint(
            "entity_ref_key",
            "attribute_key",
            "normalized_value",
            name="uq_kg_entity_attributes_key_value",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    entity_ref_key: Mapped[str] = mapped_column(String(384), nullable=False)
    attribute_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attribute_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(512), nullable=False)
    value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default="llm_extraction")
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    approved_from_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KGEntityClaim(Base):
    """Approved claims / opinions extracted from search-backed LLM context."""

    __tablename__ = "kg_entity_claims"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('brand','product','competitor','segment','profile','scenario')",
            name="ck_kg_entity_claims_kind",
        ),
        CheckConstraint(
            "status IN ('active','archived')",
            name="ck_kg_entity_claims_status",
        ),
        UniqueConstraint(
            "entity_ref_key",
            "claim_type",
            "normalized_text",
            "scenario",
            name="uq_kg_entity_claims_key_text",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    entity_ref_key: Mapped[str] = mapped_column(String(384), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(700), nullable=False)
    scenario: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default="llm_extraction")
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    approved_from_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
