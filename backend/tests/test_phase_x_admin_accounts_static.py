from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


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
