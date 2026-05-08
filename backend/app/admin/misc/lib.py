"""Misc admin helpers (Phase 9 slice 9f).

Bundles the leftover admin_console route helpers: queries-by-day mode
parsing, debug-file path validation, citation URL extraction.
"""

from __future__ import annotations

import os
import re
from typing import Any

DEBUG_FILE_EXTS: tuple[str, ...] = (".html", ".png", ".jpg", ".jpeg", ".json")

_URL_RE = re.compile(r'https?://[^\s<>"\')\]},;]+', re.IGNORECASE)
_HREF_RE = re.compile(r'<a\s[^>]*href=["\']?(https?://[^"\'>\s]+)', re.IGNORECASE)

CITATION_SKIP_DOMAINS: frozenset[str] = frozenset(
    {
        "chatgpt.com",
        "gemini.google.com",
        "accounts.google.com",
        "cdn.oaistatic.com",
        "oaiusercontent.com",
        "cdn-cgi",
        "gstatic.com",
        "googleapis.com",
        "google.com/gsi",
        "statsig",
        "sentry",
        "intercom",
    }
)


class MiscValidationError(Exception):
    """Coded validation error returned to the API layer (HTTP 400)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── debug-file utilities ────────────────────────────────────


def classify_debug_file(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".html"):
        return "html"
    if lower.endswith((".png", ".jpg", ".jpeg")):
        return "image"
    if lower.endswith(".json"):
        return "json"
    return "other"


def validate_screenshot_path(
    path: str | None, screenshot_dir: str
) -> tuple[str | None, tuple[str, int] | None]:
    """Validate ``path`` is under ``screenshot_dir``. Returns
    ``(real_path, None)`` on success or ``(None, (error_message, status))``
    on rejection — exactly mirrors admin_console line 7369."""
    if not path:
        return None, ("Path required", 400)
    real_path = os.path.realpath(path)
    real_dir = os.path.realpath(screenshot_dir)
    if not real_path.startswith(real_dir + os.sep) and real_path != real_dir:
        return None, ("Access denied", 403)
    if not os.path.isfile(real_path):
        return None, ("File not found", 404)
    return real_path, None


def list_debug_files(
    *,
    screenshot_dir: str,
    query_id: str | None = None,
    include_images: bool = True,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Walk ``screenshot_dir`` and return ``(page_items, total)``. Also
    used by the legacy "no pagination params" path which calls this
    with ``page=1, per_page=∞`` and ignores the count."""
    entries: list[dict[str, Any]] = []
    if os.path.isdir(screenshot_dir):
        for fname in os.listdir(screenshot_dir):
            lower = fname.lower()
            if not lower.endswith(DEBUG_FILE_EXTS):
                continue
            if not include_images and not lower.endswith(".html"):
                continue
            if query_id and (
                f"query_{query_id}_" not in fname and f"query_{query_id}." not in fname
            ):
                continue
            fpath = os.path.join(screenshot_dir, fname)
            try:
                stat = os.stat(fpath)
            except OSError:
                continue
            entries.append(
                {
                    "name": fname,
                    "path": fpath,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "type": classify_debug_file(fname),
                }
            )
    entries.sort(key=lambda e: e["mtime"], reverse=True)
    total = len(entries)
    start = (page - 1) * per_page
    end = start + per_page
    return entries[start:end], total


# ── queries-by-day ──────────────────────────────────────────


_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_by_day_args(args: dict[str, Any]) -> dict[str, Any]:
    """Normalize the by-day query string. Returns
    ``{mode, month?, date?, llm?, profile_id?}``. Raises
    ``MiscValidationError`` for malformed month/date."""
    args = args or {}
    month = str(args.get("month") or "").strip()
    date = str(args.get("date") or "").strip()
    llm = str(args.get("llm") or "").strip() or None
    profile_id = str(args.get("profile_id") or "").strip() or None
    if not month and not date:
        # admin_console default — not used by the FastAPI port (we let
        # the caller default to current month with timezone-aware utcnow).
        return {"mode": "month", "month": None, "llm": llm, "profile_id": profile_id}
    if month and not date:
        if not _MONTH_RE.match(month):
            raise MiscValidationError("invalid_month", "month must be YYYY-MM")
        return {
            "mode": "month",
            "month": month,
            "llm": llm,
            "profile_id": profile_id,
        }
    if not _DATE_RE.match(date):
        raise MiscValidationError("invalid_date", "date must be YYYY-MM-DD")
    return {
        "mode": "date",
        "date": date,
        "llm": llm,
        "profile_id": profile_id,
    }


# ── citation extraction ────────────────────────────────────


def extract_citations_from_text(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    return _URL_RE.findall(raw_text)


def extract_hrefs(html: str | None) -> list[str]:
    if not html:
        return []
    return _HREF_RE.findall(html)


def deduplicate_citations(urls: list[str]) -> list[dict[str, Any]]:
    """Strip trailing punctuation, dedupe, drop blacklisted domains.
    Mirrors admin_console line 7480."""
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for raw_url in urls:
        url = raw_url.rstrip(".,;:!?)]}")
        if url in seen:
            continue
        if any(domain in url for domain in CITATION_SKIP_DOMAINS):
            continue
        seen.add(url)
        citations.append({"url": url, "title": "", "index": len(citations) + 1})
    return citations


__all__ = [
    "CITATION_SKIP_DOMAINS",
    "DEBUG_FILE_EXTS",
    "MiscValidationError",
    "classify_debug_file",
    "deduplicate_citations",
    "extract_citations_from_text",
    "extract_hrefs",
    "list_debug_files",
    "parse_by_day_args",
    "validate_screenshot_path",
]
