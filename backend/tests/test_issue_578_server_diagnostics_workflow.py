import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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


def test_bestcoffer_batch_retrieves_artifacts_before_returning_remote_status() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]

    capture_status = "remote_status=${PIPESTATUS[0]}"
    retrieve_artifact = (
        '"${SERVER_USER}@${SERVER_HOST}:/tmp/genpano_scraper_batch_${GH_RUN_ID}.tar.gz"'
    )
    return_remote_status = 'exit "${remote_status}"'

    assert capture_status in run_script
    assert 'if [ "${remote_status}" -ne 0 ]; then' in run_script
    assert return_remote_status in run_script
    assert run_script.index(capture_status) < run_script.index(retrieve_artifact)
    assert run_script.index(retrieve_artifact) < run_script.index(return_remote_status)


def test_bestcoffer_batch_failure_path_still_fetches_manifest(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash is required to simulate the GitHub Actions shell")
    bash_probe = subprocess.run(
        ["bash", "-lc", "command -v bash >/dev/null"],
        capture_output=True,
        check=False,
    )
    if bash_probe.returncode != 0:
        pytest.skip("bash is not usable in this local environment")

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    trace = tmp_path / "trace.log"
    fake_commands = {
        "ssh-keyscan": 'echo keyscan >> "$TRACE_FILE"\nexit 0\n',
        "ssh": 'cat >/dev/null\necho ssh >> "$TRACE_FILE"\nexit 2\n',
        "scp": (
            'echo scp >> "$TRACE_FILE"\n'
            "mkdir -p scraper-batch-artifacts\n"
            "touch scraper-batch-artifacts/genpano_scraper_batch_${GH_RUN_ID}.tar.gz\n"
            "exit 0\n"
        ),
        "tar": 'echo manifest >> "$TRACE_FILE"\necho audit.csv\nexit 0\n',
    }
    for name, body in fake_commands.items():
        command = bin_dir / name
        command.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
        command.chmod(0o755)

    if os.name == "nt":
        bash_bin_dir = subprocess.check_output(
            ["bash", "-lc", f"cygpath -u {shlex.quote(str(bin_dir))}"],
            encoding="utf-8",
        ).strip()
        bash_trace = subprocess.check_output(
            ["bash", "-lc", f"cygpath -u {shlex.quote(str(trace))}"],
            encoding="utf-8",
        ).strip()
    else:
        bash_bin_dir = str(bin_dir)
        bash_trace = str(trace)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bash_bin_dir}:{env['PATH']}",
            "TRACE_FILE": bash_trace,
            "SERVER_HOST": "example.invalid",
            "SERVER_USER": "deploy",
            "SERVER_SSH_KEY": "fake-key",
            "BRAND_ID": "12",
            "BATCH_LIMIT": "3",
            "EXECUTE_BATCH": "true",
            "POLL_SECONDS": "1",
            "TARGET_LLM": "chatgpt",
            "REPAIR_STALE_RUNNING": "false",
            "STALE_RUNNING_TTL_SECONDS": "3600",
            "REDACT_BESTCOFFER_PAYLOAD_ARTIFACTS": "true",
            "GH_RUN_ID": "25751875032",
        }
    )

    result = subprocess.run(
        ["bash", "-lc", run_script],
        cwd=tmp_path,
        env=env,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert trace.read_text(encoding="utf-8").splitlines() == [
        "keyscan",
        "ssh",
        "scp",
        "manifest",
    ]


def test_bestcoffer_batch_audit_failures_make_remote_batch_nonzero() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]

    assert "=== Enforce selected batch status semantics ===" in run_script
    assert "batch_status_semantics_failed.txt" in run_script
    assert "terminal_failed_status" in run_script
    assert "failing_qa_auto_verdict" in run_script
    assert "missing_response_id" in run_script
    assert "missing_response_text" in run_script
    assert "sys.exit(3)" in run_script

    redaction_marker = "=== Redact payload-bearing bestCoffer artifacts ==="
    semantics_marker = "=== Enforce selected batch status semantics ==="
    execute_guard = 'if [ "${EXECUTE_BATCH}" = "true" ]; then'
    remote_end = "\nREMOTE\n"
    assert run_script.index(redaction_marker) < run_script.index(semantics_marker)
    assert run_script.rindex(execute_guard, 0, run_script.index(semantics_marker))
    assert run_script.index(semantics_marker) < run_script.index(remote_end)


