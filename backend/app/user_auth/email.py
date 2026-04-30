# ruff: noqa: E501, RUF001
"""Product transactional emails for registration and password reset.

Aliyun DirectMail SMTP or Resend can be selected by environment variables.
Local and CI runs deliberately no-op with structured return data so auth flows
can be tested without network access or secrets.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from pathlib import Path
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

EmailLocale = Literal["zh-CN", "en-US"]
_DEFAULT_LOCALE: EmailLocale = "zh-CN"
_BASE_URL_FALLBACK = "http://localhost:3000"
_FROM_ADDRESS_DEFAULT = "GenPano <noreply@genpano.com>"
_ALIYUN_DM_SMTP_HOST = "smtpdm.aliyun.com"
_ALIYUN_DM_SMTP_PORT = 465
_EMAIL_PREVIEW_DIR_DEFAULT = "/data/email-previews"
_EMAIL_PREVIEW_PROVIDER_NAMES = {"preview", "file", "filesystem"}
_EMAIL_PREVIEW_FILE_RE = re.compile(r"^[A-Za-z0-9_-]{24,96}\.html$")


@dataclass(frozen=True)
class EmailResult:
    delivered: bool
    provider_message_id: str | None
    locale: EmailLocale
    preview_url: str | None = None


@dataclass(frozen=True)
class EmailContent:
    subject: str
    html: str
    text: str


class ResendLike(Protocol):
    def send(self, params: dict[str, Any]) -> dict[str, Any]: ...


def frontend_base_url() -> str:
    return (
        os.environ.get("USER_BASE_URL")
        or os.environ.get("FRONTEND_URL")
        or os.environ.get("PUBLIC_APP_URL")
        or _BASE_URL_FALLBACK
    ).rstrip("/")


def _from_address() -> str:
    return (
        os.environ.get("USER_EMAIL_FROM") or os.environ.get("EMAIL_FROM") or _FROM_ADDRESS_DEFAULT
    )


def _get_resend_client() -> ResendLike | None:
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


def _email_provider() -> str:
    configured = (
        (os.environ.get("USER_EMAIL_PROVIDER") or os.environ.get("EMAIL_PROVIDER") or "")
        .strip()
        .lower()
    )
    if configured:
        return configured
    if os.environ.get("RESEND_API_KEY"):
        return "resend"
    if os.environ.get("ALIYUN_DM_SMTP_PASSWORD") or os.environ.get("ALIYUN_DM_SMTP_USER"):
        return "aliyun_dm"
    return "noop"


def _email_preview_dir() -> Path:
    return Path(
        os.environ.get("USER_EMAIL_PREVIEW_DIR")
        or os.environ.get("EMAIL_PREVIEW_DIR")
        or _EMAIL_PREVIEW_DIR_DEFAULT
    )


def _email_preview_enabled() -> bool:
    return _email_provider() in _EMAIL_PREVIEW_PROVIDER_NAMES


def get_preview_email_path(message_id: str) -> Path | None:
    if not _email_preview_enabled() or not _EMAIL_PREVIEW_FILE_RE.fullmatch(message_id):
        return None
    return _email_preview_dir() / message_id


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("user_email.invalid_int_env", extra={"env": name, "value": value})
        return default


def _from_email_address() -> str:
    _, address = parseaddr(_from_address())
    return address or _from_address()


def _button(url: str, label: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">'
        '<tr><td bgcolor="#605BFF" style="background:#605BFF;border-radius:10px;">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:14px 24px;'
        "font:700 14px Arial,Microsoft YaHei,sans-serif;color:#ffffff;text-decoration:none;"
        'letter-spacing:0;">'
        f"{escape(label)}</a></td></tr></table>"
    )


def _paragraphs(lines: list[str]) -> str:
    return "".join(
        '<p style="margin:0 0 12px;font-size:15px;line-height:1.75;color:#33384D;">'
        f"{escape(line)}</p>"
        for line in lines
    )


def _notice_box(*, title: str, body: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:4px 0 22px;background:#F7F7FF;border:1px solid #E5E4FF;border-radius:12px;">'
        '<tr><td style="padding:16px 18px;">'
        f'<div style="font:700 13px Arial,Microsoft YaHei,sans-serif;color:#030229;margin-bottom:5px;">{escape(title)}</div>'
        f'<div style="font:400 13px/1.7 Arial,Microsoft YaHei,sans-serif;color:#5E6278;">{escape(body)}</div>'
        "</td></tr></table>"
    )


def _fallback_link(url: str, label: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 22px;">'
        '<tr><td style="font:700 12px Arial,Microsoft YaHei,sans-serif;color:#6B7280;padding-bottom:8px;">'
        f"{escape(label)}</td></tr>"
        '<tr><td style="padding:12px 14px;background:#FAFAFB;border:1px solid #ECEEF5;border-radius:10px;">'
        f'<a href="{escape(url)}" style="font:400 12px/1.7 Arial,Microsoft YaHei,sans-serif;color:#605BFF;'
        f'text-decoration:none;word-break:break-all;">{escape(url)}</a>'
        "</td></tr></table>"
    )


def _layout(
    *,
    preheader: str,
    eyebrow: str,
    title: str,
    intro_lines: list[str],
    cta_url: str,
    cta_label: str,
    fallback_label: str,
    notice_title: str,
    notice_body: str,
    security_title: str,
    security_body: str,
) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:#F6F8FB;font-family:Arial,'Microsoft YaHei',sans-serif;color:#030229;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {escape(preheader)}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#F6F8FB" style="background:#F6F8FB;padding:34px 14px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border:1px solid #E7E9F2;border-radius:18px;overflow:hidden;box-shadow:0 18px 48px rgba(20,24,40,0.08);">
        <tr>
          <td bgcolor="#030229" style="background:#030229;padding:26px 30px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td valign="middle" style="width:52px;">
                  <table role="presentation" cellpadding="0" cellspacing="0">
                    <tr>
                      <td bgcolor="#605BFF" style="width:42px;height:42px;background:#605BFF;border-radius:12px;text-align:center;">
                        <span style="font:800 15px Arial,sans-serif;color:#FFFFFF;line-height:42px;">GP</span>
                      </td>
                    </tr>
                  </table>
                </td>
                <td valign="middle">
                  <div style="font:800 20px Arial,Microsoft YaHei,sans-serif;color:#FFFFFF;letter-spacing:0;">GenPano</div>
                  <div style="font:400 12px/1.5 Arial,Microsoft YaHei,sans-serif;color:#B8B9D1;margin-top:3px;">Brand Monitoring Workspace</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:34px 30px 8px;">
            <div style="display:inline-block;margin:0 0 14px;padding:5px 10px;background:#F0F0FF;border-radius:999px;font:700 12px Arial,Microsoft YaHei,sans-serif;color:#605BFF;">
              {escape(eyebrow)}
            </div>
            <h1 style="margin:0 0 16px;font:800 26px/1.28 Arial,Microsoft YaHei,sans-serif;color:#030229;letter-spacing:0;">
              {escape(title)}
            </h1>
            <div style="margin:0 0 22px;">
              {_paragraphs(intro_lines)}
            </div>
            {_button(cta_url, cta_label)}
            {_fallback_link(cta_url, fallback_label)}
            {_notice_box(title=notice_title, body=notice_body)}
          </td>
        </tr>
        <tr>
          <td style="padding:0 30px 30px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FAFAFB;border:1px solid #ECEEF5;border-radius:12px;">
              <tr><td style="padding:16px 18px;">
                <div style="font:700 13px Arial,Microsoft YaHei,sans-serif;color:#030229;margin-bottom:4px;">{escape(security_title)}</div>
                <div style="font:400 12px/1.7 Arial,Microsoft YaHei,sans-serif;color:#6B7280;">{escape(security_body)}</div>
              </td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 30px;background:#FFFFFF;border-top:1px solid #F2F4F7;">
            <div style="font:400 12px/1.7 Arial,Microsoft YaHei,sans-serif;color:#818194;">
              GenPano · Brand Monitoring Workspace<br>
              This is a transactional email for your GenPano account.
            </div>
          </td>
        </tr>
      </table>
      <div style="max-width:600px;margin:16px auto 0;font:400 11px/1.6 Arial,Microsoft YaHei,sans-serif;color:#A0A3B4;text-align:center;">
        Please do not reply directly to this email.
      </div>
    </td></tr>
  </table>
</body>
</html>"""


