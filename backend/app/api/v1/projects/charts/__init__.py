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
    _metric_evidence_allows_partial_data,
    _metric_evidence_dict,
    _metric_evidence_key,
    _missing_analyzer_metric_evidence,
    _with_chart_contract,
)
from app.api.v1.projects.charts.authority import (
    _target_authority_points_from_facts,
    _with_authority_trend_contract,
)
from app.api.v1.projects.charts.citation import (
    _target_citation_composition_rows,
    _with_citation_composition_contract,
)
from app.api.v1.projects.charts.engine_metric import (
    _apply_engine_metric_contract,
    _engine_metric_rows_from_facts,
    _with_engine_metric_contract,
)
from app.api.v1.projects.charts.position import _position_distribution_from_facts
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
from app.api.v1.projects.charts.topic_heatmap import _topic_heatmap_from_facts

__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "_admin_filters",
    "_apply_engine_metric_contract",
    "_chart_contract_update",
    "_chart_counts",
    "_chart_has_data",
    "_contract_metric_blocked",
    "_dt_range",
    "_engine_metric_rows_from_facts",
    "_fact_sentiment_score_response_count",
    "_label_for_polarity",
    "_metric_evidence_allows_partial_data",
    "_metric_evidence_dict",
    "_metric_evidence_key",
    "_missing_analyzer_metric_evidence",
    "_period",
    "_polarity_from_score",
    "_position_distribution_from_facts",
    "_resolve_window",
    "_sentiment_by_engine_missing_out",
    "_sentiment_label_sql",
    "_sentiment_missing_out",
    "_target_authority_points_from_facts",
    "_target_citation_composition_rows",
    "_topic_heatmap_from_facts",
    "_unique",
    "_with_authority_trend_contract",
    "_with_chart_contract",
    "_with_citation_composition_contract",
    "_with_engine_metric_contract",
    "_with_sentiment_by_engine_contract",
    "_with_sentiment_trend_contract",
]
