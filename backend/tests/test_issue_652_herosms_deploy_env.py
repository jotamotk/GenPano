from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy.yml"
SERVER_DIAGNOSTICS_WORKFLOW = REPO_ROOT / ".github/workflows/server-diagnostics.yml"


def test_deploy_propagates_hero_sms_api_key_without_printing_value() -> None:
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "HERO_SMS_API_KEY: ${{ secrets.HERO_SMS_API_KEY }}" in deploy
    assert (
        "envs: GEMINI_COOKIES_JSON,DOUBAO_COOKIES_JSON,ACR_REGISTRY_SECRET,"
        "ACR_USERNAME,ACR_PASSWORD,CLASH_API_SECRET,HERO_SMS_API_KEY"
    ) in deploy
    assert "print('HERO_SMS_API_KEY=' + value.replace('$', '$$'))" in deploy
    assert '"HERO_SMS_API_KEY_present": bool(os.getenv("HERO_SMS_API_KEY"))' in deploy
    assert 'print(os.getenv("HERO_SMS_API_KEY"' not in deploy


def test_server_diagnostics_has_readonly_hero_sms_runtime_check() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["diagnostics"]["steps"]
    diagnostic_step = next(
        step for step in steps if step.get("name") == "Run ChatGPT SMS env check"
    )
    run_script = diagnostic_step["run"]

    assert "chatgpt_sms_env_check" in workflow_text
    assert "hero-sms-env-${{ github.run_id }}" in workflow_text
    assert "hero-sms-env-artifacts/runtime-env.json" in workflow_text
    assert "docker compose exec -T worker python - <<'PY'" in run_script
    assert '"HERO_SMS_API_KEY_present": bool(os.getenv("HERO_SMS_API_KEY"))' in run_script
    assert '"service": "dr"' in run_script
    assert '"country": "187"' in run_script
    assert '"operator": "physic"' in run_script
    assert '"price_bucket": "usd<=0.60"' in run_script
    assert '"countPhysical": None' in run_script
    assert '"purchaseAttempted": False' in run_script
    assert '"purchaseEndpointsCalled": False' in run_script
    assert 'print(os.getenv("HERO_SMS_API_KEY"' not in run_script
    assert "HERO_SMS_API_KEY=" not in run_script


def test_server_diagnostics_sanitizes_captured_worker_logs() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")

    assert "sanitize_herosms_logs" in workflow_text
    assert "api key [redacted]" in workflow_text
    assert "HERO_SMS_API_KEY=" not in workflow_text