def build_verification_email(*, token: str, locale: EmailLocale = _DEFAULT_LOCALE) -> EmailContent:
    verify_url = f"{frontend_base_url()}/setup?token={token}"
    if locale == "en-US":
        subject = "Verify your GenPano account"
        intro_lines = [
            "Confirm this email to finish creating your GenPano account.",
            "After verification, you can set your password and continue to your workspace.",
        ]
        label = "Verify email"
        notice_title = "Link details"
        notice_body = "This verification link expires in 24 hours and can only be used once."
        fallback_label = "If the button does not open, copy this link into your browser:"
        security_title = "Not you?"
        security_body = "If you did not request this email, you can safely ignore it."
    else:
        subject = "验证你的 GenPano 账号"
        intro_lines = [
            "请确认此邮箱，用于完成 GenPano 账号创建。",
            "验证后，你可以设置密码并继续进入工作台。",
        ]
        label = "验证邮箱"
        notice_title = "链接说明"
        notice_body = "此验证链接将在 24 小时后过期，且只能使用一次。"
        fallback_label = "如果按钮无法打开，请复制以下链接到浏览器："
        security_title = "不是你本人操作？"
        security_body = "如果你没有注册 GenPano，可以忽略本邮件。"
    html = _layout(
        preheader=intro_lines[0],
        eyebrow="Account verification" if locale == "en-US" else "账号验证",
        title=subject,
        intro_lines=intro_lines,
        cta_url=verify_url,
        cta_label=label,
        fallback_label=fallback_label,
        notice_title=notice_title,
        notice_body=notice_body,
        security_title=security_title,
        security_body=security_body,
    )
    text = f"{intro_lines[0]}\n{intro_lines[1]}\n\n{verify_url}\n\n{notice_body}\n\n{security_body}"
    return EmailContent(subject=subject, html=html, text=text)


