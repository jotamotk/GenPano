import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Card, MockDataBadge, InfoTooltip } from '../../ui';
import { useLocale } from '../../../contexts/LocaleContext';
import { ProfileGroupSampleWarning } from '../../filters/ProfileGroupFilter';
import {
  BRANDS, ENGINES, INDUSTRIES,
  SOV_DATA, COMPETITOR_SENTIMENT_BUBBLE, TREND_DATA, DIAGNOSTICS,
} from '../../../data/mock';

import HeroBlock from './components/HeroBlock';
import PanelToolbar from './components/PanelToolbar';
import KpiCard from './components/KpiCard';
import KpiSparklineSummary from './components/KpiSparklineSummary';
import AlertBar from './components/AlertBar';
import type { AlertEmptyState, Diagnostic } from './components/AlertBar';
import CrossIndustryWarning from './components/CrossIndustryWarning';
import SovPieChart from './charts/SovPieChart';
import CompetitorQuadrant from './charts/CompetitorQuadrant';
import PanoTrendChart from './charts/PanoTrendChart';

import { asMetricNumber, formatMaybePercent, formatMaybeRank } from './lib/format';
import { PANEL_FALLBACK_BRAND } from './lib/constants';
import { normalizePanelBrand } from './lib/normalize';
import { buildSparklines } from './lib/sparklines';

/* ─────────────────────────────────────────────────────────────
   BrandPanoramaPanel — 单品牌全景视图 (PRD §4.6.1a 市场宏观视角)
   ─────────────────────────────────────────────────────────────
   复用场景:
     - DashboardPage (/dashboard): 当前用户 primaryBrand 为主视角
     - BrandDetailPage.OverviewTab: 任意品牌页概览 Tab, 以 URL :brandId 为主视角

   props:
     primary          — 主品牌 BRAND 对象 (必填)
     industry         — 所在行业 INDUSTRY 对象 (可选; 缺省时回退 primary.industryId 查表)
     competitors      — Top 3 竞品 BRAND[] (可选; 缺省时走知识图谱推荐或空)
     headerSlot       — 页面顶部自定义 header 节点 (可选), 如品牌切换器 / PDF 按钮
     onShareReport    — 分享/导出 PDF 回调 (可选)
     scrollAnchorId   — competition 区块锚点 id, 避免两个挂载点同 id 冲突

   区块构成 (与 DashboardPage 一致):
     ⓪ Hero              品牌名 + PANO Score 紧凑行 + 行业上下文
     ① 5 KPI 核心指标卡   提及率 / SoV / 情感 / 引用份额 / 行业排名
     ② 竞争视图           SoV 饼图 + 竞品四象限气泡图
     ③ 趋势视图           PANO 30d (我 vs Top 3 竞品) + 5 KPI sparkline
     ④ 告警条             Top 3 P0/P1 诊断 → 跳品牌详情诊断 Tab

   样式契约: 颜色全部走 var(--color-*) / .text-themed-*.
*/

