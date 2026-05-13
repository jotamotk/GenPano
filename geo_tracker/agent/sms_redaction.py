"""Redaction helpers for SMS registration diagnostics."""

from __future__ import annotations

import re
from typing import Any

PHONE_RE = re.compile(r"(?<!\d)(?:\+?86)?(1\d{2})\d{4}(\d{4})(?!\d)")
E164_PHONE_RE = re.compile(r"(?<!\d)(\+?\d{10,15})(?!\d)")
SMS_CODE_RE = re.compile(r"(?<!\*)\b\d{4,8}\b")
URL_CREDENTIALS_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+)(?::([^/\s@]*))?@"
)
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|authorization|cookie|set-cookie)"
    r"([\"'\s:=]+)"
    r"([^\"'\s,;}]+)"
)


def mask_phone(phone: str | None) -> str:
    """Return a display-safe phone reference."""
    if not phone:
        return "[phone-redacted]"
    phone_text = str(phone)
    masked = PHONE_RE.sub(r"\1****\2", phone_text)
    if masked != phone_text:
        return masked
    digits = re.sub(r"\D", "", phone_text)
    if len(digits) >= 8:
        prefix = "+" if phone_text.strip().startswith("+") else ""
        return f"{prefix}{digits[:3]}****{digits[-4:]}"
    return "[phone-redacted]"


def redact_sensitive_text(value: Any) -> str:
    """Best-effort redaction for provider and browser diagnostics."""
    if value is None:
        return ""
    redacted = str(value)
    redacted = URL_CREDENTIALS_RE.sub(r"\1[credentials-redacted]@", redacted)
    redacted = PHONE_RE.sub(r"\1****\2", redacted)
    redacted = E164_PHONE_RE.sub(lambda match: mask_phone(match.group(1)), redacted)
    redacted = SECRET_RE.sub(r"\1\2[redacted]", redacted)
    redacted = SMS_CODE_RE.sub("[sms-code-redacted]", redacted)
    return redacted
