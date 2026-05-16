"""Issue #1020: domain_authority heuristic tier fallback.

The `/brand/citations` donut + Authority Share trend collapsed to 100%
``未分类`` whenever ``domain_authorities`` was unseeded (which is the
default state of every newly-provisioned env). PR for #1020 introduces a
*project-agnostic* heuristic fallback so the chart helpers can still
bucket citations into Tier 1-4 without writing curated rows.

The Business Goal Layer row (donut visually colourful for the real user)
is verified post-deploy via App Analytics Readonly Evidence — these
tests pin the **process indicators** required to reach that goal:

1. The classifier itself returns expected tiers per input.
2. `_target_citation_composition_rows` (the admin-fact target path) and
   `_target_authority_points_from_facts` (the trend target path) apply
   the heuristic when ``DomainAuthority.tier IS NULL`` so the resulting
   segments / points carry real non-null tiers — even with an empty
   ``domain_authorities`` table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from genpano_models import BrandMention, CitationSource
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects.charts._domain_tier_heuristic import _classify_untiered_domain
from app.api.v1.projects.charts.authority import _target_authority_points_from_facts
from app.api.v1.projects.charts.citation import _target_citation_composition_rows

BRAND_ID = 24
DAY = datetime(2026, 5, 13, 8, 0, 0)


# ---------------------------------------------------------------------------
# Classifier unit tests
# ---------------------------------------------------------------------------


def test_classify_brand_alias_matches_tier_1() -> None:
    assert _classify_untiered_domain("bestcoffer.com", ["bestcoffer"]) == 1


def test_classify_brand_alias_subdomain_matches_tier_1() -> None:
    assert _classify_untiered_domain("docs.bestcoffer.com", ["bestcoffer"]) == 1
    assert _classify_untiered_domain("www.bestcoffer.com", ["bestcoffer"]) == 1


def test_classify_brand_alias_full_hostname_matches_tier_1() -> None:
    # Alias supplied as an explicit hostname (rare but supported).
    assert _classify_untiered_domain("bestcoffer.cn", ["bestcoffer.cn"]) == 1


def test_classify_authority_known_host_tier_2() -> None:
    assert _classify_untiered_domain("ibm.com", []) == 2
    assert _classify_untiered_domain("mediacenter.ibm.com", []) == 2
    assert _classify_untiered_domain("reuters.com", []) == 2


def test_classify_authority_gov_suffix_tier_2() -> None:
    assert _classify_untiered_domain("whitehouse.gov", []) == 2
    assert _classify_untiered_domain("spc.gov.cn", []) == 2
    assert _classify_untiered_domain("foo.edu", []) == 2
    assert _classify_untiered_domain("tsinghua.edu.cn", []) == 2


def test_classify_kol_host_tier_3() -> None:
    assert _classify_untiered_domain("zhihu.com", []) == 3
    assert _classify_untiered_domain("xiaohongshu.com", []) == 3
    assert _classify_untiered_domain("weibo.com", []) == 3


def test_classify_unknown_domain_tier_4() -> None:
    assert _classify_untiered_domain("alldatarooms.com", []) == 4
    assert _classify_untiered_domain("randomforum.io", []) == 4


def test_classify_empty_domain_returns_none() -> None:
    """Issue #1020 forbids silent coercion of genuinely-unknown rows."""
    assert _classify_untiered_domain(None, ["bestcoffer"]) is None
    assert _classify_untiered_domain("", ["bestcoffer"]) is None
    assert _classify_untiered_domain("   ", ["bestcoffer"]) is None


def test_classify_alias_takes_priority_over_authority_set() -> None:
    """If a brand happens to be hosted under an authority TLD (gov/edu)
    or shares a label with a known media host, the alias-driven Tier 1
    rule must still win."""
    # Tier-1 alias takes priority over the .gov suffix.
    assert _classify_untiered_domain("acme.gov", ["acme"]) == 1


def test_classify_lowercases_and_strips_www() -> None:
    assert _classify_untiered_domain("WWW.IBM.COM", []) == 2


# ---------------------------------------------------------------------------
# Integration tests against the target helpers
# ---------------------------------------------------------------------------


async def _seed_brand_aliases_table(db_session: AsyncSession) -> None:
    """Test envs ship with a stub ``brands`` table (id only). Extend it so
    ``brand_mention_names`` can read the brand's display name + aliases."""
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name TEXT"))
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN aliases TEXT"))
    await db_session.execute(
        text("INSERT INTO brands (id, name, aliases) VALUES (:id, :name, :aliases)"),
        {"id": BRAND_ID, "name": "BestCoffer", "aliases": "[]"},
    )
    await db_session.commit()


