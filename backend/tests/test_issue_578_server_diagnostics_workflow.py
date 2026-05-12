from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/server-diagnostics.yml"


def test_bestcoffer_batch_repair_preserves_response_rows_and_records_reason() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "repair_stale_running" in workflow
    assert "LOWER(q.status) = 'running'" in workflow
    assert "SELECT 1 FROM llm_responses r WHERE r.query_id = q.id" in workflow
    assert "retry_reason = 'stale_running_timeout:${GH_RUN_ID}'" in workflow
    assert "Post-repair query/response counters" in workflow
    assert "Rollback note:" in workflow


def test_bestcoffer_candidate_selection_only_retries_terminal_no_response_rows() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "AND LOWER(q.status) IN ('pending', 'failed')" in workflow
    assert "SELECT 1 FROM llm_responses r WHERE r.query_id = q.id" in workflow
    assert "retry_reason = 'bestcoffer_batch_audit:${GH_RUN_ID}'" in workflow


def test_server_diagnostics_preserves_live_app_analytics_mode() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "app_analytics_business_completeness" in workflow
    assert "live-app-analytics-business-completeness-e2e" in workflow
    assert "FROM_DATE" in workflow
    assert "TO_DATE" in workflow
