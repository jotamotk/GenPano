import json
import subprocess
from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def _admin_account_redaction_helper(html: str) -> str:
    return html[
        html.index("function redactAccountUiText(value)") : html.index(
            "function accountTaskFailureErrorBody(body)"
        )
    ]


def _redact_with_admin_helper(html: str, value: str) -> str:
    script = (
        _admin_account_redaction_helper(html)
        + "\nconst input = "
        + json.dumps(value, ensure_ascii=False)
        + ";\nprocess.stdout.write(JSON.stringify(redactAccountUiText(input)));"
    )
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_admin_accounts_surface_expired_recovery_state() -> None:
    html = _admin_html()

    assert "expired: 'expired'" in html
    assert "accountStatusMeta(status)" in html
    assert "已过期 · 可恢复" in html
    assert "expired: 0" in html
    assert "else if (a.status === 'expired') b.expired++;" in html


def test_admin_accounts_filter_expired_with_canonical_api() -> None:
    html = _admin_html()

    assert "accountStatusFilter: 'all'" in html
    assert "setAccountStatusFilter(status)" in html
    assert "fetchAccounts(status)" in html
    assert "API_BASE + '/admin/accounts'" in html
    assert "qp.set('status', status)" in html


def test_admin_accounts_recovery_copy_is_pending_and_redacted() -> None:
    html = _admin_html()
    pending_copy = "恢复任务已提交" + "\uff0c" + "等待后台处理"

    assert "triggerAccountRecovery(a)" in html
    assert pending_copy in html
    assert "需要人工处理" in html
    assert "redactAccountUiText" in html
    assert "r.phone ? ' (' + r.phone + ')'" not in html


def test_admin_accounts_task_failure_panel_payload_is_redacted() -> None:
    html = _admin_html()

    assert "function accountTaskFailureErrorBody(body)" in html
    assert "const taskFailure = accountTaskFailureErrorBody(body);" in html
    assert "code: taskFailure.code" in html
    assert "title: taskFailure.title" in html
    assert "detail: taskFailure.detail" in html
    assert "payload.copyText = this.formatErrorCopy(payload);" in html

    redaction_helper = html[
        html.index("function redactAccountUiText(value)") : html.index(
            "function accountTaskResultMessage(result)"
        )
    ]
    for pattern in (
        "api[_-]?key",
        "provider[_-]?secret",
        "sms[_-]?text",
        "verification[_-]?code",
        r"\+?\d[\d\s().-]{6,}\d",
        "cookies?",
        "localStorage",
        "token",
        "activation[_-]?id",
    ):
        assert pattern in redaction_helper

    task_failure_helper = html[
        html.index("function accountTaskFailureErrorBody(body)") : html.index(
            "function accountTaskResultMessage(result)"
        )
    ]
    assert "code: redactAccountUiText(raw.code || raw.error || 'task_failed')" in (
        task_failure_helper
    )
    assert "title: redactAccountUiText(raw.title || raw.error || '账号任务失败')" in (
        task_failure_helper
    )
    assert "detail: redactAccountUiText(detail)" in task_failure_helper

    failure_branch = html[
        html.index("const taskFailure = accountTaskFailureErrorBody(body);") : html.index(
            "path: 'task:' + (body.task_id || '')"
        )
    ]
    assert "body.code || body.error" not in failure_branch
    assert "body.title || body.error" not in failure_branch
    assert "body.traceback || body.detail || body.message" not in failure_branch


def test_admin_accounts_redaction_masks_json_quoted_task_payloads() -> None:
    html = _admin_html()

    samples = {
        (
            '{"cookies":"raw-cookie","token":"raw-token",'
            '"activation_id":"raw-activation","api_key":"raw-api",'
            '"provider_secret":"raw-provider"}'
        ): (
            "raw-cookie",
            "raw-token",
            "raw-activation",
            "raw-api",
            "raw-provider",
        ),
        '{"localStorage":{"auth":"raw-local","nested":{"token":"raw-nested"}}}': (
            "raw-local",
            "raw-nested",
        ),
        "HERO_SMS_API_KEY=raw-key sms_text=123456 +14155552671": (
            "raw-key",
            "123456",
            "+14155552671",
        ),
    }
    for raw_text, raw_values in samples.items():
        redacted = _redact_with_admin_helper(html, raw_text)
        for raw_value in raw_values:
            assert raw_value not in redacted
