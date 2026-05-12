from __future__ import annotations

import re

POSITION_TYPE_PRIORITY = (
    "first_recommendation",
    "comparison_winner",
    "listed",
    "mentioned_only",
    "comparison_loser",
)

DEFAULT_POSITION_TYPE = "mentioned_only"


def normalize_position_type(value: object) -> str:
    """Return one canonical BrandMention.position_type value."""
    raw = str(value or "").strip().lower()
    if not raw:
        return DEFAULT_POSITION_TYPE

    normalized = raw.replace("-", "_")
    for position_type in POSITION_TYPE_PRIORITY:
        if re.search(
            rf"(?<![a-z0-9_]){re.escape(position_type)}(?![a-z0-9_])",
            normalized,
        ):
            return position_type
    return DEFAULT_POSITION_TYPE