def build_password_reset_email(
    *, token: str, locale: EmailLocale = _DEFAULT_LOCALE
) -> EmailContent:
    reset_url = f"{frontend_base_url()}/reset-password?token={token}"
    if locale == "en-US":
        subject = "Reset your GenPano password"
        intro_lines = [
            "We received a request to reset your GenPano password.",
            "Use the secure link below to set a new password.",
        ]
        label = "Reset password"
        notice_title = "Link details"
        notice_body = "This reset link expires in 1 hour and can only be used once."
        fallback_label = "If the button does not open, copy this link into your browser:"
        security_title = "Did not request a password reset?"
        security_body = "No action is needed. Your existing password will remain unchanged."
    else:
        subject = "重置你的 GenPano 密码"
        intro_lines = [
            "我们收到了重置 GenPano 密码的请求。",
            "请使用下方安全链接设置新密码。",
        ]
        label = "重置密码"
        notice_title = "链接说明"
        notice_body = "此重置链接将在 1 小时后过期，且只能使用一次。"
        fallback_label = "如果按钮无法打开，请复制以下链接到浏览器："
        security_title = "没有发起重置？"
        security_body = "如果这不是你的操作，无需处理。你的原密码不会被修改。"
    html = _layout(
        preheader=intro_lines[0],
        eyebrow="Password reset" if locale == "en-US" else "密码重置",
        title=subject,
        intro_lines=intro_lines,
        cta_url=reset_url,
        cta_label=label,
        fallback_label=fallback_label,
        notice_title=notice_title,
        notice_body=notice_body,
        security_title=security_title,
        security_body=security_body,
    )
    text = f"{intro_lines[0]}\n{intro_lines[1]}\n\n{reset_url}\n\n{notice_body}\n\n{security_body}"
    return EmailContent(subject=subject, html=html, text=text)