async def _seed_citation_rows(
    db_session: AsyncSession,
    *,
    response_id: int,
    domains: list[tuple[str, int]],
) -> None:
    """Seed a BrandMention + N CitationSource rows for the given domains.

    Each tuple is ``(domain, count)`` — the helper inserts ``count`` rows
    sharing that domain so the resulting GROUP BY yields the expected
    aggregate counts.

    Note: ``llm_responses`` is a stub table in the test schema (id only);
    we don't insert rows there because the FK column on
    ``BrandMention`` / ``CitationSource`` only constrains within the
    in-process SQLite session — the chart helpers join via mention_id /
    response_id values, both supplied here.
    """
    mention = BrandMention(
        response_id=response_id,
        brand_id=BRAND_ID,
        brand_name="BestCoffer",
        mention_count=1,
        sentiment="neutral",
        sentiment_score=0.0,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    for domain, count in domains:
        for _ in range(count):
            db_session.add(
                CitationSource(
                    response_id=response_id,
                    mention_id=mention.id,
                    url=f"https://{domain}/page",
                    domain=domain,
                    title="t",
                    source_type="article",
                    created_at=DAY,
                )
            )
    await db_session.commit()


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    await _seed_brand_aliases_table(db_session)
    return db_session


@pytest.mark.asyncio
async def test_target_citation_composition_rows_heuristic_classifies_untiered(
    seeded_session: AsyncSession,
) -> None:
    """When ``domain_authorities`` has no rows, the target path must still
    classify cited domains via the heuristic so the resulting segments
    carry Tier 1 / Tier 2 / Tier 3 / Tier 4 (NOT 100% tier=null).
    """
    await _seed_citation_rows(
        seeded_session,
        response_id=9101,
        domains=[
            ("bestcoffer.com", 4),  # Tier 1 via brand alias
            ("ibm.com", 2),  # Tier 2 via authority host
            ("zhihu.com", 1),  # Tier 3 via KOL host
            ("alldatarooms.com", 3),  # Tier 4 (default)
        ],
    )

    segments, total = await _target_citation_composition_rows(
        seeded_session,
        brand_id=BRAND_ID,
        response_ids=[9101],
    )
    by_tier = {seg.tier: seg.count for seg in segments}

    assert total == 10
    assert by_tier.get(1) == 4
    assert by_tier.get(2) == 2
    assert by_tier.get(3) == 1
    assert by_tier.get(4) == 3
    # ``未分类`` bucket must NOT carry the bulk of traffic when every
    # cited domain is heuristic-classifiable.
    assert by_tier.get(None, 0) == 0


@pytest.mark.asyncio
async def test_target_citation_composition_rows_business_goal_proxy(
    seeded_session: AsyncSession,
) -> None:
    """Pin the Business Goal Layer proxy: with a realistic mix of cited
    domains (mostly untiered, classifiable by heuristic), at least 2
    different non-null tiers must surface as non-zero segments — the
    visual proxy for "donut has multiple colored slices, not 100% gray".
    """
    await _seed_citation_rows(
        seeded_session,
        response_id=9201,
        domains=[
            ("bestcoffer.com", 1),
            ("ibm.com", 1),
            ("alldatarooms.com", 1),
        ],
    )

    segments, _total = await _target_citation_composition_rows(
        seeded_session,
        brand_id=BRAND_ID,
        response_ids=[9201],
    )
    non_null_non_zero_tiers = {
        seg.tier for seg in segments if seg.tier is not None and seg.count > 0
    }
    assert len(non_null_non_zero_tiers) >= 2, (
        f"Donut must show at least 2 distinct tiers; got: {non_null_non_zero_tiers}"
    )


@pytest.mark.asyncio
async def test_target_authority_points_from_facts_heuristic(
    seeded_session: AsyncSession,
) -> None:
    """Authority trend path applies the same heuristic so the per-day
    points expose non-zero ``tier1_pct`` / ``tier2_pct`` / ``tier4_pct``
    even when ``domain_authorities`` is empty.
    """
    await _seed_citation_rows(
        seeded_session,
        response_id=9301,
        domains=[
            ("bestcoffer.com", 2),  # Tier 1
            ("ibm.com", 2),  # Tier 2
            ("alldatarooms.com", 1),  # Tier 4
        ],
    )

    points, total = await _target_authority_points_from_facts(
        seeded_session,
        brand_id=BRAND_ID,
        response_days={9301: "2026-05-13"},
    )
    assert total == 5
    assert len(points) == 1
    point = points[0]
    assert point.date == "2026-05-13"
    assert point.tier1_pct > 0
    assert point.tier2_pct > 0
    assert point.tier4_pct > 0
    # Heuristic must NOT silently bucket every row as untiered.
    assert point.untiered_pct == 0


@pytest.mark.asyncio
async def test_target_paths_empty_response_id_short_circuit(
    seeded_session: AsyncSession,
) -> None:
    """Short-circuit behavior is unchanged: no response_ids → empty out."""
    segs, total = await _target_citation_composition_rows(
        seeded_session, brand_id=BRAND_ID, response_ids=[]
    )
    assert segs == []
    assert total == 0

    points, total = await _target_authority_points_from_facts(
        seeded_session, brand_id=BRAND_ID, response_days={}
    )
    assert points == []
    assert total == 0


@pytest.mark.asyncio
async def test_target_citation_composition_rows_respects_db_tier_when_present(
    seeded_session: AsyncSession,
) -> None:
    """When ``domain_authorities`` *does* have a row, the curated tier
    wins over the heuristic — the data path stays canonical."""
    # Curated: ibm.com → Tier 4 (intentionally wrong vs. heuristic so we
    # can prove the DB row takes precedence).
    await seeded_session.execute(
        text(
            "INSERT INTO domain_authorities (domain, tier, confidence,"
            " created_at, updated_at) VALUES ('ibm.com', 4, 1.0, :day, :day)"
        ),
        {"day": DAY},
    )
    await _seed_citation_rows(
        seeded_session,
        response_id=9401,
        domains=[("ibm.com", 3)],
    )

    segments, total = await _target_citation_composition_rows(
        seeded_session, brand_id=BRAND_ID, response_ids=[9401]
    )
    by_tier: dict[Any, int] = {seg.tier: seg.count for seg in segments}
    # DB row wins → Tier 4, not heuristic Tier 2.
    assert by_tier.get(4) == 3
    assert by_tier.get(2, 0) == 0
    assert total == 3
