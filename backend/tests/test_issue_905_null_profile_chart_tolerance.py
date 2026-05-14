"""Issue #905 (B/App) - null-profile tolerance in brand-level aggregation.

The App-side Topics/chart aggregation builds its query scope through
`_query_scope_conditions()`. Previously, when a `profile_id` filter was
present, the SQL gate excluded every `queries` row whose `profile_id IS NULL`
- even though those rows are still bound to the project's brand via
`queries.brand_id`. That dropped real responses from chart and topic
aggregation whenever the analyzer had not yet bound a profile to a query.

Option B (authorized scope): the explicit `profile_id` filter should tolerate
null `profile_id` rows so they continue to contribute to brand-level
aggregation. Segment filtering is unchanged - a row with no profile cannot be
in a segment, so the segment EXISTS subquery naturally excludes it.

This module exercises `_query_scope_conditions()` directly and via an
in-memory sqlite row set so the SQL gate's behaviour is locked down.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import Profile, Project, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _query_scope_conditions,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


_QUERY_COLS_WITH_PROFILE: set[str] = {
    "id",
    "brand_id",
    "profile_id",
    "prompt_id",
    "target_llm",
    "created_at",
    "status",
}


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"null-profile-{uuid.uuid4().hex[:6]}@example.com",
        name="Null Profile User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    proj = Project(
        user_id=user.id,
        name="Null Profile Project",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(proj)
    await db_session.commit()
    return proj


async def _ensure_legacy_queries_table(db_session: AsyncSession) -> None:
    """Create a minimal legacy `queries` table with a `profile_id` column."""
    await db_session.execute(
        text(
            """
            CREATE TABLE queries (
                id INTEGER PRIMARY KEY,
                brand_id INTEGER,
                profile_id TEXT,
                target_llm TEXT,
                status TEXT,
                created_at DATETIME
            )
            """
        )
    )


async def _insert_queries_with_profile_mix(db_session: AsyncSession) -> None:
    now = datetime.now()
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, brand_id, profile_id, target_llm, status, created_at)
            VALUES
                (1, 42, '5', 'chatgpt', 'done', :now),
                (2, 42, NULL, 'chatgpt', 'done', :now),
                (3, 42, 'other', 'chatgpt', 'done', :now),
                (4, 42, '5', 'doubao', 'done', :now)
            """
        ),
        {"now": now},
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_query_scope_includes_null_profile_when_profile_id_filter_set(
    db_session: AsyncSession,
    project: Project,
) -> None:
    """The SQL gate must permit `q.profile_id IS NULL` rows when filtering."""
    filters = AnalysisFilters(profile_id="5")

    conditions, params = await _query_scope_conditions(
        db_session,
        project=project,
        filters=filters,
        query_cols=_QUERY_COLS_WITH_PROFILE,
    )

    profile_conds = [c for c in conditions if "profile_id" in c and "EXISTS" not in c]
    assert profile_conds, "profile_id condition missing from query scope"
    assert any("q.profile_id IS NULL" in c for c in profile_conds), (
        f"expected profile_id condition to tolerate NULL, got: {profile_conds}"
    )
    assert any("CAST(q.profile_id AS TEXT) = :profile_id" in c for c in profile_conds), (
        f"expected exact-match leg to remain, got: {profile_conds}"
    )
    assert params["profile_id"] == "5"

    # End-to-end row-set verification against an in-memory queries table.
    await _ensure_legacy_queries_table(db_session)
    await _insert_queries_with_profile_mix(db_session)
    where = " AND ".join(conditions)
    rows = (
        await db_session.execute(
            text(f"SELECT id FROM queries q WHERE {where} ORDER BY id"),
            params,
        )
    ).all()
    ids = [r[0] for r in rows]
    # Row 1 and 4 match profile_id='5'; row 2 has NULL profile_id and is now
    # tolerated; row 3 has a non-matching profile_id and must stay excluded.
    assert ids == [1, 2, 4], f"unexpected row set: {ids}"


@pytest.mark.asyncio
async def test_query_scope_still_includes_matching_profile_id(
    db_session: AsyncSession,
    project: Project,
) -> None:
    """Regression: rows whose profile_id equals the filter still match."""
    filters = AnalysisFilters(profile_id="5")

    conditions, params = await _query_scope_conditions(
        db_session,
        project=project,
        filters=filters,
        query_cols=_QUERY_COLS_WITH_PROFILE,
    )

    await _ensure_legacy_queries_table(db_session)
    await _insert_queries_with_profile_mix(db_session)

    where = " AND ".join(conditions)
    rows = (
        await db_session.execute(
            text(f"SELECT id FROM queries q WHERE {where}"),
            params,
        )
    ).all()
    ids = {r[0] for r in rows}
    assert {1, 4}.issubset(ids), f"matching-profile rows missing: {ids}"