def build_welcome_email(*, locale: EmailLocale = _DEFAULT_LOCALE) -> EmailContent:
    app_url = frontend_base_url()
    if locale == "en-US":
        subject = "Welcome to GenPano"
        intro_lines = [
            "Your account is ready.",
            "You can now open your workspace to review brand monitoring data and continue project setup.",
        ]
        label = "Open GenPano"
        notice_title = "What you can do next"
        notice_body = "Create a project, manage brands and competitors, and review monitoring results from one workspace."
        fallback_label = "If the button does not open, copy this link into your browser:"
        security_title = "Why you received this"
        security_body = "You are receiving this because your GenPano account was activated."
    else:
        subject = "欢迎使用 GenPano"
        intro_lines = [
            "你的账号已完成激活。",
            "现在可以进入工作台查看品牌监测数据，继续配置项目和报告。",
        ]
        label = "进入工作台"
        notice_title = "你可以继续做什么"
        notice_body = "创建项目、管理品牌与竞品，并在一个工作台内查看监测结果。"
        fallback_label = "如果按钮无法打开，请复制以下链接到浏览器："
        security_title = "为什么收到这封邮件"
        security_body = "你收到此邮件，是因为 GenPano 账号已完成激活。"
    html = _layout(
        preheader=intro_lines[0],
        eyebrow="Account activated" if locale == "en-US" else "账号已激活",
        title=subject,
        intro_lines=intro_lines,
        cta_url=app_url,
        cta_label=label,
        fallback_label=fallback_label,
        notice_title=notice_title,
        notice_body=notice_body,
        security_title=security_title,
        security_body=security_body,
    )
    text = f"{intro_lines[0]}\n{intro_lines[1]}\n\n{app_url}\n\n{notice_body}\n\n{security_body}"
    return EmailContent(subject=subject, html=html, text=text)


