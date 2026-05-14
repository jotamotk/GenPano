"""Issue #845 - Admin Tracker analyzer evidence contract."""

from __future__ import annotations


def _format(row: dict):
    from app.admin.queries.db import format_attempt_analysis_fields

    base = {
        "id": 184999,
        "response_id": 569,
        "response": "DeepSeek answer text",
    }
    base.update(row)
    return format_attempt_analysis_fields(base)


def test_tracker_analysis_contract_no_analyzer_row_is_missing_without_scores() -> None:
    item = _format({})

    assert item["analysis_status"] == "missing"
    assert item["analysis_summary"] is None
    assert item["analysis"]["status"] == "missing"
    assert item["analysis"]["score_source"] == "none"
    assert item["analysis"]["scores_explicit"] is False
    assert item["analysis"]["geo_score"] is None
    assert item["analysis"]["visibility_score"] is None
    assert item["analysis"]["sentiment_score"] is None


def test_tracker_analysis_contract_failed_run_is_not_serialized_as_zero_scores() -> None:
    item = _format(
        {
            "analyzer_run_id": 9001,
            "analyzer_run_status": "failed",
            "analysis_error_code": "parse_failed",
            "analysis_error_message": "Could not parse analyzer JSON",
        }
    )

    assert item["analysis_status"] == "failed"
    assert item["analysis_summary"] is None
    assert item["analysis"]["status"] == "failed"
    assert item["analysis"]["run_id"] == 9001
    assert item["analysis"]["error_code"] == "parse_failed"
    assert item["analysis"]["scores_explicit"] is False


def test_tracker_analysis_contract_completed_nullable_metrics_are_partial_not_zero() -> None:
    item = _format(
        {
            "analysis_id": 456,
            "analysis_status": "done",
            "analyzer_model": "deepseek-test",
            "geo_score": None,
            "visibility_score": 0,
            "sentiment_score": None,
            "mentions_count": 4,
            "citations_count": None,
            "features_count": 2,
        }
    )

    assert item["analysis_status"] == "done"
    assert item["analysis"]["status"] == "completed"
    assert item["analysis"]["score_source"] == "response_analyses_partial"
    assert item["analysis"]["scores_explicit"] is False
    assert item["analysis"]["geo_score"] is None
    assert item["analysis"]["visibility_score"] == 0
    assert item["analysis"]["sentiment_score"] is None
    assert item["analysis_summary"]["scores_explicit"] is False
    assert item["analysis_summary"]["geo_score"] is None
    assert item["analysis_summary"]["visibility_score"] == 0


def test_tracker_analysis_contract_defaulted_all_zero_metrics_are_not_explicit() -> None:
    item = _format(
        {
            "analysis_id": 459,
            "analysis_status": "done",
            "geo_score": 0,
            "visibility_score": 0,
            "sentiment_score": 0,
            "sov_score": 0,
            "citation_score": 0,
            "mentions_count": 0,
            "citations_count": 0,
            "features_count": 0,
        }
    )

    assert item["analysis"]["status"] == "defaulted"
    assert item["analysis"]["score_source"] == "response_analyses_defaulted"
    assert item["analysis"]["has_analyzer_evidence"] is False
    assert item["analysis"]["scores_explicit"] is False
    assert item["analysis_summary"]["status"] == "defaulted"
    assert item["analysis_summary"]["score_source"] == "response_analyses_defaulted"
    assert item["analysis_summary"]["scores_explicit"] is False
    assert item["analysis_summary"]["geo_score"] == 0
    assert item["analysis_summary"]["visibility_score"] == 0
    assert item["analysis_summary"]["sentiment_score"] == 0


def test_tracker_analysis_contract_completed_true_zero_metrics_are_explicit() -> None:
    item = _format(
        {
            "analysis_id": 457,
            "analysis_status": "done",
            "analyzer_run_id": 9002,
            "analyzer_run_status": "done",
            "geo_score": 0,
            "visibility_score": 0,
            "sentiment_score": 0,
            "sov_score": 0,
            "citation_score": 0,
            "mentions_count": 0,
            "citations_count": 0,
            "features_count": 0,
        }
    )

    assert item["analysis"]["status"] == "completed"
    assert item["analysis"]["score_source"] == "response_analyses"
    assert item["analysis"]["has_analyzer_evidence"] is True
    assert item["analysis"]["scores_explicit"] is True
    assert item["analysis_summary"]["scores_explicit"] is True
    assert item["analysis_summary"]["geo_score"] == 0
    assert item["analysis_summary"]["visibility_score"] == 0
    assert item["analysis_summary"]["sentiment_score"] == 0


def test_tracker_analysis_contract_completed_nonzero_metrics_are_explicit() -> None:
    item = _format(
        {
            "analysis_id": 458,
            "analysis_status": "done",
            "geo_score": 0.82,
            "visibility_score": 0.5,
            "sentiment_score": 0.25,
            "mentions_count": 3,
            "citations_count": 2,
            "features_count": 6,
        }
    )

    assert item["analysis"]["status"] == "completed"
    assert item["analysis"]["score_source"] == "response_analyses"
    assert item["analysis"]["scores_explicit"] is True
    assert item["analysis_summary"]["geo_score"] == 0.82
    assert item["analysis_summary"]["visibility_score"] == 0.5
    assert item["analysis_summary"]["sentiment_score"] == 0.25
