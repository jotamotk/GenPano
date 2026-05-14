"""Issue #905 - fetch_response_analyzer_status must expose score/count fields.

Previously the SQL in ``backend/app/admin/analyzer/db.py::fetch_response_analyzer_status``
only selected ``analysis_id``, ``analyzer_model``, ``analyzed_at`` plus
analyzer_run metadata. The Admin Tracker UI then had no concrete score values
(``geo_score`` / ``visibility_score`` / ``mentions_count`` / etc.) to render
in its per-row analyzer summary, so it fell through to the readiness-reason
fallback (`category was not canonicalized`, `mention evidence_quote is not
present in response_text`, ...) added by PR #934 — and looked to the user
like "详情列表也看不到任何的数据".

These regression tests assert the SQL now selects the full score + count
field set. SQLite can't execute the PostgreSQL-specific ``jsonb_agg`` /
``FILTER`` clauses used by the quality-flag LATERAL JOIN, so we capture the
rendered SQL string via a stub session and assert on its content.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _FakeAsyncOpenAI:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


openai = types.ModuleType("openai")
openai.AsyncOpenAI = _FakeAsyncOpenAI
sys.modules.setdefault("openai", openai)

import pytest  # noqa: E402

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


class _CapturedExec:
    """Records the SQL string passed to session.execute() and returns a
    minimal sqlalchemy Result-like object so the caller can chain
    ``.mappings().first()``."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self.captured_sql: str | None = None

        class _Result:
            def __init__(self, row: dict[str, Any] | None) -> None:
                self._row = row

            def mappings(self):
                outer = self

                class _Mappings:
                    def first(_self):
                        return outer._row

                return _Mappings()

        self._result = _Result(row)

    async def __call__(self, query, params=None):
        try:
            self.captured_sql = str(query)
        except Exception:
            self.captured_sql = repr(query)
        return self._result


@pytest.mark.asyncio
async def test_fetch_status_sql_selects_score_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """All five response_analyses score columns must be in the SELECT list."""
    from app.admin.analyzer import db as analyzer_db

    monkeypatch.setattr(analyzer_db, "_table_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(
        analyzer_db,
        "_table_columns",
        AsyncMock(return_value={"task_id", "batch_id"}),
    )

    captured_row = {
        "response_id": 1,
        "query_id": 2,
        "raw_text": "x",
        "analysis_status": "done",
        "analyzed_at": None,
        "attempt_status": "done",
        "analysis_id": 99,
        "analyzer_model": "doubao",
        "analysis_analyzed_at": None,
        "geo_score": 0.82,
        "visibility_score": 0.75,
        "sentiment_score": 0.65,
        "sov_score": 0.50,
        "citation_score": 0.40,
        "total_brands_mentioned": 2,
        "target_brand_mentioned": True,
        "target_brand_sentiment": "positive",
        "mentions_count": 3,
        "citations_count": 4,
        "features_count": 5,
        "analyzer_run_id": 11,
        "analysis_schema_version": "v4",
        "analyzer_run_status": "done",
        "run_model": "doubao",
        "analyzer_run_started_at": None,
        "analyzer_run_completed_at": None,
        "analysis_error_code": None,
        "analysis_error_message": None,
        "task_id": None,
        "batch_id": None,
        "validator_summary_json": None,
        "quality_flag_count": 0,
        "blocking_quality_flag_count": 0,
        "quality_flags": [],
    }

    fake_exec = _CapturedExec(captured_row)

    class _Session:
        execute = fake_exec

    item = await analyzer_db.fetch_response_analyzer_status(_Session(), 1)  # type: ignore[arg-type]
    sql = fake_exec.captured_sql or ""

    # Score columns
    assert "ra.geo_score" in sql, "geo_score missing from SELECT"
    assert "ra.visibility_score" in sql, "visibility_score missing from SELECT"
    assert "ra.sentiment_score" in sql, "sentiment_score missing from SELECT"
    assert "ra.sov_score" in sql, "sov_score missing from SELECT"
    assert "ra.citation_score" in sql, "citation_score missing from SELECT"
    # Aggregate flags
    assert "ra.total_brands_mentioned" in sql
    assert "ra.target_brand_mentioned" in sql
    assert "ra.target_brand_sentiment" in sql
    # LATERAL counts
    assert "mentions_count" in sql
    assert "citations_count" in sql
    assert "features_count" in sql
    assert "FROM brand_mentions bm WHERE bm.response_id = lr.id" in sql
    assert "FROM citation_sources cs WHERE cs.response_id = lr.id" in sql
    assert "FROM product_feature_mentions pfm" in sql

    # And the returned row makes it back to the caller untouched
    assert item is not None
    assert item["geo_score"] == 0.82
    assert item["visibility_score"] == 0.75
    assert item["mentions_count"] == 3


