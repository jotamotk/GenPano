"""GenPano shared ORM package (ADR-004).

This is the SSOT (single source of truth) for SQLAlchemy ORM models across the
entire GenPano stack. Imports:

    from genpano_models import Base, User, BrandMention, ...

Currently houses (Phase R.3 minimum):
- `Base` (DeclarativeBase + naming convention)
- User auth models (`User`, `UserAuthToken`)
- Analyzer mirror models (`BrandMention`, `SentimentDriver`, `CitationSource`,
  `ResponseAnalysis`, `ProductFeatureMention`, `GeoScoreDaily`,
  `IndustryBenchmarkDaily`, `ProductScoreDaily`)

Subsequent phases:
- Phase R.4 (admin → FastAPI) — admin code starts importing from here
- Phase 0 onwards — new tables (projects, diagnostics, alerts, etc.) added here
- Future PR — move package to repo root + adapt geo_tracker imports

Backward compatibility:
- `backend/app/models/__init__.py` re-exports everything from this module so
  existing `from app.models import ...` imports continue to work.
- `backend/app/db/base.py` re-exports `Base` for the same reason.
"""

from genpano_models.analyzer import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    ResponseAnalysis,
    SentimentDriver,
)
from genpano_models.base import Base
from genpano_models.user import User, UserAuthToken

__all__ = [
    "Base",
    "BrandMention",
    "CitationSource",
    "GeoScoreDaily",
    "IndustryBenchmarkDaily",
    "ProductFeatureMention",
    "ProductScoreDaily",
    "ResponseAnalysis",
    "SentimentDriver",
    "User",
    "UserAuthToken",
]
