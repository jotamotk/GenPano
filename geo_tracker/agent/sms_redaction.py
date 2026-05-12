"""Redaction helpers for SMS registration diagnostics."""

from __future__ import annotations

import re
from typing import Any

PHONE_RE = re.compile(r"(?<!\d)(?:\+?86)?(1\d{2})\d{4}(\d{4})(?!\d)")
SMS_CODE_RE = re.compile(r"\b\d{4,8}\b")
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|authorization|cookie|set-cookie)"
    r"([\"'\s:=]+)"
    r"([^\"'\s,;}]+)"
)


def mask_phone(phone: str | None) -> str:
    """Return a display-safe phone reference."""
    if not phone:
        return "[phone-redacted]"
    return PHONE_RE.sub(r"\1****\2", str(phone))


def redact_sensitive_text(value: Any) -> str:
    """Best-effort redaction for provider and browser diagnostics."""
    if value is None:
        return ""
    redacted = str(value)
    redacted = PHONE_RE.sub(r"\1****\2", redacted)
    redacted = SECRET_RE.sub(r"\1\2[redacted]", redacted)
    redacted = SMS_CODE_RE.sub("[sms-code-redacted]", redacted)
    return redacted
