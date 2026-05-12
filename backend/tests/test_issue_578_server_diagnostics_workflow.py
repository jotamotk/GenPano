from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/server-diagnostics.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy.yml"


def test_bestcoffer_batch_repair_preserves_response_rows_and_records_reason() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "repair_stale_running" in workflow
    assert 'case "${REPAIR_STALE_RUNNING}" in' in workflow
    assert '*) fail "REPAIR_STALE_RUNNING must be true or false" ;;' in workflow
    assert (
        '[[ "${STALE_RUNNING_TTL_SECONDS}" =~ ^[0-9]+$ ]] || fail '
        '"STALE_RUNNING_TTL_SECONDS must be an integer"'
    ) in workflow
    assert (
        '[ "${STALE_RUNNING_TTL_SECONDS}" -ge 60 ] || fail '
        '"STALE_RUNNING_TTL_SECONDS must be >= 60"'
    ) in workflow
    assert (
        '[ "${STALE_RUNNING_TTL_SECONDS}" -le 604800 ] || fail '
        '"STALE_RUNNING_TTL_SECONDS must be <= 604800"'
    ) in workflow
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


def test_deploy_does_not_write_placeholder_clash_api_secret_to_worker_env() -> None:
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    diagnostics = WORKFLOW.read_text(encoding="utf-8")

    assert "CLASH_API_SECRET=${{ secrets.CLASH_API_SECRET || vars.CLASH_API_SECRET || 'set-your-secret' }}" not in deploy
    assert "CLASH_API_SECRET=${{ secrets.CLASH_API_SECRET || vars.CLASH_API_SECRET }}" in deploy
    assert "Authorization: Bearer set-your-secret" not in deploy
    assert "Authorization: Bearer set-your-secret" not in diagnostics


def test_chatgpt_proxy_preflight_heredoc_starts_at_column_zero() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]

    assert "docker compose exec -T worker python - <<'PY' || true\nimport asyncio" in run_script
    assert "\nPY\n    docker compose exec -T worker sh -lc" in run_script
