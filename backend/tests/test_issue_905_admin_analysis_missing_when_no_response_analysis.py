"""Issue #905 - Admin Attempts analyzer normalization.

Regression tests for ``format_attempt_analysis_fields``: when an LLM response
row carries ``analysis_status`` of ``"done"`` or ``"partial"`` but the joined
``response_analyses`` row is absent (``analysis_id IS NULL``), the formatter
must downgrade the reported status to ``"missing"`` to avoid the
"status=done with summary=None" false-success payload described in #905.
"""

from __future__ import annotations

import os

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def test_done_status_with_null_analysis_id_normalizes_to_missing() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "done",
            "analysis_id": None,
            "analyzer_run_status": None,
        }
    )

    assert item["analysis_status"] == "missing"
    assert item["analysis_summary"] is None


def test_partial_status_with_null_analysis_id_normalizes_to_missing() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "partial",
            "analysis_id": None,
            "analyzer_run_status": None,
        }
    )

    assert item["analysis_status"] == "missing"
    assert item["analysis_summary"] is None


def test_pending_status_with_null_analysis_id_still_normalizes_to_missing() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "pending",
            "analysis_id": None,
            "analyzer_run_status": None,
        }
    )

    assert item["analysis_status"] == "missing"
    assert item["analysis_summary"] is None


def test_done_status_with_present_analysis_id_stays_done() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "done",
            "analysis_id": 42,
            "analyzer_run_status": None,
            "analyzer_model": "gpt-test",
            "analyzed_at": "2026-05-13T10:00:00",
            "geo_score": 0.8,
            "visibility_score": 0.7,
            "sentiment_score": None,
            "sov_score": None,
            "citation_score": None,
            "total_brands_mentioned": 3,
            "target_brand_mentioned": True,
            "target_brand_sentiment": "positive",
            "mentions_count": None,
            "citations_count": 2,
            "features_count": None,
        }
    )

    assert item["analysis_status"] == "done"
    assert isinstance(item["analysis_summary"], dict)
    assert item["analysis_summary"]["geo_score"] == 0.8
    assert item["analysis_summary"]["visibility_score"] == 0.7


def test_queued_run_status_overrides_done_persisted_status() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "done",
            "analysis_id": None,
            "analyzer_run_status": "queued",
        }
    )

    assert item["analysis_status"] == "queued"


def test_failed_run_status_with_null_analysis_id_still_failed() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "response_id": 1,
            "response": "some text",
            "analysis_status": "done",
            "analysis_id": None,
            "analyzer_run_status": "failed",
        }
    )

    assert item["analysis_status"] == "failed"
