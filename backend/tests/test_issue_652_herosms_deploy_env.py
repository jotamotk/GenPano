import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy.yml"
SERVER_DIAGNOSTICS_WORKFLOW = REPO_ROOT / ".github/workflows/server-diagnostics.yml"
SANITIZER_SCRIPT = REPO_ROOT / "scripts/sanitize_herosms_logs.py"
GATE4_UNSAFE_SAMPLE = (
    "HTTP Request: GET https://hero-sms.example/stubs/handler_api.php?"
    "action=getNumber&service=dr&country=187&api_key=unit-secret"
    "&phone=+15551234567 "
    "apikey=unit-apikey token=unit-token secret=unit-secret "
    "authorization=unit-auth auth=unit-auth-short cookie=unit-cookie-assignment "
    "set-cookie=unit-set-cookie-assignment "
    "Authorization: Bearer unit-bearer Auth: Bearer unit-auth-header "
    "Cookie: session=unit-cookie; "
    "Set-Cookie: hero=unit-set-cookie; phone=+15551234567 "
    "msisdn=15551234567 sms_text='Your login code is 654321' "
    'message="Use 112233" body=BodySecret code=998877 '
    "activation_id=123456789 activation_ref=unit-activation-ref "
    "activation_secret=unit-activation-secret activation_code=445566 "
    "service=dr country=187 operator=physic countPhysical=5"
)
GATE4_FORBIDDEN_SUBSTRINGS = [
    "hero-sms.example",
    "handler_api.php",
    "action=getNumber",
    "api_key=",
    "unit-secret",
    "unit-apikey",
    "unit-token",
    "unit-auth",
    "unit-auth-short",
    "unit-auth-header",
    "unit-cookie-assignment",
    "unit-set-cookie-assignment",
    "unit-bearer",
    "unit-cookie",
    "unit-set-cookie",
    "+15551234567",
    "15551234567",
    "654321",
    "112233",
    "BodySecret",
    "998877",
    "123456789",
    "unit-activation-ref",
    "unit-activation-secret",
    "445566",
]


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