def _send_with_resend(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    locale: EmailLocale,
    client_override: ResendLike | None = None,
) -> EmailResult:
    client = client_override if client_override is not None else _get_resend_client()
    if client is None:
        logger.info(
            "user_email.skipped",
            extra={
                "to": to,
                "subject": subject,
                "locale": locale,
                "provider": "resend",
                "reason": "no_resend_client",
            },
        )
        return EmailResult(delivered=False, provider_message_id=None, locale=locale)

    response = client.send(
        {
            "from": _from_address(),
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
    )
    message_id = response.get("id") if isinstance(response, dict) else None
    return EmailResult(
        delivered=True,
        provider_message_id=message_id if isinstance(message_id, str) else None,
        locale=locale,
    )


def _send_with_aliyun_dm(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    locale: EmailLocale,
) -> EmailResult:
    username = os.environ.get("ALIYUN_DM_SMTP_USER") or _from_email_address()
    password = os.environ.get("ALIYUN_DM_SMTP_PASSWORD")
    if not username or not password:
        logger.info(
            "user_email.skipped",
            extra={
                "to": to,
                "subject": subject,
                "locale": locale,
                "provider": "aliyun_dm",
                "reason": "missing_smtp_credentials",
            },
        )
        return EmailResult(delivered=False, provider_message_id=None, locale=locale)

    host = os.environ.get("ALIYUN_DM_SMTP_HOST", _ALIYUN_DM_SMTP_HOST)
    port = _env_int("ALIYUN_DM_SMTP_PORT", default=_ALIYUN_DM_SMTP_PORT)
    timeout = _env_int("ALIYUN_DM_SMTP_TIMEOUT", default=10)
    use_ssl = _env_bool("ALIYUN_DM_SMTP_SSL", default=port == 465)
    use_starttls = _env_bool("ALIYUN_DM_SMTP_STARTTLS", default=not use_ssl)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_address()
    message["To"] = to
    reply_to = os.environ.get("USER_EMAIL_REPLY_TO") or os.environ.get("EMAIL_REPLY_TO")
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as smtp:
            smtp.login(username, password)
            refused = smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            if use_starttls:
                smtp.starttls(context=context)
            smtp.login(username, password)
            refused = smtp.send_message(message)

    if refused:
        raise RuntimeError(f"Aliyun DM refused recipients: {', '.join(refused.keys())}")

    return EmailResult(delivered=True, provider_message_id=None, locale=locale)


def _send_with_preview(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    locale: EmailLocale,
) -> EmailResult:
    preview_dir = _email_preview_dir()
    preview_dir.mkdir(parents=True, exist_ok=True)

    message_id = secrets.token_urlsafe(24)
    html_filename = f"{message_id}.html"
    text_filename = f"{message_id}.txt"
    html_path = preview_dir / html_filename
    text_path = preview_dir / text_filename
    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")

    preview_url = f"{frontend_base_url()}/api/auth/email-preview/{html_filename}"
    metadata = {
        "id": message_id,
        "to": to,
        "subject": subject,
        "locale": locale,
        "preview_url": preview_url,
        "html_file": html_filename,
        "text_file": text_filename,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (preview_dir / f"{message_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (preview_dir / "latest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "user_email.preview_saved",
        extra={"to": to, "subject": subject, "locale": locale, "preview_url": preview_url},
    )
    return EmailResult(
        delivered=True,
        provider_message_id=message_id,
        locale=locale,
        preview_url=preview_url,
    )


def _send(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    locale: EmailLocale,
    client_override: ResendLike | None = None,
) -> EmailResult:
    provider = _email_provider()
    if provider in _EMAIL_PREVIEW_PROVIDER_NAMES:
        return _send_with_preview(to=to, subject=subject, html=html, text=text, locale=locale)
    if provider in {"aliyun", "aliyun_dm", "aliyun_smtp"}:
        return _send_with_aliyun_dm(to=to, subject=subject, html=html, text=text, locale=locale)
    if provider == "resend" or client_override is not None:
        return _send_with_resend(
            to=to,
            subject=subject,
            html=html,
            text=text,
            locale=locale,
            client_override=client_override,
        )
    if provider in {"", "noop", "none", "off"}:
        logger.info(
            "user_email.skipped",
            extra={
                "to": to,
                "subject": subject,
                "locale": locale,
                "provider": "noop",
                "reason": "email_disabled",
            },
        )
        return EmailResult(delivered=False, provider_message_id=None, locale=locale)

    logger.warning(
        "user_email.unknown_provider",
        extra={"to": to, "subject": subject, "locale": locale, "provider": provider},
    )
    return EmailResult(delivered=False, provider_message_id=None, locale=locale)


def send_verification_email(
    *,
    to: str,
    token: str,
    locale: EmailLocale = _DEFAULT_LOCALE,
    client_override: ResendLike | None = None,
) -> EmailResult:
    content = build_verification_email(token=token, locale=locale)
    return _send(
        to=to,
        subject=content.subject,
        html=content.html,
        text=content.text,
        locale=locale,
        client_override=client_override,
    )


def send_password_reset_email(
    *,
    to: str,
    token: str,
    locale: EmailLocale = _DEFAULT_LOCALE,
    client_override: ResendLike | None = None,
) -> EmailResult:
    content = build_password_reset_email(token=token, locale=locale)
    return _send(
        to=to,
        subject=content.subject,
        html=content.html,
        text=content.text,
        locale=locale,
        client_override=client_override,
    )


def send_welcome_email(
    *,
    to: str,
    locale: EmailLocale = _DEFAULT_LOCALE,
    client_override: ResendLike | None = None,
) -> EmailResult:
    content = build_welcome_email(locale=locale)
    return _send(
        to=to,
        subject=content.subject,
        html=content.html,
        text=content.text,
        locale=locale,
        client_override=client_override,
    )
