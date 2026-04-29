"""Email validation rules shared by product auth endpoints."""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email_format(email: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(normalize_email(email)))
