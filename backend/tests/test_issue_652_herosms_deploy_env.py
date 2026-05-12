from pathlib import Path
import importlib.util

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy.yml"
SERVER_DIAGNOSTICS_WORKFLOW = REPO_ROOT / ".github/workflows/server-diagnostics.yml"
SANITIZER_SCRIPT = REPO_ROOT / "scripts/sanitize_herosms_logs.py"


def _load_sanitizer_module():
    spec = importlib.util.spec_from_file_location(
        "sanitize_herosms_logs",
        SANITIZER_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
    assert "scripts/sanitize_herosms_logs.py" in workflow_text
    assert "HERO_SMS_API_KEY=" not in workflow_text


def test_herosms_log_sanitizer_redacts_sample_stdout_and_artifact_text() -> None:
    sanitizer = _load_sanitizer_module()
    unsafe = (
        "HTTP Request: GET https://hero-sms.example/stubs/handler_api.php?"
        "action=getNumber&service=dr&country=187&api_key=unit-secret "
        "HERO_SMS_API_KEY=unit-secret operator=physic countPhysical=5"
    )

    safe = sanitizer.sanitize_text(unsafe)

    assert "unit-secret" not in safe
    assert "api_key=" not in safe
    assert "HERO_SMS_API_KEY=" not in safe
    assert "api key [redacted]" in safe
    assert "HERO_SMS_API_KEY_present=true" in safe
    assert "service=dr" in safe
    assert "country=187" in safe
    assert "operator=physic" in safe
    assert "countPhysical=5" in safe


def test_server_diagnostics_worker_stdout_log_streams_are_sanitized() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")

    assert "sanitize_herosms_stream()" in workflow_text
    assert (
        "docker compose logs --since '2026-05-11T08:07:00' "
        "--until '2026-05-11T08:11:00' worker worker-analysis backend nginx "
        "2>&1 | sanitize_herosms_stream || true"
    ) in workflow_text
    assert (
        "docker compose logs --tail=260 worker worker-analysis beat "
        "2>&1 | sanitize_herosms_stream || true"
    ) in workflow_text
    assert (
        "docker compose logs --since '2026-05-11T08:07:00' "
        "--until '2026-05-11T08:11:00' worker worker-analysis backend nginx || true"
    ) not in workflow_text
    assert "docker compose logs --tail=260 worker worker-analysis beat || true" not in workflow_text
