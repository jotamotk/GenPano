import React, { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, MetricLabel } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import DashboardEmptyState from '../components/empty/DashboardEmptyState';
import BrandPanoramaPanel from '../components/dashboard/BrandPanoramaPanel';
import AnalyticsVisualizationContract from '../components/dashboard/AnalyticsVisualizationContract';
import { BRANDS, INDUSTRIES } from '../data/mock';
import { useProjects } from '../hooks/useProjects';
import { useBrandOverview, isLiveProjectId } from '../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../lib/liveProject';
import {
  useBrandMetrics,
  useCompetitorMetrics,
  useCompetitorTrends,
} from '../hooks/useBrandMetrics';
import { useDiagnostics } from '../hooks/useDiagnostics';
import { useIndustryAvgGeo } from '../hooks/useIndustries';
import {
  adaptOverviewToPrimary,
  adaptCompetitorMetricsToList,
  adaptCompetitorMetricsToSov,
  adaptCompetitorMetricsToBubble,
  adaptOverviewToTrend,
  adaptCompetitorTrendsToTrendData,
  adaptDiagnostics,
  adaptMetricsToSparklines,
  adaptIndustryAvgGeo,
} from '../adapters/dashboardAdapter';
import type { ProjectAnalysisParams } from '../lib/projectAnalysisFilters';

