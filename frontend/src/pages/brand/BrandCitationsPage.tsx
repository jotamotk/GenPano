import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, Button, MockDataBadge, InfoTooltip, MetricLabel } from '../../components/ui';
import { TrendChart, DonutChart } from '../../components/charts';
import ContentGapPanel from '../../components/citation/ContentGapPanel';
import PrTargetsPanel from '../../components/citation/PrTargetsPanel';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../../lib/liveProject';
import { toProjectAnalysisParams } from '../../lib/projectAnalysisFilters';
import { useBrandCitations } from '../../hooks/useBrandMetrics';
import {
  useAuthorityTrend,
  useCitationComposition,
  useContentGap,
  usePrTargets,
  useSimulatorBaseline,
} from '../../hooks/useCharts';
import {
  adaptAuthorityTrend,
  adaptCitationComposition,
  adaptContentGap,
  adaptPrTargets,
  adaptSimulatorBaseline,
} from '../../adapters/chartAdapters';
import {
  BRANDS,
  AUTHORITY_SHARE_SERIES,
  CITATION_SOURCE_COMPOSITION,
  TOP_CITED_DOMAINS,
  TOP_CITED_PAGES,
  CONTENT_GAP_TOPICS,
  CONTENT_GAP_PAGE_TYPE_DISTRIBUTION,
  PR_TARGETS,
  TIER2_COVERAGE_MATRIX,
  KOL_SCORECARDS,
  SIMULATOR_BASELINE,
  SIMULATOR_PRESETS,
} from '../../data/mock';

function finiteNumberOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function formatMaybeNumber(value) {
  const next = finiteNumberOrNull(value);
  return next == null ? '--' : next;
}

