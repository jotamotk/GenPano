"""Charts sub-package — split from the legacy `_charts_service.py` god-module.

This package is being filled incrementally; see Epic #885 and tracking issue
#886. Public surface re-exported here for backwards-compatible imports.
"""

from __future__ import annotations

from app.api.v1.projects.charts._common import (
    DEFAULT_WINDOW_DAYS,
    _admin_filters,
    _chart_counts,
    _dt_range,
    _period,
    _resolve_window,
    _unique,
)

__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "_admin_filters",
    "_chart_counts",
    "_dt_range",
    "_period",
    "_resolve_window",
    "_unique",
]
