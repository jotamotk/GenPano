"""Pure helpers for ``llm_accounts`` cookie operations.

Cookie security note: payload validation lives here as pure-Python so
it's testable without a DB. The caller (route handler / db module)
takes the validated structure and writes it as a JSON-serialized
``cookies_json`` column. Operator credentials are NOT logged in audit
rows — only counts + platform / label.

Public:
- ``ACCOUNT_STATUSES`` allowed values.
- ``CookieImportError``: coded validation error.
- ``parse_cookies_payload(payload)``: validate + EditThisCookie auto-
  detect/convert + optional ``local_storage`` packing. Returns
  ``(cookies_json_str, cookie_count, local_storage_count)``.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

ACCOUNT_STATUSES = ("active", "banned", "cooldown", "expired")

_PHONE_TEXT_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{5,}\d)(?!\d)")
_SMS_CODE_RE = re.compile(r"\b\d{4,8}\b")
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|authorization|cookie|set-cookie)"
    r"([\"'\s:=]+)"
    r"([^\"'\s,;}]+)"
)
_SENSITIVE_ACCOUNT_FIELD_MARKERS = (
    "activation",
    "api_key",
    "apikey",
    "cookie",
    "local_storage",
    "localstorage",
    "password",
    "provider_secret",
    "secret",
    "sms",
    "token",
)


_SAME_SITE_MAP = {
    "unspecified": "Lax",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
}


class CookieImportError(Exception):
    """Coded validation error returned to the API layer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_edit_this_cookie_format(cookies: list[Any]) -> bool:
    """EditThisCookie / Cookie-Editor exports ship ``storeId`` /
    ``hostOnly`` keys; standard Playwright/JSON exports don't."""
    return bool(
        cookies
        and isinstance(cookies[0], dict)
        and ("storeId" in cookies[0] or "hostOnly" in cookies[0])
    )


def _convert_edit_this_cookie(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert EditThisCookie format → Playwright cookie shape.

    Mirrors admin_console import_cookies_api: session cookies (no
    ``expirationDate``) get a 30-day TTL injected so Playwright
    doesn't drop them on context creation.
    """
    converted: list[dict[str, Any]] = []
    now = time.time()
    for c in cookies:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        entry: dict[str, Any] = {
            "name": c["name"],
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        if c.get("expirationDate"):
            entry["expires"] = c["expirationDate"]
        elif c.get("session"):
            # Session-cookie heuristic: 30-day TTL so Playwright
            # injection survives. Same magic number admin_console used.
            entry["expires"] = now + 30 * 86400
        if c.get("httpOnly"):
            entry["httpOnly"] = True
        if c.get("secure"):
            entry["secure"] = True
        same_site = str(c.get("sameSite") or "unspecified").lower()
        entry["sameSite"] = _SAME_SITE_MAP.get(same_site, "Lax")
        converted.append(entry)
    return converted


def parse_cookies_payload(
    payload: dict[str, Any] | None,
) -> tuple[str, str, str, int, int, int]:
    """Validate + normalize an ``import_cookies`` payload.

    Returns ``(platform, label, cookies_json_str, cookie_count,
    local_storage_count, daily_limit)``. Raises ``CookieImportError``
    with a stable code on missing / malformed input — caller maps to
    HTTP 400.
    """
    payload = payload or {}
    platform = str(payload.get("platform") or "").strip()
    if not platform:
        raise CookieImportError("platform_required", "Platform is required")
    label = str(payload.get("label") or "").strip() or "web_upload"
    daily_limit_raw = payload.get("daily_limit", 20)
    try:
        daily_limit = int(daily_limit_raw)
    except (TypeError, ValueError):
        daily_limit = 20
    daily_limit = max(0, min(daily_limit, 10_000))

    cookies_raw = payload.get("cookies_json")
    if cookies_raw in (None, ""):
        raise CookieImportError("cookies_required", "cookies_json is required")
    if isinstance(cookies_raw, (dict, list)):
        cookies = cookies_raw
    else:
        try:
            cookies = json.loads(str(cookies_raw))
        except json.JSONDecodeError as exc:
            raise CookieImportError("invalid_cookies_json", f"Invalid JSON: {exc}") from exc

    if isinstance(cookies, list) and _is_edit_this_cookie_format(cookies):
        cookies = _convert_edit_this_cookie(cookies)

    if not isinstance(cookies, list) or not cookies:
        raise CookieImportError("no_valid_cookies", "No valid cookies found")

    local_storage_raw = payload.get("local_storage")
    local_storage: dict[str, Any] = {}
    if local_storage_raw not in (None, ""):
        if isinstance(local_storage_raw, dict):
            local_storage = dict(local_storage_raw)
        else:
            try:
                parsed = json.loads(str(local_storage_raw))
                if isinstance(parsed, dict):
                    local_storage = parsed
            except Exception:
                local_storage = {}

    if local_storage:
        cookies_json_str = json.dumps(
            {"cookies": cookies, "localStorage": local_storage},
            ensure_ascii=False,
        )
    else:
        cookies_json_str = json.dumps(cookies, ensure_ascii=False)

    return (
        platform,
        label,
        cookies_json_str,
        len(cookies),
        len(local_storage),
        daily_limit,
    )


def normalize_account_status(value: Any) -> str | None:
    """Returns one of ACCOUNT_STATUSES, or None when invalid."""
    text = str(value or "").strip().lower()
    return text if text in ACCOUNT_STATUSES else None


def mask_phone_reference(value: Any) -> str:
    """Return a display-safe account phone reference.

    Non-phone labels such as ``web_upload`` or ``label-1`` are preserved.
    Numeric phone-like identifiers expose only a short stable reference.
    """
    text = str(value or "")
    digits = re.sub(r"\D+", "", text)
    if len(digits) < 7:
        return text
    return f"{digits[:3]}****{digits[-4:]}"


def redact_sensitive_text(value: Any) -> str:
    """Best-effort redaction for Admin Accounts audit reasons."""
    if value is None:
        return ""
    redacted = str(value)
    redacted = _SMS_CODE_RE.sub("[sms-code-redacted]", redacted)
    redacted = _PHONE_TEXT_RE.sub(lambda match: mask_phone_reference(match.group(0)), redacted)
    redacted = _SECRET_RE.sub(r"\1\2[redacted]", redacted)
    return redacted


def redact_account_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive account fields and mask phone references for API output."""
    safe: dict[str, Any] = {}
    for key, value in dict(row).items():
        key_l = str(key).lower()
        if any(marker in key_l for marker in _SENSITIVE_ACCOUNT_FIELD_MARKERS):
            continue
        safe[key] = value
    if "phone_number" in row:
        safe["phone_number"] = mask_phone_reference(row.get("phone_number"))
    return safe


_LABEL_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.\-+@]+")


def safe_email_for_label(label: str, platform: str) -> str:
    """Synthesize the legacy ``label@platform.local`` email used as the
    inserted-row identity (admin_console line 8568). Strips chars that
    would break the email format."""
    safe_label = _LABEL_SAFE_RE.sub("_", str(label or "web_upload")).strip("_") or "web_upload"
    safe_platform = _LABEL_SAFE_RE.sub("_", str(platform or "unknown")).strip("_") or "unknown"
    return f"{safe_label}@{safe_platform}.local"