/* ─────────────────────────────────────────────────────────────
   BrandCitationsPage — /brand/citations (§4.6-IA-v2.C.2.2 + §4.2.7)
   ─────────────────────────────────────────────────────────────
   Citation 归因 / Authority Share / Content Gap / PR 目标. 用 ?sub=
   参数切换子视图 (overview / content-gap / pr-targets / simulator).
*/
export default function BrandCitationsPage() {
  const [params, setParams] = useSearchParams();
  const sub = params.get('sub') || 'overview';
  const { t, formatNumber } = useLocale();
  const { activeProject } = useProject();
  const primary = BRANDS.find((b) => b.id === activeProject?.primaryBrandId) || BRANDS[1];
  const { filters } = useBrandAnalysisFilters(); // C10
  const chartFilters = toProjectAnalysisParams(filters);

  // ── Live data hooks ──
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);
  const citationsQ = useBrandCitations(isLive ? liveProjectId : null, 50, chartFilters);
  const authorityTrendQ = useAuthorityTrend(isLive ? liveProjectId : null, chartFilters);
  const compositionQ = useCitationComposition(isLive ? liveProjectId : null, chartFilters);
  const contentGapQ = useContentGap(isLive ? liveProjectId : null, 12, chartFilters);
  const prTargetsQ = usePrTargets(isLive ? liveProjectId : null);
  const simulatorQ = useSimulatorBaseline(isLive ? liveProjectId : null);

  // Authority share trend
  const liveAuthority = adaptAuthorityTrend(authorityTrendQ.data);
  const authoritySeries = isLive ? liveAuthority : AUTHORITY_SHARE_SERIES;
  const authorityIsMock = !isLive;

  // Citation composition donut
  const liveComposition = adaptCitationComposition(compositionQ.data);
  const compositionData = isLive ? liveComposition : CITATION_SOURCE_COMPOSITION;
  const compositionIsMock = !isLive;

  // Top domains: prefer /citations response.by_domain_top (already has tier).
  const liveDomains =
    isLive && citationsQ.data?.state === 'ok' && Array.isArray(citationsQ.data.by_domain_top)
      ? citationsQ.data.by_domain_top.map((d) => ({
          domain: d.domain,
          tier: d.tier ?? null,
          count: d.count,
        }))
      : [];
  const topDomains = isLive ? liveDomains : TOP_CITED_DOMAINS;
  const topDomainsIsMock = !isLive;

  // Top cited pages: from /citations.items
  const livePages =
    isLive && citationsQ.data?.state === 'ok' && Array.isArray(citationsQ.data.items)
      ? Array.from(
          citationsQ.data.items.reduce<Map<string, { url: string; title: string; tier: number | null; count: number }>>(
            (acc, c) => {
              const key = c.url;
              const existing = acc.get(key);
              if (existing) existing.count += 1;
              else
                acc.set(key, {
                  url: c.url,
                  title: c.title || c.domain || c.url,
                  tier: c.tier ?? null,
                  count: 1,
                });
              return acc
            },
            new Map(),
          ).values(),
        )
          .sort((a, b) => b.count - a.count)
          .slice(0, 6)
      : [];
  const topPages = isLive ? livePages : TOP_CITED_PAGES;
  const topPagesIsMock = !isLive;

  // Content Gap
  const liveGap = adaptContentGap(contentGapQ.data);
  const contentGapTopicsLive =
    isLive
      ? liveGap.topics.map((t, i) => ({
          topicName: t.topicName,
          mentionRate: t.mentionRate,
          citationRate: t.citationRate,
          gap: t.gap,
          suggestion: t.suggestion ?? '',
          rank: i + 1,
        }))
      : CONTENT_GAP_TOPICS;
  const contentGapDistLive = isLive
    ? liveGap.pageTypeDistribution
    : CONTENT_GAP_PAGE_TYPE_DISTRIBUTION;
  const contentGapIsMock = !isLive;

  // PR Targets
  const livePr = adaptPrTargets(prTargetsQ.data);
  const prTargets = isLive ? livePr.targets : PR_TARGETS;
  const prMatrix = isLive ? livePr.tier2Matrix : TIER2_COVERAGE_MATRIX;
  const prKols = isLive ? livePr.kolScorecards : KOL_SCORECARDS;
  const prIsMock = !isLive;

  // Simulator
  const liveSim = simulatorQ.data?.state === 'ok'
    ? adaptSimulatorBaseline(simulatorQ.data)
    : null;
  const simulatorBaseline =
    isLive
      ? liveSim
      : SIMULATOR_BASELINE;
  const simulatorPresets = isLive ? (liveSim?.presets ?? []) : SIMULATOR_PRESETS;
  const simulatorIsMock = !isLive;

  const setSub = (next) => {
    const nextParams = new URLSearchParams(params);
    if (next === 'overview') nextParams.delete('sub');
    else nextParams.set('sub', next);
    setParams(nextParams, { replace: true });
  };

  const subTabs = [
    { id: 'overview',     label: t('brand_citations.sub_overview') },
    { id: 'content-gap',  label: t('brand_citations.sub_content_gap') },
    { id: 'pr-targets',   label: t('brand_citations.sub_pr_targets') },
    { id: 'simulator',    label: t('brand_citations.sub_simulator') },
  ];

  return (
    <div className="space-y-4">
      {/* Page header */}
      <header>
        <h2 className="text-2xl font-brand font-bold text-themed-primary">
          <MetricLabel helpText={t('brand_citations.page_subtitle', { brand: primary.name })}>
            {t('brand_citations.page_title')}
          </MetricLabel>
        </h2>
      </header>

      {/* Shared filter bar */}
      <BrandAnalysisFilterBar />

      {/* Sub-view tabs — FilterPill style */}
      <div className="flex items-center gap-2 flex-wrap">
        {subTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setSub(tab.id)}
            className={`px-3 py-1.5 rounded-pill text-xs font-medium transition-colors ${
              sub === tab.id
                ? 'text-themed-accent'
                : 'text-themed-muted'
            }`}
            style={sub === tab.id
              ? { background: 'var(--color-accent-bg-light)' }
              : { background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {sub === 'overview' && (
        <div className="space-y-4">
          {/* Authority share trend */}
          <Card className="p-4">
            <div className="flex items-baseline justify-between mb-3">
              <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
                {t('brand_citations.authority_trend_title')}
                <InfoTooltip text={t('brand_citations.authority_trend_subtitle')} />
                {authorityIsMock && <MockDataBadge />}
              </h3>
            </div>
            <TrendChart
              data={authoritySeries.map((d: any) => ({ name: d.date, ...d }))}
              lines={[
                { key: 'official_domain_pct', label: t('brand_citations.official_domain'), color: 'var(--color-accent)', area: true },
                { key: 'co_occurrence_pct', label: t('brand_citations.co_occurrence'), color: 'var(--color-chart-3)', area: false },
                { key: 'text_match_pct', label: t('brand_citations.text_match'), color: 'var(--color-chart-line-grid)', area: false, dashed: true },
              ]}
              height={260}
            />
          </Card>

          {/* Source composition + top domains */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-themed-primary mb-3 flex items-center gap-2">
                {t('brand_citations.composition_title')}
                {compositionIsMock && <MockDataBadge />}
              </h3>
              <DonutChart segments={compositionData} size={200} />
            </Card>
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-themed-primary mb-3 flex items-center gap-2">
                {t('brand_citations.top_domains_title')}
                {topDomainsIsMock && <MockDataBadge />}
              </h3>
              <div className="space-y-2">
                {(topDomains || []).slice(0, 8).map((d: any) => (
                  <div key={d.domain} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="muted">{`T${d.tier ?? '?'}`}</Badge>
                      <span className="text-sm text-themed-primary">{d.domain}</span>
                    </div>
                    <span className="text-sm text-themed-muted tabular-nums">{formatNumber(d.count)}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Top cited pages */}
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-themed-primary mb-3 flex items-center gap-2">
              {t('brand_citations.top_pages_title')}
              {topPagesIsMock && <MockDataBadge />}
            </h3>
            <div className="space-y-2">
              {(topPages || []).slice(0, 6).map((p: any, i: number) => (
                <a
                  key={i}
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block p-3 rounded-btn bg-themed-subtle hover:bg-themed-card transition-colors"
                >
                  <div className="text-sm font-medium text-themed-primary truncate">{p.title}</div>
                  <div className="text-xs text-themed-muted truncate mt-0.5">{p.url}</div>
                  <div className="text-xs text-themed-muted mt-1">
                    {formatNumber(p.count)} × · Tier {p.tier ?? '?'}
                  </div>
                </a>
              ))}
            </div>
          </Card>
        </div>
      )}

      {sub === 'content-gap' && (
        <div>
          {contentGapIsMock && (
            <div className="mb-2"><MockDataBadge reason="缺少 topic_score_daily 数据" /></div>
          )}
          <ContentGapPanel
            topics={contentGapTopicsLive}
            distribution={contentGapDistLive}
            maxTopics={20}
          />
        </div>
      )}

      {sub === 'pr-targets' && (
        <div>
          {prIsMock && (
            <div className="mb-2"><MockDataBadge reason="缺少 PR/KOL 真实数据" /></div>
          )}
          <PrTargetsPanel
            targets={prTargets}
            tier2Matrix={prMatrix}
            kolScorecards={prKols}
          />
        </div>
      )}

      {sub === 'simulator' && (
        <div>
          {simulatorIsMock && (
            <div className="mb-2"><MockDataBadge reason="缺少 geo_score_weekly 真实数据" /></div>
          )}
          {simulatorBaseline ? (
            <AuthoritySimulator baseline={simulatorBaseline} presets={simulatorPresets} />
          ) : (
            <Card className="p-4 text-sm text-themed-muted">
              暂无模拟器基线数据。
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   AuthoritySimulator — PRD §4.2.7.E
   Tier 权重模拟器: 4 个滑块 (Tier 1-4 delta) + 3 个预设 + PANO 计算
   ─────────────────────────────────────────────────────────────── */
function AuthoritySimulator({ baseline, presets }) {
  const { t, formatNumber } = useLocale();
  const [deltas, setDeltas] = useState([0, 0, 0, 0]); // [T1, T2, T3, T4]

  const tiers = [1, 2, 3, 4];

  const calculated = useMemo(() => {
    // Calculate new PANO A based on baseline + deltas
    const weights = baseline.tierWeights || {};
    const confidence = baseline.defaultConfidence || {};
    let panoDelta = 0;

    tiers.forEach((tier, i) => {
      const weight = weights[tier] ?? 0;
      const conf = confidence[tier] ?? 0;
      const delta = deltas[i] || 0;
      // Contribution = weight × (delta count) × confidence
      panoDelta += weight * delta * conf;
    });

    const newPanoA = baseline.currentPanoA + panoDelta;

    return {
      newPanoA: Math.max(0, Math.min(100, newPanoA)), // Clamp 0-100
      panoDelta: Math.round(panoDelta * 10) / 10,
    };
  }, [deltas, baseline]);

  const handleDeltaChange = (idx, val) => {
    const newDeltas = [...deltas];
    newDeltas[idx] = parseInt(val, 10) || 0;
    setDeltas(newDeltas);
  };

  const applyPreset = (preset) => {
    const newDeltas = [0, 0, 0, 0];
    tiers.forEach((tier, i) => {
      newDeltas[i] = preset.deltaByTier?.[tier] || 0;
    });
    setDeltas(newDeltas);
  };

  const resetDeltas = () => {
    setDeltas([0, 0, 0, 0]);
  };

  const panoStatus = useMemo(() => {
    const delta = calculated.panoDelta;
    const current = finiteNumberOrNull(baseline.currentPanoA);
    const top3 = finiteNumberOrNull(baseline.industryTop3Avg);
    const median = finiteNumberOrNull(baseline.industryMedian);
    if (current != null && top3 != null && delta >= top3 - current) {
      return { label: '超越 Top 3 平均', color: 'var(--color-success)' };
    }
    if (current != null && median != null && delta >= median - current) {
      return { label: '达到行业中位', color: 'var(--color-accent)' };
    }
    if (delta > 0) {
      return { label: '有改善', color: 'var(--color-accent)' };
    }
    return { label: '保持现状', color: 'var(--color-text-muted)' };
  }, [calculated, baseline]);

  return (
    <div className="space-y-4">
      {/* Baseline info card */}
      <Card className="p-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <div className="flex items-baseline justify-between mb-2">
              <h3 className="text-sm font-semibold text-themed-primary">
                {t('brand_citations.simulator_current_status') || '当前状态'}
              </h3>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-themed-muted">主品牌 PANO 评分</span>
                <span className="text-lg font-bold text-themed-primary tabular-nums">
                  {baseline.currentPanoA}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-themed-muted">行业中位</span>
                <span className="text-sm text-themed-primary tabular-nums">
                  {formatMaybeNumber(baseline.industryMedian)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-themed-muted">Top 3 平均</span>
                <span className="text-sm text-themed-primary tabular-nums">
                  {formatMaybeNumber(baseline.industryTop3Avg)}
                </span>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-baseline justify-between mb-2">
              <h3 className="text-sm font-semibold text-themed-primary">
                {t('brand_citations.simulator_breakdown') || '各层 citation 数'}
              </h3>
            </div>
            <div className="space-y-2">
              {tiers.map((tier, i) => (
                <div key={tier} className="flex items-center justify-between">
                  <span className="text-xs text-themed-muted">Tier {tier}</span>
                  <span className="text-sm font-medium text-themed-primary tabular-nums">
                    {baseline.currentByTier[tier] ?? '--'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Preset buttons */}
      <Card className="p-4">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-themed-primary">
            <MetricLabel helpText={t('brand_citations.simulator_presets_hint')}>
              {t('brand_citations.simulator_presets') || '快速场景'}
            </MetricLabel>
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.id}
              onClick={() => applyPreset(preset)}
              className="px-3 py-1.5 rounded-pill text-xs font-medium transition-colors border border-themed-card hover:border-themed-accent hover:bg-themed-subtle text-themed-primary"
            >
              {preset.label}
            </button>
          ))}
          <button
            onClick={resetDeltas}
            className="px-3 py-1.5 rounded-pill text-xs font-medium transition-colors text-themed-muted hover:text-themed-primary hover:bg-themed-subtle border border-themed-card"
          >
            重置
          </button>
        </div>
      </Card>

      {/* Delta sliders */}
      <Card className="p-4">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-themed-primary">
            <MetricLabel helpText={t('brand_citations.simulator_adjust_hint')}>
              {t('brand_citations.simulator_adjust_deltas') || '调整各层增长'}
            </MetricLabel>
          </h3>
        </div>
        <div className="space-y-4">
          {tiers.map((tier, i) => (
            <div key={tier}>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-themed-primary">
                  Tier {tier} {tier === 1 ? '(官方)' : tier === 2 ? '(权威媒体)' : tier === 3 ? '(KOL)' : '(UGC)'}
                </label>
                <span className="text-sm font-semibold text-themed-accent tabular-nums">
                  {deltas[i] >= 0 ? '+' : ''}
                  {deltas[i]}
                </span>
              </div>
              <input
                type="range"
                min="-5"
                max="10"
                step="1"
                value={deltas[i]}
                onChange={(e) => handleDeltaChange(i, e.target.value)}
                className="w-full cursor-pointer accent-[var(--color-accent)]"
              />
              <div className="flex items-center justify-between mt-1 text-[10px] text-themed-muted">
                <span>-5</span>
                <span className="tabular-nums">{baseline.currentByTier[tier] ?? '--'}</span>
                <span>+10</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Result card */}
      <Card className="p-4 border-l-4" style={{ borderLeftColor: panoStatus.color }}>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div>
            <p className="text-[10px] text-themed-muted mb-1">
              <MetricLabel helpText={t('brand_citations.simulator_current_pano_help')}>
                当前 PANO
              </MetricLabel>
            </p>
            <p className="text-3xl font-bold tabular-nums text-themed-primary leading-none">
              {baseline.currentPanoA}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-themed-muted mb-1">
              <MetricLabel helpText={t('brand_citations.simulator_estimated_pano_help')}>
                预估 PANO
              </MetricLabel>
            </p>
            <p className="text-3xl font-bold tabular-nums text-themed-primary leading-none">
              {calculated.newPanoA.toFixed(1)}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-themed-muted mb-1">
              <MetricLabel helpText={t('brand_citations.simulator_delta_help')}>
                变化
              </MetricLabel>
            </p>
            <p
              className="text-3xl font-bold tabular-nums leading-none"
              style={{ color: panoStatus.color }}
            >
              {calculated.panoDelta >= 0 ? '+' : ''}
              {calculated.panoDelta}
            </p>
            <p className="text-[10px] mt-1" style={{ color: panoStatus.color }}>
              {panoStatus.label}
            </p>
          </div>
        </div>
        <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
          <a
            href="mailto:hello@genpano.com?subject=我想要定制化优化方案"
            className="inline-flex items-center justify-center px-4 py-2.5 rounded-btn bg-themed-accent text-white font-medium text-sm transition-colors hover:opacity-90"
          >
            获取定制优化方案
            <span className="ml-1.5">→</span>
          </a>
          <p className="text-[10px] text-themed-muted mt-2">
            {t('brand_citations.simulator_cta_hint') || '了解如何通过内容策略、外联 PR、平台合作等方式实现增长'}
          </p>
        </div>
      </Card>
    </div>
  );
}
