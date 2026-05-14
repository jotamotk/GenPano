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
from app.api.v1.projects.charts._contracts import (
    _chart_contract_update,
    _chart_has_data,
    _contract_metric_blocked,
    _metric_evidence_dict,
    _metric_evidence_key,
    _missing_analyzer_metric_evidence,
    _with_chart_contract,
)
from app.api.v1.projects.charts.sentiment import (
    _fact_sentiment_score_response_count,
    _label_for_polarity,
    _polarity_from_score,
    _sentiment_by_engine_missing_out,
    _sentiment_label_sql,
    _sentiment_missing_out,
    _with_sentiment_by_engine_contract,
    _with_sentiment_trend_contract,
)

__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "_admin_filters",
    "_chart_contract_update",
    "_chart_counts",
    "_chart_has_data",
    "_contract_metric_blocked",
    "_dt_range",
    "_fact_sentiment_score_response_count",
    "_label_for_polarity",
    "_metric_evidence_dict",
    "_metric_evidence_key",
    "_missing_analyzer_metric_evidence",
    "_period",
    "_polarity_from_score",
    "_resolve_window",
    "_sentiment_by_engine_missing_out",
    "_sentiment_label_sql",
    "_sentiment_missing_out",
    "_unique",
    "_with_chart_contract",
    "_with_sentiment_by_engine_contract",
    "_with_sentiment_trend_contract",
]
