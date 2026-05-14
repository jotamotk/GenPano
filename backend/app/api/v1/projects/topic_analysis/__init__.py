"""Topic-analysis sub-package — split from the legacy
`_topic_analysis_service.py` god-module.

This package is being filled incrementally; see Epic #885 and tracking issue
#887. Public surface re-exported here for backwards-compatible imports.
"""

from __future__ import annotations

from app.api.v1.projects.topic_analysis.legacy_schema import (
    _not_deleted_condition,
    _prompt_scope_expr,
    _prompt_tags_expr,
    _prompt_text_expr,
    _safe_ident,
    _select_col,
    _topic_name_expr,
    legacy_table_columns,
    legacy_table_exists,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _as_float,
    _as_int,
    _coerce_json,
    _date_key,
    _iso,
    _mean,
    _normalize_key,
    _pct,
    _response_preview,
    _round,
    _timestamp_key,
)

__all__ = [
    "_as_float",
    "_as_int",
    "_coerce_json",
    "_date_key",
    "_iso",
    "_mean",
    "_normalize_key",
    "_not_deleted_condition",
    "_pct",
    "_prompt_scope_expr",
    "_prompt_tags_expr",
    "_prompt_text_expr",
    "_response_preview",
    "_round",
    "_safe_ident",
    "_select_col",
    "_timestamp_key",
    "_topic_name_expr",
    "legacy_table_columns",
    "legacy_table_exists",
]