function isoOffset(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function engineId(raw: string) {
  const value = raw.trim().toLowerCase();
  if (!value) return '';
  if (value.includes('豆包') || value.includes('doubao')) return 'doubao';
  if (value.includes('deepseek')) return 'deepseek';
  if (value.includes('chatgpt') || value.includes('chat')) return 'chatgpt';
  return value;
}

/* ─────────────────────────────────────────────────────────────
   DashboardPage ("我的品牌") — PRD §4.6.1a 市场宏观视角
   ─────────────────────────────────────────────────────────────
   Data flow (Phase 5 §"mock 退役"):
     1. useProjects() resolves the current user's first live Project
        (UUID-shaped id).
     2. When live: hooks fetch overview / competitors / diagnostics
        from /v1/projects/:id/{overview, competitors/metrics, diagnostics};
        adapter functions reshape them into the prop format
        BrandPanoramaPanel's chart sub-components consume; the panel
        renders 100% real-data charts.
     3. When no project (anonymous / pre-onboarding): the panel falls
        back to its existing mock arrays so the demo experience is
        preserved without showing an empty page.
   The PRD viz layout is identical in both modes — only the data
   source switches transparently.
*/
export default function DashboardPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { projects, activeProject } = useProject();
  const { data: liveProjects } = useProjects();
  const [searchParams] = useSearchParams();

  /* ── PRD §4.1.1d E1: Zero-Project early-return (MANDATORY) ──
     Skip the empty state when the user has at least one real project
     in the backend. */
  if (projects.length === 0 && (!liveProjects || liveProjects.length === 0)) {
    return <DashboardEmptyState />;
  }

  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);
  const showAnalyticsVisualizationContract =
    searchParams.get('viz') === 'analytics-contract';

  /* ?brandId=X URL param lets the BrandPicker (sidebar) view this
     dashboard for a different brand than the project's primary, e.g.
     viewing 雅诗兰黛's panorama from a sports-shoes project. The
     backend resolves the override against the same project context. */
  const brandIdParam = searchParams.get('brandId');
  const brandIdOverride =
    brandIdParam && /^\d+$/.test(brandIdParam) ? Number(brandIdParam) : null;
  const analysisFilters = useMemo<ProjectAnalysisParams>(() => {
    const range = searchParams.get('range') || '30d';
    const days = range === '7d' ? 7 : range === '90d' ? 90 : 30;
    const profileGroup = searchParams.get('profileGroup') || 'all';
    const engines = (searchParams.get('engines') || '')
      .split(',')
      .map(engineId)
      .filter(Boolean);
    const next: ProjectAnalysisParams = {
      from: isoOffset(days),
      to: new Date().toISOString().slice(0, 10),
    };
    if (engines.length) next.engine = engines.join(',');
    if (profileGroup && profileGroup !== 'all') {
      if (profileGroup.startsWith('profile:')) {
        next.profile_id = profileGroup.slice('profile:'.length);
      } else {
        next.segment_id = profileGroup;
      }
    }
    const dimension = searchParams.get('dimension');
    const intent = searchParams.get('intent');
    if (dimension) next.dimension = dimension;
    if (intent) next.intent = intent;
    return next;
  }, [searchParams]);

  /* ── Live data hooks (gated on isLive — mock-only sessions skip) ── */
  const overviewQ = useBrandOverview(isLive ? liveProjectId : null, brandIdOverride);
  const metricsQ = useBrandMetrics(
    isLive ? liveProjectId : null,
    ['mention_rate', 'sov', 'sentiment', 'rank', 'citation'],
    brandIdOverride,
    analysisFilters,
  );
  const competitorsQ = useCompetitorMetrics(
    isLive ? liveProjectId : null,
    brandIdOverride,
    analysisFilters,
  );
  const competitorTrendsQ = useCompetitorTrends(
    isLive ? liveProjectId : null,
    'geo_score',
    brandIdOverride,
    analysisFilters,
  );
  const diagnosticsQ = useDiagnostics(isLive ? liveProjectId : null, {
    status: 'open',
    limit: 5,
  });

  // Industry avg GEO depends on the project's industry_id (from overview)
  const liveIndustryId = overviewQ.data?.industry_id ?? null;
  const industryAvgQ = useIndustryAvgGeo(
    isLive && liveIndustryId ? liveIndustryId : null,
  );

  /* ── Adapter: convert backend → BrandPanoramaPanel prop shape ── */
  const adapted = useMemo(() => {
    if (!isLive) return null;
    const compsList = competitorsQ.data
      ? adaptCompetitorMetricsToList(competitorsQ.data)
      : { primary: null, competitors: [] };
    const overviewPrimary = overviewQ.data
      ? adaptOverviewToPrimary(overviewQ.data)
      : null;
    const primaryFromBackend = overviewPrimary ?? compsList.primary;
    // Prefer per-competitor 30d trends when available — gives real
    // competitor lines on the trend chart instead of synthetic sin curves.
    const trend =
      competitorTrendsQ.data && competitorTrendsQ.data.series.length > 0
        ? adaptCompetitorTrendsToTrendData(
            competitorTrendsQ.data,
            overviewQ.data ?? null,
          )
        : overviewQ.data
          ? adaptOverviewToTrend(overviewQ.data)
          : [];
    return {
      primary: primaryFromBackend,
      competitors: compsList.competitors,
      sov: competitorsQ.data
        ? adaptCompetitorMetricsToSov(competitorsQ.data)
        : [],
      bubble: competitorsQ.data
        ? adaptCompetitorMetricsToBubble(competitorsQ.data)
        : [],
      trend,
      sparklines: metricsQ.data
        ? adaptMetricsToSparklines(metricsQ.data)
        : null,
      industryAvg: industryAvgQ.data
        ? adaptIndustryAvgGeo(industryAvgQ.data)
        : null,
      diagnostics: diagnosticsQ.data
        ? adaptDiagnostics(diagnosticsQ.data.items)
        : [],
    };
  }, [
    isLive,
    overviewQ.data,
    competitorsQ.data,
    competitorTrendsQ.data,
    metricsQ.data,
    industryAvgQ.data,
    diagnosticsQ.data,
  ]);

  /* ── primary / industry / competitors props for the panel ──
     Live mode prefers backend-derived; fall back to mock to keep the
     panel from crashing if Project is misconfigured. */
  const project = activeProject;
  const defaultPrimary = BRANDS[1] || BRANDS[0] || {
    id: 'fallback-brand',
    name: 'Brand',
    nameZh: 'Brand',
    nameEn: 'Brand',
    industryId: '',
    panoScore: 0,
    mentionRate: 0,
    sentiment: 0,
    ranking: 1,
  };
  const mockPrimary =
    BRANDS.find((b) => String(b.id) === String(project?.primaryBrandId)) ||
    defaultPrimary;
  const mockIndustry =
    INDUSTRIES.find((ind) => ind.id === project?.industryId) || null;
  const mockCompetitors = (project?.competitorBrandIds || [])
    .map((id) => BRANDS.find((b) => b.id === id))
    .filter(Boolean)
    .slice(0, 3);

  // Augment backend primary with id/industryId so panel competitor
  // fallback by industry still works in live mode (if industry id matches
  // mock), without losing the live KPIs.
  const liveEmptyPrimary = {
    ...defaultPrimary,
    id: String(activeProject?.primaryBrandId || liveProjectId || 'live-brand'),
    name: activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    nameZh: activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    nameEn: activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    panoScore: 0,
    mentionRate: 0,
    sentiment: 0,
    ranking: 1,
  };
  const primaryForPanel =
    adapted?.primary
      ? {
          ...liveEmptyPrimary,
          ...adapted.primary,
          nameZh: adapted.primary.nameZh || adapted.primary.name,
          nameEn: adapted.primary.nameEn || adapted.primary.name,
        }
      : isLive
        ? liveEmptyPrimary
        : mockPrimary;

  // Live competitors come from /competitors/metrics; if backend returned
  // any rows, use them. Otherwise fall back to mock pinned competitors.
  const competitorsForPanel =
    adapted && adapted.competitors.length > 0
      ? adapted.competitors.map((c) => ({
          ...liveEmptyPrimary,
          ...c,
          industryId: primaryForPanel.industryId,
        }))
      : isLive
        ? []
        : mockCompetitors;

  const header = (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-baseline gap-3">
        <MetricLabel helpText={t('dashboard.page_help')} className="text-sm text-themed-muted font-medium">
          {t('dashboard.page_subtitle')}
        </MetricLabel>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => navigate('/project-settings')}>
          {t('dashboard.toolbar.project_settings')}
        </Button>
        <Button variant="primary" size="sm" onClick={() => navigate(`/brands/${primaryForPanel.id}?tab=diagnostics`)}>
          {t('dashboard.toolbar.share_pdf')}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {showAnalyticsVisualizationContract && <AnalyticsVisualizationContract />}
      <BrandPanoramaPanel
        primary={primaryForPanel}
        industry={mockIndustry}
        competitors={competitorsForPanel}
        headerSlot={header}
        scrollAnchorId="dashboard-competition"
        sovDataOverride={adapted?.sov}
        bubbleDataOverride={adapted?.bubble}
        trendDataOverride={adapted?.trend}
        diagnosticsOverride={adapted?.diagnostics}
        sparklineOverride={adapted?.sparklines ?? undefined}
        industryAvgScoreOverride={adapted?.industryAvg ?? undefined}
        isLive={isLive}
      />
    </div>
  );
}
