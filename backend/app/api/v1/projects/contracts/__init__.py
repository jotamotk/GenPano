"""Contracts sub-package — split from the legacy `_analytics_contract.py`
god-module.

This package is being filled incrementally; see Epic #885 and tracking issue
#888. Public surface re-exported here for backwards-compatible imports.
"""

from __future__ import annotations

from app.api.v1.projects.contracts.models import (
    AnalyticsContractContext,
    DataFreshness,
    FormulaDiagnostics,
    IdentityDiagnostics,
    MetricDefinition,
    MetricValue,
    ProjectScope,
    ValueRange,
)

__all__ = [
    "AnalyticsContractContext",
    "DataFreshness",
    "FormulaDiagnostics",
    "IdentityDiagnostics",
    "MetricDefinition",
    "MetricValue",
    "ProjectScope",
    "ValueRange",
]
