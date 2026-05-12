"""Redact HeroSMS secrets from diagnostics logs and streams."""

from __future__ import annotations

import re
import sys
from pathlib import Path

API_KEY_QUERY_RE = re.compile(r"(?i)([?&])api_key=[^&\s\"'<>]+")
API_KEY_ASSIGN_RE = re.compile(r"(?i)\bapi[_-]?key\s*=\s*[^&\s\"'<>]+")
HERO_SMS_ENV_RE = re.compile(r"(?i)\bHERO_SMS_API_KEY\s*=\s*\S+")


def sanitize_text(text: str) -> str:
    """Return log text with HeroSMS API-key material removed."""
    sanitized = API_KEY_QUERY_RE.sub(r"\1api key [redacted]", text)
    sanitized = API_KEY_ASSIGN_RE.sub("api key [redacted]", sanitized)
    return HERO_SMS_ENV_RE.sub("HERO_SMS_API_KEY_present=true", sanitized)


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