def test_bestcoffer_batch_preview_skips_status_semantics_gate() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]

    semantics_marker = "=== Enforce selected batch status semantics ==="
    skip_marker = "=== Skip selected batch status semantics for preview ==="
    gate_start = run_script.rindex(
        'if [ "${EXECUTE_BATCH}" = "true" ]; then',
        0,
        run_script.index(semantics_marker),
    )
    gate_end = run_script.index("\nREMOTE", gate_start)
    gate_block = run_script[gate_start:gate_end]

    assert skip_marker in gate_block
    assert "batch_status_semantics_skipped.txt" in gate_block
    assert "execute_batch=false candidate preview does not dispatch selected rows" in gate_block
    assert gate_block.index(semantics_marker) < gate_block.index(skip_marker)


def test_bestcoffer_batch_audit_gate_flags_failed_rows_and_missing_response(
    tmp_path: Path,
) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]
    marker = 'python3 - "${artifact_dir}/audit.csv"'
    block_start = run_script.index(marker)
    code_start = run_script.index("<<'PY'\n", block_start) + len("<<'PY'\n")
    code_end = run_script.index("\nPY", code_start)
    gate_code = run_script[code_start:code_end]

    audit = tmp_path / "audit.csv"
    failure_note = tmp_path / "batch_status_semantics_failed.txt"
    audit.write_text(
        "\n".join(
            [
                "query_id,target_llm,status,retry_reason,response_id,response_len,qa_auto_verdict",
                "184406,doubao,failed,doubao_not_logged_in,,0,FAIL_NO_RESPONSE",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-c", gate_code, str(audit), str(failure_note)],
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    failure_text = failure_note.read_text(encoding="utf-8")
    assert "query_id=184406" in failure_text
    assert "terminal_failed_status" in failure_text
    assert "failing_qa_auto_verdict" in failure_text
    assert "missing_response_id" in failure_text
    assert "missing_response_text" in failure_text


def test_doubao_auth_false_success_repair_mode_is_guarded_and_artifacted() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "doubao_auth_false_success_repair" in workflow
    assert "doubao_auth_repair_apply" in workflow
    assert 'case "${DOUBAO_AUTH_REPAIR_APPLY}" in' in workflow
    assert '*) fail "DOUBAO_AUTH_REPAIR_APPLY must be true or false" ;;' in workflow
    assert 'if [ "${DOUBAO_AUTH_REPAIR_APPLY}" = "true" ]; then' in workflow
    assert (
        "docker compose exec -T worker python -m "
        "geo_tracker.tasks.doubao_auth_false_success_repair "
        '--approval-ref "Refs #594 dry-run:${GH_RUN_ID}"'
    ) in workflow
    assert (
        "docker compose exec -T worker python -m "
        "geo_tracker.tasks.doubao_auth_false_success_repair --apply "
        '--approval-ref "Refs #594:${GH_RUN_ID}"'
    ) in workflow
    assert "doubao-auth-false-success-repair-${{ github.run_id }}" in workflow
    assert "doubao-auth-repair-artifacts" in workflow
    assert "repair-output.json" in workflow
    assert "python3 - <<'PY' > doubao-auth-repair-artifacts/rollback.sql" in workflow
    assert "rollback" in workflow.lower()


def test_server_diagnostics_preserves_live_app_analytics_mode() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "app_analytics_business_completeness" in workflow
    assert "live-app-analytics-business-completeness-e2e" in workflow
    assert "FROM_DATE" in workflow
    assert "TO_DATE" in workflow


def test_deploy_does_not_write_placeholder_clash_api_secret_to_worker_env() -> None:
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    diagnostics = WORKFLOW.read_text(encoding="utf-8")
    placeholder_secret_env = (
        "CLASH_API_SECRET=${{ secrets.CLASH_API_SECRET || "
        "vars.CLASH_API_SECRET || 'set-your-secret' }}"
    )

    assert placeholder_secret_env not in deploy
    assert "CLASH_API_SECRET=${{ secrets.CLASH_API_SECRET || vars.CLASH_API_SECRET }}" in deploy
    assert "Authorization: Bearer set-your-secret" not in deploy
    assert "Authorization: Bearer set-your-secret" not in diagnostics


def test_chatgpt_proxy_preflight_heredoc_starts_at_column_zero() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]

    assert "docker compose exec -T worker python - <<'PY' || true\nimport asyncio" in run_script
    assert "\nPY\n    docker compose exec -T worker sh -lc" in run_script


def test_bestcoffer_batch_writes_chatgpt_citation_review_artifact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "citation_review.jsonl" in workflow
    assert "citation_not_applicable" in workflow
    assert "source_markers_without_extractable_urls" in workflow


def test_bestcoffer_batch_issue_697_artifacts_do_not_export_raw_payloads() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]
    audit_block = run_script[
        run_script.index("=== Final response/citation audit CSV ===") : run_script.index(
            "=== Export current batch responses JSONL ==="
        )
    ]
    responses_block = run_script[
        run_script.index("=== Export current batch responses JSONL ===") : run_script.index(
            "=== Collect current batch worker logs ==="
        )
    ]

    assert "response_preview" not in audit_block
    assert "REGEXP_REPLACE(LEFT(COALESCE(latest.raw_text" not in audit_block
    assert "'query_text'" not in responses_block
    assert "'response_text'" not in responses_block
    assert "'citations'" not in responses_block
    assert "query_text_hash" in responses_block
    assert "response_text_hash" in responses_block
    assert "citation_payload_hash" in responses_block
    assert "REDACT_BESTCOFFER_PAYLOAD_ARTIFACTS" in run_script
    assert "payload_artifacts_redacted.txt" in run_script
    assert "payload_logs_redacted.txt" in run_script
    assert "-name '*.html'" in run_script
    assert "-name '*.png'" in run_script


def test_query_evidence_mode_collects_exact_readonly_citation_artifacts() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    inputs = workflow["on" if "on" in workflow else True]["workflow_dispatch"]["inputs"]

    assert "query_evidence" in inputs["scraper_mode"]["description"]
    assert inputs["diagnostic_query_id"]["default"] == "185003"
    assert inputs["diagnostic_log_since_utc"]["default"] == "2026-05-14 05:32:00 UTC"
    assert inputs["diagnostic_log_until_utc"]["default"] == "2026-05-14 05:34:30 UTC"

    steps = workflow["jobs"]["diagnostics"]["steps"]
    query_step = next(
        step for step in steps if step.get("name") == "Run exact query evidence diagnostics"
    )
    upload_step = next(
        step for step in steps if step.get("name") == "Upload exact query evidence artifacts"
    )
    run_script = query_step["run"]

    assert query_step["if"] == "${{ inputs.scraper_mode == 'query_evidence' }}"
    assert upload_step["if"] == "${{ always() && inputs.scraper_mode == 'query_evidence' }}"
    assert "read_only=true" in run_script
    assert "mutations_attempted=false" in run_script
    assert "QUERY_ID" in run_script
    assert '[ "${QUERY_ID}" -ge 1 ] || fail' in run_script
    assert "SELECT" in run_script
    assert "UPDATE " not in run_script
    assert "DELETE " not in run_script
    assert "INSERT " not in run_script
    assert "redis-cli" not in run_script
    assert "execute_query" not in run_script
    assert "citation_sources" in run_script
    assert "response_html_marker_summary.json" in run_script
    assert "artifact-file-summary.jsonl" in run_script
    assert "query_${QUERY_ID}_*" in run_script
    assert "screenshot-paths.txt" in run_script
    assert "docker compose cp" in run_script
    assert "entry-btn-v3" in run_script
    assert "container-outer" in run_script
    assert "search-item-" in run_script
    assert "search-reference-ui-v3" in run_script
    assert "data-href" in run_script
    assert "python3 -c" in run_script
    assert "sys.stdin.read()" in run_script
    assert "docker compose logs --since" in run_script