export default function BrandPanoramaPanel({
  primary: primaryProp,
  industry,
  competitors: competitorsProp,
  headerSlot,
  scrollAnchorId = 'panorama-competition',
  /* Phase 5 §"mock 退役" — 真实数据接入. 任意 override 为 undefined 时
     回退到 mock 数组, 让没有 Project 的访客仍能看到 demo 数据.
     有 Project + pipeline 已生成数据时, DashboardPage 通过 adapter 把
     /v1/projects/:id/{overview, metrics, competitors/metrics,
     competitors/trends, diagnostics} 的响应注入下面 prop. */
  sovDataOverride,
  bubbleDataOverride,
  trendDataOverride,
  diagnosticsOverride,
  alertEmptyState = 'empty',
  sparklineOverride,
  industryAvgScoreOverride,
  isLive,
}) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { t, formatBrand } = useLocale();
  const primary = useMemo(
    () => normalizePanelBrand(primaryProp, BRANDS[1] || BRANDS[0] || PANEL_FALLBACK_BRAND),
    [primaryProp],
  );

  /* ── Competitors fallback: 若外部没传, 从 knowledge graph / 同行业取 3 个 ── */
  const competitors = useMemo(() => {
    const provided = (competitorsProp || [])
      .filter(Boolean)
      .map((brand) => normalizePanelBrand(brand, primary))
      .slice(0, 3);
    if (provided.length) return provided;
    if (isLive) return [];
    const sameIndustry = BRANDS.filter((b) =>
      b.industryId === primary.industryId && b.id !== primary.id
    );
    return sameIndustry
      .sort((a, b) => b.panoScore - a.panoScore)
      .map((brand) => normalizePanelBrand(brand, primary))
      .slice(0, 3);
  }, [competitorsProp, primary, isLive]);

  /* ── Industry fallback: 若外部没传, 从 primary.industryId 查表 ── */
  const resolvedIndustry = useMemo(() => {
    if (industry) return industry;
    return INDUSTRIES.find((ind) => ind.id === primary.industryId) || null;
  }, [industry, primary.industryId]);

  /* ── Cross-industry detection ── */
  const hasCrossIndustryCompetitors = useMemo(() => {
    if (!primary.industryId) return false;
    return competitors.some((b) => b && b.industryId && b.industryId !== primary.industryId);
  }, [primary.industryId, competitors]);

  /* ── URL filter state ── */
  const [filtersExpanded, setFiltersExpanded] = useState(
    () => searchParams.get('filters') === 'expanded'
  );
  const range = searchParams.get('range') || '30d';
  const engineParam = searchParams.get('engines');
  const dimension = searchParams.get('dimension') || '';
  const intent = searchParams.get('intent') || '';
  const selectedEngines = useMemo(() => (
    engineParam
      ? engineParam.split(',').filter((n) => ENGINES.find((e) => e.name === n))
      : ENGINES.map((e) => e.name)
  ), [engineParam]);

  const setParam = (key, value, defaultValue = '') => {
    const p = new URLSearchParams(searchParams);
    if (value === defaultValue) p.delete(key); else p.set(key, value);
    setSearchParams(p, { replace: true });
  };
  const updateRange = (next) => setParam('range', next, '30d');
  const updateEngines = (next) => {
    const p = new URLSearchParams(searchParams);
    if (next.length === ENGINES.length || next.length === 0) p.delete('engines');
    else p.set('engines', next.join(','));
    setSearchParams(p, { replace: true });
  };
  const toggleEngine = (name) => {
    const next = selectedEngines.includes(name)
      ? selectedEngines.filter((e) => e !== name)
      : [...selectedEngines, name];
    updateEngines(next.length ? next : ENGINES.map((e) => e.name));
  };
  const updateDimension = (next) => setParam('dimension', next, '');
  const updateIntent = (next) => setParam('intent', next, '');
  const toggleFiltersExpanded = () => {
    const next = !filtersExpanded;
    setFiltersExpanded(next);
    setParam('filters', next ? 'expanded' : '', '');
  };

  /* ── KPI values ──
     PRD §4.6-IA-v2.N / DESIGN_TOKENS C11 (2026-04-20): mentionRate stored as
     decimal 0-1; render layer converts to percentage. Prevents "1620%" bug. */
  /* ── Effective data sources ──
     Live mode: use override (may be empty array → chart renders empty state).
     Demo mode (no project): use mock arrays so anonymous visitors see content.
     Important: never silently mix mock with live — once isLive=true, missing
     data shows as empty so operators can see which pipeline parts have gaps. */
  const sovData     = isLive ? (sovDataOverride ?? []) : SOV_DATA;
  const bubbleData  = isLive ? (bubbleDataOverride ?? []) : COMPETITOR_SENTIMENT_BUBBLE;
  const trendData   = isLive ? (trendDataOverride ?? []) : TREND_DATA;

  const mentionRateDec   = asMetricNumber(primary.mentionRate);
  const mentionRateValue = mentionRateDec == null ? null : +(mentionRateDec * 100).toFixed(1);
  const sovEntry         = sovData.find((s) => s.name === primary.name);
  const sovMetricValue   = asMetricNumber(primary.sov);
  const sovValue         = sovMetricValue ?? (sovEntry ? sovEntry.value : null);
  const sentimentValue   = asMetricNumber(primary.sentiment);
  const citationShare    = isLive
    ? (sparklineOverride?.citation?.at(-1) ?? null)
    : 18.2;
  const industryRank     = asMetricNumber(primary.ranking);

  /* ── Sparklines ── (live: from /v1/projects/:id/metrics; mock: synthesized) */
  const { sparkMention, sparkSov, sparkSent, sparkCite, sparkRank } = buildSparklines({
    isLive, trendData, sovValue, industryRank, sparklineOverride,
  });

  const onAlertClick = (d: Diagnostic) => {
    navigate(`/brands/${primary.id}?tab=diagnostics&diagId=${d.id}`);
  };

  const kpis = [
    {
      label: t('dashboard.kpi.mention_rate'),
      fullLabel: t('dashboard.kpi.mention_rate_full'),
      value: formatMaybePercent(mentionRateValue),
      delta: isLive ? undefined : 3.8,
      helpText: t('dashboard.kpi.mention_rate_help'),
      sparkData: sparkMention,
    },
    {
      label: t('dashboard.kpi.sov'),
      fullLabel: t('dashboard.kpi.sov_full'),
      value: formatMaybePercent(sovValue),
      delta: isLive ? undefined : 2.1,
      helpText: t('dashboard.kpi.sov_help'),
      sparkData: sparkSov,
    },
    {
      label: t('dashboard.kpi.sentiment'),
      fullLabel: '',
      value: formatMaybePercent(sentimentValue == null ? null : Math.round(sentimentValue * 100)),
      delta: isLive ? undefined : -2,
      helpText: t('dashboard.kpi.sentiment_help'),
      sparkData: sparkSent,
    },
    {
      label: t('dashboard.kpi.citation_share'),
      fullLabel: '',
      value: formatMaybePercent(citationShare),
      delta: isLive ? undefined : 1.5,
      helpText: t('dashboard.kpi.citation_share_help'),
      sparkData: sparkCite,
    },
    {
      label: t('dashboard.kpi.industry_rank'),
      fullLabel: '',
      value: formatMaybeRank(industryRank, t),
      delta: isLive ? undefined : 1,
      trendIsRank: true,
      helpText: t('dashboard.kpi.industry_rank_help'),
      sparkData: sparkRank,
    },
  ];

  const primaryAlerts = useMemo(() => {
    const source = isLive ? (diagnosticsOverride ?? []) : DIAGNOSTICS;
    return source
      .filter((d) => d.severity === 'P0' || d.severity === 'P1')
      .slice(0, 3);
  }, [isLive, diagnosticsOverride]);

  const sparklineRows = [
    { label: t('dashboard.kpi.mention_rate'),   spark: sparkMention, value: formatMaybePercent(mentionRateValue),    color: 'var(--color-chart-2)' },
    { label: t('dashboard.kpi.sov'),            spark: sparkSov,     value: formatMaybePercent(sovValue),            color: 'var(--color-accent)' },
    { label: t('dashboard.kpi.sentiment'),      spark: sparkSent,    value: formatMaybePercent(sentimentValue == null ? null : Math.round(sentimentValue * 100)), color: 'var(--color-chart-3)' },
    { label: t('dashboard.kpi.citation_share'), spark: sparkCite,    value: formatMaybePercent(citationShare),       color: 'var(--color-chart-4)' },
    { label: t('dashboard.kpi.industry_rank'),  spark: sparkRank,    value: industryRank == null ? '#—' : `#${industryRank}`,        color: 'var(--color-chart-5)' },
  ];

  const industryAvgScore = useMemo(() => {
    if (isLive && industryAvgScoreOverride != null) {
      return Math.round(industryAvgScoreOverride);
    }
    if (isLive) return null;
    const sameBrands = BRANDS.filter((b) => b.industryId === primary.industryId);
    if (!sameBrands.length) return 60;
    return Math.round(sameBrands.reduce((sum, b) => sum + b.panoScore, 0) / sameBrands.length);
  }, [isLive, industryAvgScoreOverride, primary.industryId]);

  return (
    <div className="space-y-4 pb-4">
      {headerSlot}

      {/* ⓪ Hero */}
      <HeroBlock
        primary={primary}
        industry={resolvedIndustry}
        industryAvgScore={industryAvgScore}
        t={t}
        formatBrand={formatBrand}
        isLive={isLive}
        onScoreClick={() => navigate(`/brands/${primary.id}?tab=overview`)}
        onRankClick={() => {
          document.getElementById(scrollAnchorId)?.scrollIntoView({ behavior: 'smooth' });
        }}
      />

      {/* Toolbar */}
      <PanelToolbar
        range={range}
        engines={ENGINES}
        selectedEngines={selectedEngines}
        onRangeChange={updateRange}
        onEngineToggle={toggleEngine}
        onEngineAll={() => updateEngines(ENGINES.map((e) => e.name))}
        dimension={dimension}
        onDimensionChange={updateDimension}
        intent={intent}
        onIntentChange={updateIntent}
        filtersExpanded={filtersExpanded}
        onToggleFilters={toggleFiltersExpanded}
        t={t}
      />

      <ProfileGroupSampleWarning />

      {/* ① 5 KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {kpis.map((k) => (
          <KpiCard key={k.label} {...k} />
        ))}
      </div>

      {/* ② Competition view */}
      <div id={scrollAnchorId} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline mb-1 gap-2">
            <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.competition.sov_pie_title')}</h3>
            <InfoTooltip text={t('dashboard.competition.sov_pie_subtitle')} />
            {!isLive && <MockDataBadge />}
            <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
          </div>
          <SovPieChart data={sovData} primaryName={primary.name} />
        </Card>
        <Card className="p-4">
          <div className="flex items-baseline mb-1 gap-2">
            <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.competition.quadrant_title')}</h3>
            <InfoTooltip text={t('dashboard.competition.quadrant_subtitle')} />
            {!isLive && <MockDataBadge />}
            <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
          </div>
          <CompetitorQuadrant data={bubbleData} primaryName={primary.name} t={t} />
        </Card>
      </div>

      {/* ③ Trend view */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline mb-2 gap-2">
            <h3 className="text-sm font-semibold text-themed-primary">{t('dashboard.trend.pano_title')}</h3>
            {!isLive && <MockDataBadge />}
            <CrossIndustryWarning visible={hasCrossIndustryCompetitors} t={t} />
          </div>
          <PanoTrendChart
            trendData={trendData}
            primaryName={primary.name}
            competitors={competitors}
            isLive={isLive}
            t={t}
          />
        </Card>
        <Card className="p-4">
          <h3 className="text-sm font-semibold text-themed-primary mb-3 flex items-center gap-2">
            {t('dashboard.trend.kpi_summary_title')}
            {!isLive && <MockDataBadge />}
          </h3>
          <KpiSparklineSummary rows={sparklineRows} />
        </Card>
      </div>

      {/* ④ Alert bar */}
      <div>
        <h3 className="text-sm font-semibold text-themed-primary mb-2 px-1">{t('dashboard.alerts.title')}</h3>
        <AlertBar
          diagnostics={primaryAlerts}
          emptyState={alertEmptyState as AlertEmptyState}
          onAlertClick={onAlertClick}
          t={t}
        />
      </div>
    </div>
  );
}
