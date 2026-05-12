"""Redact HeroSMS secrets from diagnostics logs and streams."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEROSMS_HANDLER_URL_RE = re.compile(
    r"(?i)https?://[^\s\"'<>]*handler_api\.php[^\s\"'<>]*"
)
SECRET_ASSIGN_RE = re.compile(
    r"(?ix)"
    r"\b("
    r"api[_-]?key|apikey|"
    r"access[_-]?token|refresh[_-]?token|token|secret|"
    r"authorization|cookie|set[_-]?cookie"
    r")\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^&\s\"'<>]+)"
)
HERO_SMS_ENV_RE = re.compile(r"(?i)\bHERO_SMS_API_KEY\s*=\s*\S+")
AUTH_HEADER_RE = re.compile(r"(?i)\b(authorization)\s*:\s*(?:bearer\s+)?[^\s;]+")
COOKIE_HEADER_RE = re.compile(r"(?i)\b(cookie|set-cookie)\s*:\s*[^;\r\n]+;?")
PHONE_FIELD_RE = re.compile(
    r"(?ix)"
    r"\b(phone(?:[_-]?number)?|msisdn|mobile|number)\s*[:=]\s*"
    r"\+?\d[\d\s().-]{7,}\d"
)
E164_PHONE_RE = re.compile(r"(?<![\w])\+?\d{10,15}(?![\w])")
SMS_FIELD_RE = re.compile(
    r"(?ix)"
    r"\b(sms(?:[_-]?(?:text|body|message|code))?|text|body|message|code)"
    r"\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^&\s\"'<>]+)"
)
ACTIVATION_FIELD_RE = re.compile(
    r"(?ix)"
    r"\b(activation[_-]?(?:id|ref|secret|code)|activationid)\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^&\s\"'<>]+)"
)


def _redact_assignment(marker: str):
    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}={marker}"

    return replace


def _redact_header(match: re.Match[str]) -> str:
    return f"{match.group(1)}: [secret redacted]"


def sanitize_text(text: str) -> str:
    """Return log text with HeroSMS secrets and activation details removed."""
    sanitized = HEROSMS_HANDLER_URL_RE.sub("[HeroSMS URL redacted]", text)
    sanitized = AUTH_HEADER_RE.sub(_redact_header, sanitized)
    sanitized = COOKIE_HEADER_RE.sub(_redact_header, sanitized)
    sanitized = SECRET_ASSIGN_RE.sub(_redact_assignment("[secret redacted]"), sanitized)
    sanitized = HERO_SMS_ENV_RE.sub("HERO_SMS_API_KEY_present=true", sanitized)
    sanitized = PHONE_FIELD_RE.sub(_redact_assignment("[phone redacted]"), sanitized)
    sanitized = E164_PHONE_RE.sub("[phone redacted]", sanitized)
    sanitized = SMS_FIELD_RE.sub(_redact_assignment("[SMS field redacted]"), sanitized)
    return ACTIVATION_FIELD_RE.sub(
        _redact_assignment("[activation field redacted]"),
        sanitized,
    )


def sanitize_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(sanitize_text(text), encoding="utf-8")


def main(argv: list[str]) -> int:
    if argv:
        for arg in argv:
            sanitize_file(Path(arg))
        return 0
    sys.stdout.write(sanitize_text(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
