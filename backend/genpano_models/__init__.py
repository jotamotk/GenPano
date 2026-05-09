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

from genpano_models.admin_console import (
    AdminLoginAttempt,
    AdminUser,
    BrandContextSnapshot,
    BrandGenerationLog,
    Profile,
    PromptCandidate,
    PromptGenerationRun,
    QueryGenerationCandidate,
    QueryGenerationRun,
    Segment,
    TopicCandidate,
    TopicPlanRun,
    UserModerationAction,
)
from genpano_models.admin_ops import (
    AdminAuditLog,
    BudgetThreshold,
    CommsAnnouncement,
    CostEvent,
    DiscoveryLog,
    EngineHealthDaily,
    McpCallLog,
    ProxyHealthDaily,
)
from genpano_models.alert import (
    Alert,
    AlertRule,
    UserNotificationPreferences,
)
from genpano_models.analyzer import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    ResponseAnalysis,
    SentimentDriver,
    TopicScoreDaily,
)
from genpano_models.analyzer_phase_a import (
    BrandGroup,
    BrandGroupMember,
    BrandGroupSharedDomain,
    BrandOfficialDomain,
    CitationWeeklyByDomain,
    CompetitorMentionDaily,
    DomainAuthority,
    GeoScoreWeekly,
    IndustryTopicDaily,
)
from genpano_models.api_key import Organization, UserApiKey
from genpano_models.base import Base
from genpano_models.brand_submission import BrandSubmission
from genpano_models.commercial_lead import CommercialLead
from genpano_models.crawl_request import CrawlRequest
from genpano_models.diagnostic import Diagnostic
from genpano_models.export_job import ExportJob
from genpano_models.industry_pricing import IndustryPricingParams
from genpano_models.kg import (
    KgBrand,
    KgBrandRelation,
    KgCategory,
    KgProduct,
    KgProductRelation,
    KgRelationCandidate,
)
from genpano_models.project import Project, ProjectCompetitor, ProjectTopicPin
from genpano_models.report import ReportJob, ReportSchedule, ReportShareToken
from genpano_models.user import User, UserAuthToken

__all__ = [
    "AdminAuditLog",
    "AdminLoginAttempt",
    "AdminUser",
    "Alert",
    "AlertRule",
    "Base",
    "BrandContextSnapshot",
    "BrandGenerationLog",
    "BrandGroup",
    "BrandGroupMember",
    "BrandGroupSharedDomain",
    "BrandMention",
    "BrandOfficialDomain",
    "BrandSubmission",
    "BudgetThreshold",
    "CitationSource",
    "CitationWeeklyByDomain",
    "CommercialLead",
    "CommsAnnouncement",
    "CompetitorMentionDaily",
    "CostEvent",
    "CrawlRequest",
    "Diagnostic",
    "DiscoveryLog",
    "DomainAuthority",
    "EngineHealthDaily",
    "ExportJob",
    "GeoScoreDaily",
    "GeoScoreWeekly",
    "IndustryBenchmarkDaily",
    "IndustryPricingParams",
    "IndustryTopicDaily",
    "KgBrand",
    "KgBrandRelation",
    "KgCategory",
    "KgProduct",
    "KgProductRelation",
    "KgRelationCandidate",
    "McpCallLog",
    "Organization",
    "ProductFeatureMention",
    "ProductScoreDaily",
    "Profile",
    "Project",
    "ProjectCompetitor",
    "ProjectTopicPin",
    "PromptCandidate",
    "PromptGenerationRun",
    "ProxyHealthDaily",
    "QueryGenerationCandidate",
    "QueryGenerationRun",
    "ReportJob",
    "ReportSchedule",
    "ReportShareToken",
    "ResponseAnalysis",
    "Segment",
    "SentimentDriver",
    "TopicCandidate",
    "TopicPlanRun",
    "TopicScoreDaily",
    "User",
    "UserApiKey",
    "UserAuthToken",
    "UserModerationAction",
    "UserNotificationPreferences",
]