@pytest.mark.asyncio
async def test_query_scope_excludes_non_matching_non_null_profile_id(
    db_session: AsyncSession,
    project: Project,
) -> None:
    """Regression: a non-null, non-matching profile_id row stays excluded."""
    filters = AnalysisFilters(profile_id="5")

    conditions, params = await _query_scope_conditions(
        db_session,
        project=project,
        filters=filters,
        query_cols=_QUERY_COLS_WITH_PROFILE,
    )

    await _ensure_legacy_queries_table(db_session)
    await _insert_queries_with_profile_mix(db_session)

    where = " AND ".join(conditions)
    rows = (
        await db_session.execute(
            text(f"SELECT id FROM queries q WHERE {where}"),
            params,
        )
    ).all()
    ids = {r[0] for r in rows}
    assert 3 not in ids, f"row with profile_id='other' must be excluded; got {ids}"


@pytest.mark.asyncio
async def test_query_scope_no_filter_unchanged(
    db_session: AsyncSession,
    project: Project,
) -> None:
    """Regression: with no profile_id filter, every brand-scoped row appears."""
    filters = AnalysisFilters()  # no profile_id, no segment, no engines

    conditions, params = await _query_scope_conditions(
        db_session,
        project=project,
        filters=filters,
        query_cols=_QUERY_COLS_WITH_PROFILE,
    )

    # No profile/segment gate should be present at all when the filter is empty.
    assert not any("profile_id" in c for c in conditions), (
        f"profile_id condition leaked despite empty filters: {conditions}"
    )

    await _ensure_legacy_queries_table(db_session)
    await _insert_queries_with_profile_mix(db_session)

    where = " AND ".join(conditions) if conditions else "1 = 1"
    rows = (
        await db_session.execute(
            text(f"SELECT id FROM queries q WHERE {where} ORDER BY id"),
            params,
        )
    ).all()
    ids = [r[0] for r in rows]
    assert ids == [1, 2, 3, 4], (
        f"empty filter must keep all brand-scoped rows including NULL profile; got {ids}"
    )


@pytest.mark.asyncio
async def test_segment_filter_still_excludes_null_profile(
    db_session: AsyncSession,
    project: Project,
) -> None:
    """Segment semantics intact: a NULL-profile row cannot be in any segment."""
    # Build the legacy queries table so the segment branch can run; `profiles`
    # already exists from the ORM `Profile` model in conftest.
    await _ensure_legacy_queries_table(db_session)
    await _insert_queries_with_profile_mix(db_session)
    db_session.add_all(
        [
            Profile(
                id="5",
                segment_id="SEG-A",
                brand_id="42",
                brand_name="Test Brand",
                name="Profile 5",
                status="active",
                weight=1,
            ),
            Profile(
                id="other",
                segment_id="SEG-B",
                brand_id="42",
                brand_name="Test Brand",
                name="Profile Other",
                status="active",
                weight=1,
            ),
        ]
    )
    await db_session.commit()

    filters = AnalysisFilters(segment_id="SEG-A")

    conditions, params = await _query_scope_conditions(
        db_session,
        project=project,
        filters=filters,
        query_cols=_QUERY_COLS_WITH_PROFILE,
    )

    # The segment branch must contribute an EXISTS subquery against profiles.
    assert any("EXISTS" in c and "profiles pf" in c for c in conditions), (
        f"expected segment EXISTS subquery; got {conditions}"
    )

    where = " AND ".join(conditions)
    rows = (
        await db_session.execute(
            text(f"SELECT id FROM queries q WHERE {where} ORDER BY id"),
            params,
        )
    ).all()
    ids = [r[0] for r in rows]
    # Only rows 1 and 4 (profile_id='5' -> segment SEG-A) match. Row 2's NULL
    # profile_id must NOT slip through the segment filter.
    assert 2 not in ids, f"NULL-profile row 2 must not appear under a segment filter; got {ids}"
    assert ids == [1, 4], f"segment filter row set mismatch: {ids}"
