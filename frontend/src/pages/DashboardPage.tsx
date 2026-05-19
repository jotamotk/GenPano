import React, { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, MetricLabel } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import DashboardEmptyState from '../components/empty/DashboardEmptyState';
import BrandPanoramaPanel from '../components/dashboard/BrandPanoramaPanel';
import { BRANDS, INDUSTRIES } from '../data/mock';
import { useProjects } from '../hooks/useProjects';
import { useBrandOverview, isLiveProjectId } from '../hooks/useBrandOverview';
import { resolveLiveProjectIdForBrand } from '../lib/liveProject';
import {
  useBrandMetrics,
  useCompetitorMetrics,
  useCompetitorTrends,
} from '../hooks/useBrandMetrics';
import { useDiagnostics } from '../hooks/useDiagnostics';
import { useIndustries, useIndustryAvgGeo } from '../hooks/useIndustries';
import {
  adaptOverviewToPrimary,
  adaptCompetitorMetricsToList,
  adaptCompetitorMetricsToSov,
  adaptCompetitorMetricsToBubble,
  adaptOverviewToTrend,
  adaptOverviewToSov,
  adaptCompetitorTrendsToTrendData,
  adaptDiagnostics,
  adaptMetricsToSparklines,
  adaptIndustryAvgGeo,
} from '../adapters/dashboardAdapter';
import {
  brandIdFromSearchParams,
  type ProjectAnalysisParams,
} from '../lib/projectAnalysisFilters';

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

type FormulaStatusPayload = {
  state?: unknown;
  formula_status?: unknown;
  kpi_cards?: Array<{ value?: unknown; formula_status?: unknown }>;
  series?: Array<{
    state?: unknown;
    formula_status?: unknown;
    points?: Array<{ value?: unknown }>;
  }>;
  metric_definition?: { formula_status?: unknown } | null;
  metric_definitions?: Record<string, { formula_status?: unknown }>;
};

function nonOkStatus(value: unknown) {
  const text = String(value ?? '').trim().toLowerCase();
  return Boolean(text && text !== 'ok');
}

function finiteMetric(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value);
}

function metricUnavailable(value: unknown) {
  return value == null || !Number.isFinite(Number(value));
}

