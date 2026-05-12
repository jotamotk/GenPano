import os
import shlex
import shutil
import subprocess
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
