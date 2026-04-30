from __future__ import annotations

from email.message import EmailMessage
from typing import ClassVar

from app.user_auth.email import send_verification_email


class FakeSmtpSsl:
    instances: ClassVar[list[FakeSmtpSsl]] = []

    def __init__(self, host: str, port: int, *, timeout: int, context: object) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.login_args: tuple[str, str] | None = None
        self.message: EmailMessage | None = None
        FakeSmtpSsl.instances.append(self)

    def __enter__(self) -> FakeSmtpSsl:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.message = message
        return {}


def test_aliyun_dm_smtp_provider_sends_email(monkeypatch) -> None:
    FakeSmtpSsl.instances.clear()
    monkeypatch.setenv("EMAIL_PROVIDER", "aliyun_dm")
    monkeypatch.setenv("ALIYUN_DM_SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("ALIYUN_DM_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("USER_EMAIL_FROM", "GenPano <noreply@example.com>")
    monkeypatch.setenv("USER_BASE_URL", "http://app.local")

    monkeypatch.setattr("app.user_auth.email.smtplib.SMTP_SSL", FakeSmtpSsl)

    result = send_verification_email(to="person@example.com", token="abc123", locale="en-US")

    assert result.delivered is True
    smtp = FakeSmtpSsl.instances[0]
    assert smtp.host == "smtpdm.aliyun.com"
    assert smtp.port == 465
    assert smtp.login_args == ("noreply@example.com", "secret")
    assert smtp.message is not None
    assert smtp.message["From"] == "GenPano <noreply@example.com>"
    assert smtp.message["To"] == "person@example.com"
    plain_body = smtp.message.get_body(preferencelist=("plain",)).get_content()
    assert "http://app.local/setup?token=abc123" in plain_body


def test_email_noops_without_provider_credentials(monkeypatch) -> None:
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("USER_EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ALIYUN_DM_SMTP_USER", raising=False)
    monkeypatch.delenv("ALIYUN_DM_SMTP_PASSWORD", raising=False)

    result = send_verification_email(to="person@example.com", token="abc123")

    assert result.delivered is False


def test_preview_provider_writes_email_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "preview")
    monkeypatch.setenv("USER_EMAIL_PREVIEW_DIR", str(tmp_path))
    monkeypatch.setenv("USER_BASE_URL", "http://app.local")

    result = send_verification_email(to="person@example.com", token="abc123", locale="en-US")

    assert result.delivered is True
    assert result.preview_url is not None
    filename = result.preview_url.rsplit("/", 1)[-1]
    assert filename.endswith(".html")
    html = (tmp_path / filename).read_text(encoding="utf-8")
    text = (tmp_path / filename.replace(".html", ".txt")).read_text(encoding="utf-8")
    assert "http://app.local/setup?token=abc123" in html
    assert "http://app.local/setup?token=abc123" in text