function hasAnalyticsGap(payload: FormulaStatusPayload | null | undefined) {
  if (!payload) return false;
  if (nonOkStatus(payload.state) || nonOkStatus(payload.formula_status)) return true;
  if (payload.metric_definition && nonOkStatus(payload.metric_definition.formula_status)) return true;
  if (
    payload.metric_definitions &&
    Object.values(payload.metric_definitions).some((definition) => nonOkStatus(definition?.formula_status))
  ) {
    return true;
  }
  if (Array.isArray(payload.kpi_cards)) {
    if (payload.kpi_cards.length === 0) return true;
    if (
      payload.kpi_cards.some((card) => nonOkStatus(card.formula_status) || metricUnavailable(card.value))
    ) {
      return true;
    }
  }
  if (Array.isArray(payload.series)) {
    if (payload.series.length === 0) return true;
    return payload.series.some((series) => (
      nonOkStatus(series.state) ||
      nonOkStatus(series.formula_status) ||
      !Array.isArray(series.points) ||
      !series.points.some((point) => finiteMetric(point.value))
    ));
  }
  return false;
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

  /* ?brandId=X URL param lets the BrandPicker (sidebar) view this
     dashboard for a different brand than the project's primary, e.g.
     viewing 雅诗兰黛's panorama from a sports-shoes project. The
     backend resolves the override against the same project context. */
  const brandIdOverride = brandIdFromSearchParams(searchParams);
  const liveProjectId = resolveLiveProjectIdForBrand(liveProjects, activeProject, brandIdOverride);
  const isLive = isLiveProjectId(liveProjectId);
  const resolvedLiveProject = useMemo(
    () => liveProjects?.find((project) => project.id === liveProjectId) ?? null,
    [liveProjects, liveProjectId],
  );
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

  // Industry avg GEO depends on the project's industry_id (from overview).
  // We also pass the resolved industry name so the backend can short-circuit
  // its position-based `industry_id`→name lookup — see issue #975.
  const liveIndustriesQ = useIndustries();
  const liveIndustryId = overviewQ.data?.industry_id ?? null;
  const liveIndustryName = useMemo(() => {
    if (!isLive || liveIndustryId == null) return undefined;
    const row = liveIndustriesQ.data?.find((ind) => ind.industry_id === liveIndustryId);
    return row?.name || undefined;
  }, [isLive, liveIndustryId, liveIndustriesQ.data]);
  const industryAvgQ = useIndustryAvgGeo(
    isLive && liveIndustryId ? liveIndustryId : null,
    liveIndustryName ? { name: liveIndustryName } : undefined,
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
      competitorTrendsQ.data && Array.isArray(competitorTrendsQ.data.series) && competitorTrendsQ.data.series.length > 0
        ? adaptCompetitorTrendsToTrendData(
            competitorTrendsQ.data,
            overviewQ.data ?? null,
            metricsQ.data ?? null,
          )
        : overviewQ.data
          ? adaptOverviewToTrend(overviewQ.data)
          : [];
    const competitorSov = competitorsQ.data
      ? adaptCompetitorMetricsToSov(competitorsQ.data)
      : [];
    const overviewSov = overviewQ.data ? adaptOverviewToSov(overviewQ.data) : [];
    return {
      primary: primaryFromBackend,
      competitors: compsList.competitors,
      sov: competitorSov.length > 0 ? competitorSov : overviewSov,
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
        ? adaptDiagnostics(diagnosticsQ.data.items ?? [])
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
     Live mode prefers backend-derived identity only; metric gaps stay null so
     the panel renders unavailable states instead of mock/zero values. */
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
  // Live mode: backend industry_id is numeric; mock INDUSTRIES uses string keys
  // (e.g. 'beauty'), so the lookup above always returns null for real projects
  // and the hero shows "行业: —". Resolve against the live /industries list
  // (`liveIndustriesQ` is fetched above for the avg-geo-score call).
  const liveIndustry = useMemo(() => {
    if (!isLive) return null;
    const industryId = overviewQ.data?.industry_id;
    if (industryId == null) return null;
    const row = liveIndustriesQ.data?.find((ind) => ind.industry_id === industryId);
    if (!row) return null;
    return { id: row.industry_id, name: row.nameZh || row.name, nameEn: row.nameEn };
  }, [isLive, overviewQ.data?.industry_id, liveIndustriesQ.data]);
  const industryForPanel = liveIndustry ?? mockIndustry;
  const mockCompetitors = (project?.competitorBrandIds || [])
    .map((id) => BRANDS.find((b) => b.id === id))
    .filter(Boolean)
    .slice(0, 3);

  // Augment backend primary with id/industryId while keeping live metric gaps
  // unavailable unless the backend supplied usable values.
  const liveEmptyPrimary = {
    ...defaultPrimary,
    id: String(resolvedLiveProject?.primary_brand_id || activeProject?.primaryBrandId || liveProjectId || 'live-brand'),
    name: resolvedLiveProject?.name || activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    nameZh: resolvedLiveProject?.name || activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    nameEn: resolvedLiveProject?.name || activeProject?.primaryBrandName || activeProject?.name || 'Brand',
    panoScore: null,
    mentionRate: null,
    sentiment: null,
    ranking: null,
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

  // Live competitors come only from /competitors/metrics; missing rows stay empty.
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

  const alertEmptyState = useMemo(() => {
    if (!isLive) return 'empty';
    if (
      overviewQ.isLoading ||
      metricsQ.isLoading ||
      competitorsQ.isLoading ||
      competitorTrendsQ.isLoading ||
      diagnosticsQ.isLoading
    ) {
      return 'loading';
    }
    if (
      overviewQ.error ||
      metricsQ.error ||
      competitorsQ.error ||
      competitorTrendsQ.error ||
      diagnosticsQ.error
    ) {
      return 'unavailable';
    }
    const hasPayloadGap = [
      overviewQ.data,
      metricsQ.data,
      competitorsQ.data,
      competitorTrendsQ.data,
    ].some((payload) => hasAnalyticsGap(payload));
    const hasKpiGap = [
      primaryForPanel.panoScore,
      primaryForPanel.mentionRate,
      primaryForPanel.sov,
      primaryForPanel.sentiment,
      primaryForPanel.ranking,
    ].some(metricUnavailable);
    const hasCitationGap = !adapted?.sparklines?.citation?.some(finiteMetric);
    if (!diagnosticsQ.data || hasPayloadGap || hasKpiGap || hasCitationGap) {
      return 'incomplete';
    }
    return 'empty';
  }, [
    isLive,
    overviewQ.isLoading,
    metricsQ.isLoading,
    competitorsQ.isLoading,
    competitorTrendsQ.isLoading,
    diagnosticsQ.isLoading,
    overviewQ.error,
    metricsQ.error,
    competitorsQ.error,
    competitorTrendsQ.error,
    diagnosticsQ.error,
    overviewQ.data,
    metricsQ.data,
    competitorsQ.data,
    competitorTrendsQ.data,
    diagnosticsQ.data,
    primaryForPanel.panoScore,
    primaryForPanel.mentionRate,
    primaryForPanel.sov,
    primaryForPanel.sentiment,
    primaryForPanel.ranking,
    adapted?.sparklines,
  ]);

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
    <>
      <BrandPanoramaPanel
        primary={primaryForPanel}
        industry={industryForPanel}
        competitors={competitorsForPanel}
        headerSlot={header}
        scrollAnchorId="dashboard-competition"
        sovDataOverride={adapted?.sov}
        bubbleDataOverride={adapted?.bubble}
        trendDataOverride={adapted?.trend}
        diagnosticsOverride={adapted?.diagnostics}
        alertEmptyState={alertEmptyState}
        sparklineOverride={adapted?.sparklines ?? undefined}
        industryAvgScoreOverride={adapted?.industryAvg ?? undefined}
        isLive={isLive}
      />
    </>
  );
}
