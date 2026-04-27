"""Admin transactional email — Resend client + zh-CN/en-US templates.

Decision #24.B + PRD §4.10.4a: every admin-facing transactional email
ships in zh-CN and en-US. The locale is selected per-call (defaults to
zh-CN per Frank's MVP audience). Sending two languages for the same
event is forbidden — pick one based on the user's profile.

`ADMIN_BASE_URL` env var supplies the front-end origin used in reset /
invitation links. When unset (typical local dev) the helper falls back
to `http://localhost:5173` (Vite default), matching what the master TS
implementation did so that QA workflows stay identical.

Network IO is gated behind `_get_resend_client()` so the unit tests can
patch the import boundary; in production it is a thin wrapper around
the official `resend` SDK if installed, or a noop logger if not (the
Phase Gate flow does not require live mail in CI).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

EmailLocale = Literal["zh-CN", "en-US"]
_DEFAULT_LOCALE: EmailLocale = "zh-CN"
_ADMIN_BASE_URL_FALLBACK = "http://localhost:5173"
_FROM_ADDRESS_DEFAULT = "GenPano Admin <admin@genpano.com>"


@dataclass(frozen=True)
class EmailResult:
    """Outcome of a send attempt — `delivered=False` only when the SDK is
    unavailable (CI / local without Resend creds)."""

    delivered: bool
    provider_message_id: str | None
    locale: EmailLocale


class ResendLike(Protocol):
    """Subset of the `resend.Emails` interface we exercise — typed so the
    test suite can pass a `Mock` and mypy --strict still passes."""

    def send(self, params: dict[str, Any]) -> dict[str, Any]: ...


def _admin_base_url() -> str:
    return os.environ.get("ADMIN_BASE_URL") or _ADMIN_BASE_URL_FALLBACK


def _from_address() -> str:
    return os.environ.get("ADMIN_EMAIL_FROM") or _FROM_ADDRESS_DEFAULT


def _get_resend_client() -> ResendLike | None:
    """Return a Resend client when API key + SDK are present, else None.

    Returning None deliberately — the email helper logs a structured
    line and reports `delivered=False`. In CI this keeps the email
    flow exercised without leaking secrets or hitting the network.
    """

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return None
    try:
        import resend  # type: ignore[import-not-found]
    except ImportError:
        return None
    resend.api_key = api_key
    client: ResendLike = resend.Emails
    return client


def _build_password_reset(
    *,
    locale: EmailLocale,
    reset_url: str,
) -> tuple[str, str, str]:
    if locale == "en-US":
        subject = "Reset your GenPano admin password"
        text = (
            "We received a request to reset your GenPano admin password.\n\n"
            f"Reset link (valid for 24h): {reset_url}\n\n"
            "If you did not request this, ignore this email."
        )
        html = (
            "<p>We received a request to reset your GenPano admin password.</p>"
            f'<p><a href="{reset_url}">Reset password</a> (valid for 24h)</p>'
            "<p>If you did not request this, ignore this email.</p>"
        )
        return subject, text, html

    # zh-CN
    subject = "重置 GenPano 管理员密码"
    text = (
        "我们收到了重置您 GenPano 管理员密码的请求。\n\n"
        f"重置链接 (24 小时内有效): {reset_url}\n\n"
        "如果您没有发起此请求, 请忽略此邮件。"
    )
    html = (
        "<p>我们收到了重置您 GenPano 管理员密码的请求。</p>"
        f'<p><a href="{reset_url}">重置密码</a> (24 小时内有效)</p>'
        "<p>如果您没有发起此请求, 请忽略此邮件。</p>"
    )
    return subject, text, html


def _build_invitation(
    *,
    locale: EmailLocale,
    invite_url: str,
    inviter_email: str,
) -> tuple[str, str, str]:
    if locale == "en-US":
        subject = "You've been invited to GenPano admin"
        text = (
            f"{inviter_email} has invited you to the GenPano admin console.\n\n"
            f"Set your password (valid for 24h): {invite_url}\n"
        )
        html = (
            f"<p>{inviter_email} has invited you to the GenPano admin console.</p>"
            f'<p><a href="{invite_url}">Set your password</a> (valid for 24h)</p>'
        )
        return subject, text, html

    subject = "您被邀请加入 GenPano 管理后台"
    text = (
        f"{inviter_email} 邀请您加入 GenPano 管理后台。\n\n"
        f"设置密码 (24 小时内有效): {invite_url}\n"
    )
    html = (
        f"<p>{inviter_email} 邀请您加入 GenPano 管理后台。</p>"
        f'<p><a href="{invite_url}">设置密码</a> (24 小时内有效)</p>'
    )
    return subject, text, html


def _send(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    locale: EmailLocale,
    client_override: ResendLike | None = None,
) -> EmailResult:
    client = client_override if client_override is not None else _get_resend_client()
    if client is None:
        logger.info(
            "admin_email.skipped",
            extra={
                "to": to,
                "subject": subject,
                "locale": locale,
                "reason": "no_resend_client",
            },
        )
        return EmailResult(delivered=False, provider_message_id=None, locale=locale)

    response = client.send(
        {
            "from": _from_address(),
            "to": [to],
            "subject": subject,
            "text": text,
            "html": html,
        }
    )
    message_id = response.get("id") if isinstance(response, dict) else None
    return EmailResult(
        delivered=True,
        provider_message_id=message_id if isinstance(message_id, str) else None,
        locale=locale,
    )


def send_password_reset_email(
    *,
    to: str,
    reset_token: str,
    locale: EmailLocale = _DEFAULT_LOCALE,
    client_override: ResendLike | None = None,
) -> EmailResult:
    reset_url = f"{_admin_base_url()}/admin/reset-password?token={reset_token}"
    subject, text, html = _build_password_reset(locale=locale, reset_url=reset_url)
    return _send(
        to=to,
        subject=subject,
        text=text,
        html=html,
        locale=locale,
        client_override=client_override,
    )


def send_invitation_email(
    *,
    to: str,
    invite_token: str,
    inviter_email: str,
    locale: EmailLocale = _DEFAULT_LOCALE,
    client_override: ResendLike | None = None,
) -> EmailResult:
    invite_url = f"{_admin_base_url()}/admin/reset-password?token={invite_token}&purpose=invitation"
    subject, text, html = _build_invitation(
        locale=locale, invite_url=invite_url, inviter_email=inviter_email
    )
    return _send(
        to=to,
        subject=subject,
        text=text,
        html=html,
        locale=locale,
        client_override=client_override,
    )
