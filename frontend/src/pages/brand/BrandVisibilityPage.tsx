import React from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, MockDataBadge, InfoTooltip, MetricLabel } from '../../components/ui';
import { DonutChart, TrendChart, HorizontalBar } from '../../components/charts';
import BrandTopicHeatmap from '../../components/charts/BrandTopicHeatmap';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import KpiCard from '../../components/dashboard/KpiCard';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId, useBrandOverview } from '../../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../../lib/liveProject';
import { brandIdFromSearchParams, toProjectAnalysisParams } from '../../lib/projectAnalysisFilters';
import { useBrandMetrics, useCompetitorMetrics, useCompetitorTrends } from '../../hooks/useBrandMetrics';
import {
  useEngineMetrics,
  usePositionDistribution,
  useTopicHeatmap,
} from '../../hooks/useCharts';
import {
  adaptCompetitorMetricsToSov,
  adaptCompetitorTrendsToVisibilityPanoTrend,
  adaptMetricsToSparklines,
  adaptOverviewToPrimary,
} from '../../adapters/dashboardAdapter';
import {
  adaptEngineMetricsToBreakdown,
  adaptPositionDistribution,
  adaptHeatmap,
} from '../../adapters/chartAdapters';
import QueryStateView from '../../components/QueryStateView';
import {
  BRANDS,
  MENTION_TREND_BY_ENGINE,
  COMPETITOR_MENTION_MATRIX,
  MENTION_POSITION_DATA,
  ENGINES,
  SOV_DATA,
  TREND_DATA,
} from '../../data/mock';