@pytest.mark.asyncio
async def test_fetch_status_sql_handles_missing_response_analyses_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When response_analyses table is absent, score columns must still be
    present in the SELECT shape as NULL placeholders so the formatter contract
    stays stable."""
    from app.admin.analyzer import db as analyzer_db

    async def _table_exists(_session, name: str) -> bool:
        # llm_responses must exist or the function early-returns None.
        if name == "llm_responses":
            return True
        return False

    monkeypatch.setattr(analyzer_db, "_table_exists", AsyncMock(side_effect=_table_exists))
    monkeypatch.setattr(analyzer_db, "_table_columns", AsyncMock(return_value=set()))

    fake_exec = _CapturedExec({"response_id": 1})

    class _Session:
        execute = fake_exec

    await analyzer_db.fetch_response_analyzer_status(_Session(), 1)  # type: ignore[arg-type]
    sql = fake_exec.captured_sql or ""

    assert "NULL AS geo_score" in sql
    assert "NULL AS visibility_score" in sql
    assert "NULL AS sentiment_score" in sql
    assert "NULL AS sov_score" in sql
    assert "NULL AS citation_score" in sql
    assert "NULL AS total_brands_mentioned" in sql
    assert "NULL AS target_brand_mentioned" in sql
    assert "NULL AS target_brand_sentiment" in sql
    assert "NULL AS mentions_count" in sql
    assert "NULL AS citations_count" in sql
    assert "NULL AS features_count" in sql


@pytest.mark.asyncio
async def test_fetch_status_payload_feeds_format_attempt_analysis_fields() -> None:
    """End-to-end shape: when fetch_response_analyzer_status returns the new
    fields, format_attempt_analysis_fields surfaces them inside
    ``analysis_summary`` so the front-end JS can render real numbers instead
    of falling back to the readiness-reason string."""
    from app.admin.queries.db import format_attempt_analysis_fields

    fake_row = {
        "response_id": 648,
        "query_id": 185005,
        "response": "bestCoffer 在 AI 数据脱敏方向表现突出",
        "analysis_status": "done",
        "analysis_id": 12345,
        "analyzer_model": "doubao-seed-2-0-pro-260215",
        "analyzed_at": None,
        "geo_score": 0.82,
        "visibility_score": 0.75,
        "sentiment_score": 0.65,
        "sov_score": 0.50,
        "citation_score": 0.40,
        "total_brands_mentioned": 2,
        "target_brand_mentioned": True,
        "target_brand_sentiment": "positive",
        "mentions_count": 3,
        "citations_count": 4,
        "features_count": 5,
        "analyzer_run_id": 999,
        "analyzer_run_status": "done",
        "quality_flag_count": 0,
        "blocking_quality_flag_count": 0,
        "quality_flags": [],
    }
    item = format_attempt_analysis_fields(fake_row)
    summary = item["analysis_summary"]
    assert summary is not None, "analysis_summary should be a dict, not None"
    assert summary["geo_score"] == 0.82
    assert summary["visibility_score"] == 0.75
    assert summary["sentiment_score"] == 0.65
    assert summary["sov_score"] == 0.50
    assert summary["citation_score"] == 0.40
    assert summary["mentions_count"] == 3
    assert summary["citations_count"] == 4
    assert summary["total_brands_mentioned"] == 2
    assert summary["target_brand_mentioned"] is True
    assert summary["target_brand_sentiment"] == "positive"
    # And the status should be `done` (passes through), not `missing`.
    assert item["analysis_status"] == "done"


@pytest.mark.asyncio
async def test_fetch_status_payload_with_partial_scores_still_surfaces_counts() -> None:
    """Partial scores (some NULL, some present) plus non-zero counts should
    still produce a non-empty analysis_summary so the UI partial-evidence
    fallback can render mention/citation numbers."""
    from app.admin.queries.db import format_attempt_analysis_fields

    fake_row = {
        "response_id": 648,
        "response": "bestCoffer 只是泛泛提及",
        "analysis_status": "done",
        "analysis_id": 12345,
        "geo_score": None,  # SoV-derived composite skipped (no competitors)
        "visibility_score": 0.3,
        "sentiment_score": None,
        "sov_score": None,
        "citation_score": None,
        "total_brands_mentioned": 1,
        "target_brand_mentioned": True,
        "target_brand_sentiment": None,
        "mentions_count": 1,
        "citations_count": 0,
        "features_count": 0,
    }
    item = format_attempt_analysis_fields(fake_row)
    summary = item["analysis_summary"]
    assert summary is not None
    assert summary["visibility_score"] == 0.3
    assert summary["mentions_count"] == 1
    assert summary["citations_count"] == 0
    assert summary["total_brands_mentioned"] == 1
    # geo_score / sov_score remain None — the front-end will display
    # the non-NULL values (visibility, mention count, citation count) and
    # skip the NULL composites.
    assert summary["geo_score"] is None
    assert summary["sov_score"] is None