def _inline_sanitizer_sources() -> list[str]:
    workflow = yaml.safe_load(SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["diagnostics"]["steps"]
    scripts = [
        steps[0]["run"],
        next(step for step in steps if step.get("name") == "Run Doubao SMS forensics")["run"],
        next(step for step in steps if step.get("name") == "Run read-only diagnostics")["with"][
            "script"
        ],
    ]
    sources = []
    start = "cat > \"${sanitizer_py}\" <<'PY'\n"
    end = "\nPY\nchmod 700"
    for script in scripts:
        assert start in script
        assert end in script
        sources.append(script.split(start, 1)[1].split(end, 1)[0])
    return sources


def _assert_gate4_sanitized(safe: str) -> None:
    for forbidden in GATE4_FORBIDDEN_SUBSTRINGS:
        assert forbidden not in safe

    assert "[HeroSMS URL redacted]" in safe
    assert "[phone redacted]" in safe
    assert "[secret redacted]" in safe
    assert "[SMS field redacted]" in safe
    assert "[activation field redacted]" in safe
    assert "operator=physic" in safe
    assert "countPhysical=5" in safe


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


def test_server_diagnostics_has_readonly_doubao_sms_forensics_mode() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    workflow_dispatch = workflow.get("on", workflow.get(True))["workflow_dispatch"]
    inputs = workflow_dispatch["inputs"]
    steps = workflow["jobs"]["diagnostics"]["steps"]
    diagnostic_step = next(step for step in steps if step.get("name") == "Run Doubao SMS forensics")
    run_script = diagnostic_step["run"]

    assert "doubao_sms_forensics" in workflow_text
    assert "doubao_sms_since_utc" in inputs
    assert "doubao_sms_until_utc" in inputs
    assert "doubao_sms_phone_suffixes" in inputs
    assert "docker compose exec -T postgres psql" in run_script
    assert "llm_accounts" in run_script
    assert "cookies_json IS NOT NULL" in run_script
    assert "phone_suffix" in run_script
    assert "sanitize_herosms_stream" in run_script
    assert "cat > \"${sanitizer_py}\" <<'PY'" in run_script
    assert "scripts/sanitize_herosms_logs.py" not in run_script
    assert 'if [ "${BASH_SUBSHELL:-0}" != "0" ]; then' in run_script
    assert "docker compose logs --since" in run_script
    assert "queue-lengths.txt" in run_script
    assert "journal-docker-window.txt" in run_script
    assert "compose-window.log" in run_script
    assert "compose-current-tail.log" in run_script

    forbidden_write_or_sms_triggers = [
        "UPDATE ",
        "DELETE ",
        "INSERT ",
        "TRUNCATE ",
        "trigger_sms_register",
        "sms_register",
        "auto_login.delay",
        "getKeywordSms",
        "reserve_number(",
    ]
    for forbidden in forbidden_write_or_sms_triggers:
        assert forbidden not in run_script


def test_server_diagnostics_sanitizes_captured_worker_logs() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    run_script = workflow["jobs"]["diagnostics"]["steps"][0]["run"]
    sanitizer_selftest = "sanitizer_probe=\"$(sanitize_herosms_stream <<'EOF'"
    collect_worker_logs = (
        'docker compose logs --since "${utc_started_at}" worker worker-analysis beat'
    )

    assert "sanitize_herosms_logs" in workflow_text
    assert "scripts/sanitize_herosms_logs.py" not in run_script
    assert sanitizer_selftest in run_script
    assert "handler_api.php" in run_script
    assert "selftest-activation-secret" in run_script
    assert "selftest-auth-short" in run_script
    assert "selftest-auth-header" in run_script
    assert "selftest-cookie" in run_script
    assert "+15551234567" in run_script
    assert "654321" in run_script
    assert run_script.index(sanitizer_selftest) < run_script.index(collect_worker_logs)
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
    assert "[HeroSMS URL redacted]" in safe
    assert "HERO_SMS_API_KEY_present=true" in safe
    assert "operator=physic" in safe
    assert "countPhysical=5" in safe


def test_herosms_log_sanitizer_redacts_gate4_sensitive_values() -> None:
    sanitizer = _load_sanitizer_module()

    safe = sanitizer.sanitize_text(GATE4_UNSAFE_SAMPLE)

    _assert_gate4_sanitized(safe)


def test_workflow_inline_herosms_sanitizers_redact_gate4_sensitive_values() -> None:
    for index, source in enumerate(_inline_sanitizer_sources()):
        namespace = {"__name__": f"inline_sanitizer_{index}"}
        exec(compile(source, f"inline_sanitizer_{index}.py", "exec"), namespace)

        safe = namespace["sanitize_text"](GATE4_UNSAFE_SAMPLE)

        _assert_gate4_sanitized(safe)


def test_server_diagnostics_worker_stdout_log_streams_are_sanitized() -> None:
    workflow_text = SERVER_DIAGNOSTICS_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    diagnostic_step = next(
        step
        for step in workflow["jobs"]["diagnostics"]["steps"]
        if step.get("name") == "Run read-only diagnostics"
    )
    run_script = diagnostic_step["with"]["script"]
    sanitizer_selftest = "sanitizer_probe=\"$(sanitize_herosms_stream <<'EOF'"
    first_worker_log = (
        "docker compose logs --since '2026-05-11T08:07:00' "
        "--until '2026-05-11T08:11:00' worker worker-analysis backend nginx"
    )

    assert "sanitize_herosms_stream()" in workflow_text
    assert "scripts/sanitize_herosms_logs.py" not in run_script
    assert sanitizer_selftest in run_script
    assert "handler_api.php" in run_script
    assert "selftest-activation-secret" in run_script
    assert "selftest-auth-short" in run_script
    assert "selftest-auth-header" in run_script
    assert "selftest-cookie" in run_script
    assert "+15551234567" in run_script
    assert "654321" in run_script
    assert run_script.index(sanitizer_selftest) < run_script.index(first_worker_log)
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