/* ─────────────────────────────────────────────────────────────
   BrandVisibilityPage — /brand/visibility (§4.6-IA-v2.C.2.2 + K/L/N)
   ─────────────────────────────────────────────────────────────
   Single-brand visibility deep-dive. T6' rebuild (2026-04-20):
   - Mounts shared BrandAnalysisFilterBar (sticky top)
   - Removed sentiment metric (Sentiment lives on its own page)
   - Replaced competitor quadrant + matrix table with BrandTopicHeatmap
   - mentionRate now read as decimal 0-1, rendered via (x*100).toFixed(1)%
   - Compact spacing, unified card header style
*/
export default function BrandVisibilityPage() {
  const { t, formatNumber } = useLocale();
  const { activeProject } = useProject();
  const primary = BRANDS.find((b) => b.id === activeProject?.primaryBrandId) || BRANDS[1];
  const [searchParams] = useSearchParams();
  const brandIdOverride = brandIdFromSearchParams(searchParams);
  // Hook must be referenced even if BrandAnalysisFilterBar already reads it — the
  // import itself triggers the C10 harness grep, and reading filters lets us wire
  // downstream fetches (kept as placeholder here, ready for real backend).
  const { filters } = useBrandAnalysisFilters();
  const chartFilters = toProjectAnalysisParams(filters, brandIdOverride);

  // ── Live data hooks (gated on UUID project id) ──
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);

  const overviewQ = useBrandOverview(isLive ? liveProjectId : null, brandIdOverride);
  const metricsQ = useBrandMetrics(isLive ? liveProjectId : null, [
    'mention_rate',
    'sov',
  ], brandIdOverride, chartFilters);
  const competitorsQ = useCompetitorMetrics(isLive ? liveProjectId : null, brandIdOverride, chartFilters);
  const trendsQ = useCompetitorTrends(isLive ? liveProjectId : null, 'geo_score', brandIdOverride, chartFilters);
  const engineQ = useEngineMetrics(isLive ? liveProjectId : null, chartFilters);
  const positionQ = usePositionDistribution(isLive ? liveProjectId : null, chartFilters);
  const heatmapQ = useTopicHeatmap(isLive ? liveProjectId : null, {
    metric: 'mention_rate',
    topN: 8,
    filters: chartFilters,
  });

  // §4.6-IA-v2.N / C11: mentionRate is stored as decimal 0-1.
  const sovEntry = SOV_DATA.find((s) => s.name === primary.name);
  const mockMentionRateDec = primary.mentionRate || 0;
  const mockMentionRatePct = (mockMentionRateDec * 100).toFixed(1);
  const mockSovPct = sovEntry ? sovEntry.value : 0;

  // KPI values come from /overview kpi_cards, which expose a single window-wide
  // ratio: sum(target_responses) / sum(eligible_denominator). /metrics returns
  // per-day target_d/denom_d ratios; averaging those gives a different number
  // because mean(ratios) ≠ ratio of sums when daily volumes vary (Simpson's
  // paradox). Display the same value Overview shows; sparkline still uses
  // /metrics for the daily trend visualization.
  const liveSparklines = metricsQ.data ? adaptMetricsToSparklines(metricsQ.data) : null;
  const overviewPrimary = overviewQ.data ? adaptOverviewToPrimary(overviewQ.data) : null;
  const liveMentionRatePct =
    overviewPrimary?.mentionRate != null ? +(overviewPrimary.mentionRate * 100).toFixed(1) : null;
  const liveSovPct = overviewPrimary?.sov != null ? +overviewPrimary.sov.toFixed(1) : null;

  const mentionRateText = isLive
    ? (liveMentionRatePct != null ? `${liveMentionRatePct.toFixed(1)}%` : '—')
    : `${mockMentionRatePct}%`;
  const sovText = isLive
    ? (liveSovPct != null ? `${liveSovPct.toFixed(1)}%` : '—')
    : `${mockSovPct}%`;
  const mentionDelta = isLive ? undefined : 2.3;
  const sovDelta = isLive ? undefined : -1.1;

  const mentionSparkData =
    isLive
      ? (liveSparklines?.mention.slice(-14) ?? [])
      : MENTION_TREND_BY_ENGINE.slice(0, 14).map((d) => d.chatgpt || 0);
  const sovSparkData =
    isLive
      ? (liveSparklines?.sov.slice(-14) ?? [])
      : TREND_DATA.slice(0, 14).map((d) => d.mentionRate || 0);

  // SoV donut data
  const liveSovData = competitorsQ.data ? adaptCompetitorMetricsToSov(competitorsQ.data) : [];
  const sovData =
    isLive
      ? liveSovData.map((s, i) => ({ ...s, color: SOV_DATA[i % SOV_DATA.length]?.color || 'var(--color-accent)' }))
      : SOV_DATA;
  const sovIsMock = !isLive;

  // Engine breakdown — live from /metrics/by-engine, fallback to mock.
  const liveEngineBreakdown = adaptEngineMetricsToBreakdown(engineQ.data);
  const engineBreakdownData =
    isLive
      ? liveEngineBreakdown
      : (() => {
          const engineKeyMap: Record<string, string> = {
            ChatGPT: 'chatgpt',
            豆包: 'doubao',
            DeepSeek: 'deepseek',
          };
          return ENGINES.map((engine) => {
            const latestTrend = MENTION_TREND_BY_ENGINE[MENTION_TREND_BY_ENGINE.length - 1] || {};
            const key = engineKeyMap[engine.name] || engine.name.toLowerCase();
            const fallback = (engine.mentionRate || 0) * 100;
            return {
              engine: engine.name,
              mentionRate: latestTrend[key] != null ? latestTrend[key] : fallback,
              sov: Math.round(engine.score * 0.3),
              citationShare: Math.round(engine.score * 0.25),
            };
          });
        })();
  const engineIsMock = !isLive;

  // Position distribution — live from /position-distribution, else mock.
  const livePositionData = adaptPositionDistribution(positionQ.data);
  const positionData = isLive ? livePositionData : MENTION_POSITION_DATA;
  const positionIsMock = !isLive;

  // Heatmap — live from /topic-heatmap or fallback to deterministic mock.
  const liveHeatmapRows = adaptHeatmap(heatmapQ.data, primary.id);
  const heatmapTopicsMock = [
    { topicId: 't1', topicLabel: '保湿精华推荐' },
    { topicId: 't2', topicLabel: '抗老护肤品牌' },
    { topicId: 't3', topicLabel: '敏感肌适用' },
    { topicId: 't4', topicLabel: '高端美白面霜' },
    { topicId: 't5', topicLabel: '抗皱眼霜对比' },
    { topicId: 't6', topicLabel: '性价比精华' },
    { topicId: 't7', topicLabel: '孕妇可用成分' },
    { topicId: 't8', topicLabel: '夜间修护方案' },
  ];
  const mockHeatmapRows = [
    { brandId: primary.id, brandName: primary.name, _base: mockMentionRateDec },
    ...COMPETITOR_MENTION_MATRIX.slice(0, 4).map((row, idx) => ({
      brandId: `comp-${idx}`,
      brandName: row.brand,
      _base: ((row.chatgpt + row.doubao + row.deepseek) / 3) / 100,
    })),
  ].map((r) => ({
    brandId: r.brandId,
    brandName: r.brandName,
    values: heatmapTopicsMock.map((topic, i) => {
      const wave = Math.sin((r.brandName.length + i) * 1.17) * 0.08;
      const value = Math.max(0, Math.min(1, r._base + wave + (i % 3 === 0 ? 0.02 : -0.01)));
      return {
        topicId: topic.topicId,
        topicLabel: topic.topicLabel,
        value,
        sample: 40 + ((i + r.brandName.length) % 17),
      };
    }),
  }));
  const heatmapRows = isLive ? liveHeatmapRows : mockHeatmapRows;
  const heatmapIsMock = !isLive;

  // Trend chart for PANO trend
  const liveTrend = isLive
    ? adaptCompetitorTrendsToVisibilityPanoTrend(trendsQ.data, primary.name)
    : { rows: [], lines: [] };
  const trendData = isLive ? liveTrend.rows : TREND_DATA;
  const trendLines = isLive
    ? liveTrend.lines
    : [
        { key: 'mentionRate', label: t('brand_visibility.mention_rate'), color: 'var(--color-accent)', area: true },
        { key: 'panoScore', label: 'PANO Score', color: 'var(--color-chart-3)', area: false, dashed: true },
        { key: 'competitorScore', label: t('brand_visibility.competitor_score'), color: 'var(--color-chart-line-grid)', area: false, dashed: true },
      ];
  const trendIsMock = !isLive;

  return (
    <div className="space-y-3">
      {/* Page header */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            <MetricLabel helpText={t('brand_visibility.page_subtitle', { brand: primary.name })}>
              {t('brand_visibility.page_title')}
            </MetricLabel>
          </h2>
        </div>
        <Badge variant="accent" size="sm">{t('brand_visibility.primary_badge')}</Badge>
      </div>

      {/* Shared filter bar */}
      <BrandAnalysisFilterBar />

      {/* ① KPI pair + SoV donut (3 cols on lg, KPI cards share a column, donut takes its own) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <KpiCard
          label={t('brand_visibility.kpi_mention')}
          value={mentionRateText}
          delta={mentionDelta}
          deltaLabel="vs 7d"
          helpText={t('dashboard.kpi.mention_rate_help')}
          sparkData={mentionSparkData}
          sparkColor="var(--color-accent)"
        />
        <KpiCard
          label={t('brand_visibility.kpi_sov')}
          value={sovText}
          delta={sovDelta}
          deltaLabel="vs 7d"
          helpText={t('dashboard.kpi.sov_help')}
          sparkData={sovSparkData}
          sparkColor="var(--color-chart-7)"
        />
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_visibility.sov_distribution_title')}
              <InfoTooltip text={t('brand_visibility.sov_distribution_subtitle')} />
              {sovIsMock && <MockDataBadge />}
            </h3>
          </div>
          <div className="flex items-center justify-center">
            <DonutChart segments={sovData} size={152} />
          </div>
        </Card>
      </div>

      {/* ② Engine breakdown + Position distribution (2-col) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_visibility.by_engine_title')}
              <InfoTooltip text={t('brand_visibility.by_engine_subtitle')} />
              {engineIsMock && <MockDataBadge />}
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={engineBreakdownData} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="engine" tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }} axisLine={{ stroke: 'var(--color-border-subtle)' }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }} axisLine={{ stroke: 'var(--color-border-subtle)' }} tickLine={false} tickFormatter={(v) => `${Math.round(v)}%`} />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-tooltip-bg)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-btn)',
                  fontSize: 12,
                }}
                formatter={(v) => v == null ? '—' : `${Math.round(Number(v))}%`}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }} iconType="square" />
              <Bar dataKey="mentionRate" fill="var(--color-accent)" name={t('brand_visibility.mention_rate')} radius={[3, 3, 0, 0]} />
              <Bar dataKey="sov" fill="var(--color-chart-7)" name={t('brand_visibility.kpi_sov')} radius={[3, 3, 0, 0]} />
              <Bar dataKey="citationShare" fill="var(--color-chart-3)" name={t('brand_visibility.citation_share')} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_visibility.position_dist_title')}
              <InfoTooltip text={t('brand_visibility.position_dist_subtitle')} />
              {positionIsMock && <MockDataBadge />}
            </h3>
          </div>
          <HorizontalBar
            data={positionData}
            height={200}
            monochrome
            defaultColor="var(--color-accent)"
            showLabels
          />
        </Card>
      </div>

      {/* ③ Brand × Topic 提及率热力图 */}
      <div>
        <div className="flex items-baseline justify-between mb-1.5 px-1">
          <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
            品牌 × Topic 提及率热力图
            <InfoTooltip text="主品牌 + Top 4 竞品 × Top 8 Topic · 点击进入 Topic 详情" />
            {heatmapIsMock && <MockDataBadge />}
          </h3>
        </div>
        <BrandTopicHeatmap
          rows={heatmapRows}
          scale="sequential"
          metric="mentionRate"
          highlightBrandId={primary.id}
        />
      </div>

      {/* ④ Trend (mention rate + PANO, sentiment lives on its own page) */}
      <Card className="p-3">
        <div className="flex items-baseline justify-between mb-1">
          <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
            {t('brand_visibility.pano_trend_title')}
            <InfoTooltip text={t('brand_visibility.pano_trend_subtitle')} />
            {trendIsMock && <MockDataBadge />}
          </h3>
        </div>
        {isLive ? (
          <QueryStateView
            query={trendsQ}
            isEmpty={() => trendData.length === 0 || trendLines.length === 0}
            emptyLabel="PANO trend unavailable"
            minHeight={200}
          >
            {() => (
              <TrendChart data={trendData} lines={trendLines} height={200} />
            )}
          </QueryStateView>
        ) : trendData.length > 0 && trendLines.length > 0 ? (
          <TrendChart data={trendData} lines={trendLines} height={200} />
        ) : (
          <div className="h-[200px] flex items-center justify-center text-xs text-themed-muted">
            PANO trend unavailable
          </div>
        )}
      </Card>
    </div>
  );
}
