import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, MockDataBadge, InfoTooltip, MetricLabel } from '../../components/ui';
import { TrendChart, DonutChart } from '../../components/charts';
import BrandTopicHeatmap from '../../components/charts/BrandTopicHeatmap';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../../lib/liveProject';
import { brandIdFromSearchParams, toProjectAnalysisParams } from '../../lib/projectAnalysisFilters';
import { canUseMetricEvidence } from '../../api/analyticsContract';
import { useBrandSentiment } from '../../hooks/useBrandMetrics';
import {
  useSentimentByEngine,
  useSentimentTrendByEngine,
  useTopicHeatmap,
  useTopicAttribution,
  useMentionSamples,
} from '../../hooks/useCharts';
import {
  adaptSentimentByEngine,
  adaptSentimentTrend,
  adaptHeatmap,
  adaptTopicAttribution,
  adaptMentionSamples,
} from '../../adapters/chartAdapters';
import QueryStateView from '../../components/QueryStateView';
import SentimentKeywordsTable from '../../components/brand/SentimentKeywordsTable';
import SentimentSamplesTable from '../../components/brand/SentimentSamplesTable';
import {
  BRANDS,
  SENTIMENT_DISTRIBUTION,
  SENTIMENT_TREND_BY_ENGINE,
  SENTIMENT_KEYWORDS,
  SENTIMENT_DETAIL_LIST,
  SENTIMENT_TOPIC_ATTRIBUTION,
  COMPETITOR_SENTIMENT_BUBBLE,
} from '../../data/mock';

const RESPONSE_SAMPLE_LIMIT = 100;

type SentimentResponseRow = {
  label: string;
  topic: string;
  engine: string;
  time: string;
  summary: string;
  polarity?: string | null;
  queryId?: number | null;
  mentionId?: number | null;
  responseId?: number | null;
  snippet?: string | null;
  responseText?: string | null;
};

/* ─────────────────────────────────────────────────────────────
   BrandSentimentPage — /brand/sentiment (§4.6-IA-v2.C.2.2 + K/L/N)
   ─────────────────────────────────────────────────────────────
   T6' rebuild (2026-04-20):
   - Mounts shared BrandAnalysisFilterBar (sticky top)
   - §4.6-IA-v2.N / C12: Sentiment Distribution MUST be a Donut (the
     previous "three giant text % numbers" looked like a broken chart)
   - §4.6-IA-v2.L: Brand × Topic sentiment heatmap (diverging scale)
     replaces the flat竞品情感对比 table as the primary comparison.
   - Compact spacing, unified card header style.
*/
export default function BrandSentimentPage() {
  const { t } = useLocale();
  const { activeProject } = useProject();
  const primary = BRANDS.find((b) => b.id === activeProject?.primaryBrandId) || BRANDS[1];
  const [searchParams] = useSearchParams();
  const brandIdOverride = brandIdFromSearchParams(searchParams);
  // C10: page must reference useBrandAnalysisFilters (filter state lives in URL
  // and drives downstream fetches once the backend is wired).
  const { filters } = useBrandAnalysisFilters();
  const chartFilters = toProjectAnalysisParams(filters, brandIdOverride);

  // Response filter state (kept local — it's a drill-down within the samples card, not a page-level filter)
  const [polarity, setPolarity] = useState('all');
  const [expandedResponseKey, setExpandedResponseKey] = useState<string | null>(null);
  const [responseOffset, setResponseOffset] = useState(0);
  const [accumulatedLiveSamples, setAccumulatedLiveSamples] = useState<SentimentResponseRow[]>([]);

  // ── Live data hooks ──
  // activeProject is URL-aware via ProjectContext (Epic #1175): when the
  // route carries `?brandId=<int>`, the context already overrides
  // activeProject to the project that owns that brand. We can therefore
  // call resolveLiveProjectId(activeProject) directly without re-doing
  // the brand→project lookup at the page level. This keeps liveProjectId
  // and activeProject.id moving together — eliminating the dual-identity
  // mismatch that caused the accumulator to reset spuriously.
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);
  const sentimentQ = useBrandSentiment(isLive ? liveProjectId : null, chartFilters);
  const engineQ = useSentimentByEngine(isLive ? liveProjectId : null, chartFilters);
  const trendQ = useSentimentTrendByEngine(isLive ? liveProjectId : null, chartFilters);
  const heatmapQ = useTopicHeatmap(isLive ? liveProjectId : null, {
    metric: 'sentiment',
    topN: 20,
    filters: chartFilters,
  });
  const attributionQ = useTopicAttribution(isLive ? liveProjectId : null, 5, chartFilters);
  // Issue #1248: polarity is intentionally NOT passed to the backend any more.
  // The backend `get_mention_samples` polarity filter joins through the
  // `brand_mentions` table (backend/app/api/v1/projects/_charts_service.py:1885-1887)
  // which is empty for some brands (e.g. BestCoffer brand 24, see readonly
  // evidence run https://github.com/jotamotk/trash_test/actions/runs/26034927203
  // → brand_mention_count: 0 vs admin_fact_response_count: 191). For those
  // brands, polarity=positive made the backend return 0 items even though the
  // all-view returned 100/298. The defensive fix is to always load the
  // all-view set from the backend and narrow client-side. The backend
  // JOIN-shape mismatch is tracked as a separate followup.
  const samplesQ = useMentionSamples(isLive ? liveProjectId : null, {
    limit: RESPONSE_SAMPLE_LIMIT,
    offset: responseOffset,
    filters: chartFilters,
  });

  // ──────────────────────────────────────────────────────────────
  // Sentiment distribution — prefer live, fallback to mock aggregate.
  // ──────────────────────────────────────────────────────────────
  let positivePct: number | null;
  let negativePct: number | null;
  let neutralPct: number | null;
  let distributionIsMock = !isLive;
  if (isLive) {
    const distribution = canUseMetricEvidence(sentimentQ.data, 'sentiment')
      ? sentimentQ.data?.distribution
      : null;
    positivePct = distribution ? Math.round(distribution.positive_pct) : null;
    negativePct = distribution ? Math.round(distribution.negative_pct) : null;
    neutralPct = distribution ? Math.round(distribution.neutral_pct) : null;
  } else {
    const positive = SENTIMENT_DISTRIBUTION.reduce((sum, d) => sum + d.positive, 0);
    const negative = SENTIMENT_DISTRIBUTION.reduce((sum, d) => sum + d.negative, 0);
    const neutral = SENTIMENT_DISTRIBUTION.reduce((sum, d) => sum + d.neutral, 0);
    const total = positive + negative + neutral || 1;
    positivePct = Math.round((positive / total) * 100);
    negativePct = Math.round((negative / total) * 100);
    neutralPct = Math.round((neutral / total) * 100);
  }

  // §4.6-IA-v2.N / C12: Sentiment Distribution renders as a Donut.
  const distributionSegments = [
    { name: '正面', value: positivePct, color: 'var(--color-chart-7)' },
    { name: '中性', value: neutralPct, color: 'var(--color-chart-line-grid)' },
    { name: '负面', value: negativePct, color: 'var(--color-danger)' },
  ].filter((segment) => segment.value != null);

  // ──────────────────────────────────────────────────────────────
  // Engine stacked bar — prefer live, fallback to mock.
  // ──────────────────────────────────────────────────────────────
  const liveStackedData = adaptSentimentByEngine(engineQ.data);
  const stackedChartData =
    isLive
      ? liveStackedData
      : SENTIMENT_DISTRIBUTION.map((d) => ({
          engine: d.engine,
          positive: d.positive,
          negative: d.negative,
          neutral: d.neutral,
        }));
  const stackedIsMock = !isLive;

  // Sentiment trend (engine lines)
  const liveTrend = adaptSentimentTrend(trendQ.data);
  const trendDataLive = liveTrend.rows.length > 0 ? liveTrend.rows : null;
  const trendIsMock = !isLive;
  const trendLines = isLive
    ? liveTrend.engines.map((eng, idx) => ({
        key: eng,
        label: eng,
        color: idx === 0 ? 'var(--color-engine-chatgpt)' : `var(--color-chart-${(idx % 5) + 2})`,
        area: idx === 0,
      }))
    : [
        { key: 'chatgpt', label: 'ChatGPT', color: 'var(--color-engine-chatgpt)', area: true },
        { key: 'doubao', label: '豆包', color: 'var(--color-engine-doubao)', area: false },
        { key: 'deepseek', label: 'DeepSeek', color: 'var(--color-engine-deepseek)', area: false, dashed: true },
      ];

  // ──────────────────────────────────────────────────────────────
  // Brand × Topic sentiment heatmap (diverging -1 … +1).
  // Real data lands from API; here we fabricate from primary.sentiment +
  // COMPETITOR_SENTIMENT_BUBBLE using a deterministic wave so the cells are
  // non-uniform while still being reproducible for visual baselines.
  // ──────────────────────────────────────────────────────────────
  const heatmapTopics = [
    { topicId: 's1', topicLabel: '保湿精华推荐' },
    { topicId: 's2', topicLabel: '抗老护肤品牌' },
    { topicId: 's3', topicLabel: '敏感肌适用' },
    { topicId: 's4', topicLabel: '高端美白面霜' },
    { topicId: 's5', topicLabel: '抗皱眼霜对比' },
    { topicId: 's6', topicLabel: '性价比精华' },
    { topicId: 's7', topicLabel: '孕妇可用成分' },
    { topicId: 's8', topicLabel: '夜间修护方案' },
  ];

  const sentimentRowSeeds = [
    { brandId: primary.id, brandName: primary.name, _base: (primary.sentiment ?? 0.5) * 2 - 1 },
    ...(COMPETITOR_SENTIMENT_BUBBLE || []).slice(0, 4).map((comp, idx) => ({
      brandId: `sent-comp-${idx}`,
      brandName: comp.brand,
      _base: (comp.sentiment ?? 0.5) * 2 - 1,
    })),
  ];

  const mockSentimentHeatmapRows = sentimentRowSeeds.map((r) => ({
    brandId: r.brandId,
    brandName: r.brandName,
    values: heatmapTopics.map((topic, i) => {
      const wave = Math.sin((r.brandName.length + i) * 0.91) * 0.3;
      const drift = i % 3 === 0 ? 0.08 : i % 3 === 1 ? -0.05 : 0.02;
      const v = Math.max(-1, Math.min(1, r._base + wave + drift));
      return {
        topicId: topic.topicId,
        topicLabel: topic.topicLabel,
        value: v,
        sample: 32 + ((i + r.brandName.length) % 21),
      };
    }),
  }));
  const liveHeatmapRows = adaptHeatmap(heatmapQ.data, primary.id);
  const sentimentHeatmapRows = isLive ? liveHeatmapRows : mockSentimentHeatmapRows;
  const sentimentHeatmapIsMock = !isLive;

  // ──────────────────────────────────────────────────────────────
  // Topic attribution (live → mock).
  // ──────────────────────────────────────────────────────────────
  const liveAttribution = adaptTopicAttribution(attributionQ.data);
  const topicAttribution =
    isLive
      ? liveAttribution.map((a) => ({
          topicName: a.topicName,
          sampleSnippet: a.sampleSnippet ?? '',
          negativeCount: a.negativeCount,
          negativeRatio: a.negativeRatio,
        }))
      : SENTIMENT_TOPIC_ATTRIBUTION || [];
  const attributionIsMock = !isLive;

  // ──────────────────────────────────────────────────────────────
  // Filter response samples by polarity (local control)
  // ──────────────────────────────────────────────────────────────
  const livePageSignature = useMemo(
    () =>
      `${responseOffset}|${(samplesQ.data?.items ?? [])
        .map((item, idx) => `${item.query_id ?? 'query'}-${item.mention_id ?? item.response_id ?? idx}`)
        .join('|')}`,
    [responseOffset, samplesQ.data],
  );
  // Issue #1248: polarity is excluded from responseScopeKey because polarity
  // is now a pure client-side display filter (see the useMentionSamples call
  // above). Including polarity here would wipe the accumulator on every
  // polarity click and the client-side filter would have nothing to narrow.
  const responseScopeKey = useMemo(
    () => JSON.stringify({ projectId: liveProjectId, filters: chartFilters }),
    [liveProjectId, chartFilters],
  );

  useEffect(() => {
    setResponseOffset(0);
    setExpandedResponseKey(null);
    setAccumulatedLiveSamples([]);
  }, [responseScopeKey]);

  useEffect(() => {
    if (!isLive || !samplesQ.data) return;
    const liveSamples = adaptMentionSamples(samplesQ.data);
    setAccumulatedLiveSamples((prev) => {
      const next = responseOffset === 0 ? [] : [...prev];
      const seen = new Set(
        next.map((item, idx) => `${item.queryId ?? 'query'}-${item.mentionId ?? item.responseId ?? idx}`),
      );
      for (const item of liveSamples) {
        const key = `${item.queryId ?? 'query'}-${item.mentionId ?? item.responseId ?? next.length}`;
        if (!seen.has(key)) {
          next.push(item);
          seen.add(key);
        }
      }
      return next;
    });
  }, [isLive, livePageSignature]);

  const samplesData: SentimentResponseRow[] = isLive ? accumulatedLiveSamples : (SENTIMENT_DETAIL_LIST || []);
  const samplesIsMock = !isLive;
  const positiveKeywords = isLive
    ? (canUseMetricEvidence(sentimentQ.data, 'sentiment') ? sentimentQ.data?.top_keywords || [] : [])
        .filter((kw) => kw.polarity === 'positive')
        .map((kw) => ({ word: kw.keyword, weight: kw.count }))
    : SENTIMENT_KEYWORDS.positive || [];
  const negativeKeywords = isLive
    ? (canUseMetricEvidence(sentimentQ.data, 'sentiment') ? sentimentQ.data?.top_keywords || [] : [])
        .filter((kw) => kw.polarity === 'negative')
        .map((kw) => ({ word: kw.keyword, weight: kw.count }))
    : SENTIMENT_KEYWORDS.negative || [];
  // Issue #1248: always apply the client-side polarity filter, including under
  // live mode. The backend `get_mention_samples` polarity filter joins through
  // `brand_mentions` (see backend/app/api/v1/projects/_charts_service.py:1885-1887),
  // which is empty for some brands (e.g. BestCoffer brand 24 has
  // brand_mention_count: 0 per readonly evidence run
  // https://github.com/jotamotk/trash_test/actions/runs/26034927203), while the
  // "all" view derives from a different source. Trusting the backend to filter
  // produced 0 visible rows after clicking 正面/负面 even though the loaded
  // window contained multiple positive/negative labels. The defensive
  // client-side filter on already-loaded items keeps the UI consistent
  // regardless of backend join-shape mismatches.
  const filteredResponses = samplesData.filter((item: SentimentResponseRow) => {
    if (polarity === 'all') return true;
    const normalizedPolarity = String(item.polarity || item.label || '').toLowerCase();
    if (polarity === 'positive') return normalizedPolarity === 'positive' || item.label === '正面';
    if (polarity === 'negative') return normalizedPolarity === 'negative' || item.label === '负面';
    return true;
  });
  const fetchedResponseCount = samplesData.length;
  const visibleResponseCount = filteredResponses.length;
  const responseTotal = isLive ? (samplesQ.data?.total ?? fetchedResponseCount) : fetchedResponseCount;
  const responseHasMore = isLive ? Boolean(samplesQ.data?.has_more) && fetchedResponseCount < responseTotal : false;
  const evidenceCount = isLive ? (samplesQ.data?.evidence_count ?? responseTotal) : fetchedResponseCount;
  // Issue #1248: when the client-side polarity filter narrows the loaded
  // window, surface the filter delta explicitly so users do not read
  // "Showing 100 of 298 responses" while only 42 polarity-matching rows
  // render below.
  const polarityFilterActive = polarity !== 'all';
  const polarityFilterSuffix = polarityFilterActive
    ? ` (${visibleResponseCount} match the ${polarity} filter)`
    : '';
  const responseWindowLabel = isLive
    ? responseHasMore
      ? `Showing ${fetchedResponseCount} of ${responseTotal} responses${polarityFilterSuffix}`
      : `Showing all ${fetchedResponseCount} responses${polarityFilterSuffix}`
    : `Showing ${visibleResponseCount} demo responses`;
  const responseApiNeed =
    'Needs backend fields from #1191: query_id, response_text, total, limit, offset, has_more, evidence_count, selected_filters.';
  const handleLoadMoreResponses = () => {
    if (!isLive || !responseHasMore || samplesQ.isFetching) return;
    setResponseOffset(fetchedResponseCount);
  };

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-2xl font-brand font-bold text-themed-primary">
            <MetricLabel helpText={t('brand_sentiment.page_subtitle', { brand: primary.name })}>
              {t('brand_sentiment.page_title')}
            </MetricLabel>
          </h2>
        </div>
      </div>

      {/* Shared filter bar */}
      <BrandAnalysisFilterBar />

      {/* ① Distribution (Donut) + Engine breakdown (Stacked Bar) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_sentiment.distribution_title')}
              <InfoTooltip text={t('brand_sentiment.distribution_subtitle', { default: '全引擎汇总' })} />
              {distributionIsMock && <MockDataBadge />}
            </h3>
          </div>
          {(() => {
            const renderDonut = () => (
              <div className="flex items-center justify-center gap-6 mt-2">
                <DonutChart segments={distributionSegments} size={180} />
                <div className="flex flex-col gap-2.5">
                  {distributionSegments.map((s) => (
                    <div key={s.name} className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />
                      <span className="text-xs text-themed-muted w-8">{s.name}</span>
                      <span className="text-sm font-semibold text-themed-primary tabular-nums">{s.value}%</span>
                    </div>
                  ))}
                </div>
              </div>
            );
            return isLive ? (
              <QueryStateView
                query={sentimentQ}
                isEmpty={() => distributionSegments.length === 0 || positivePct == null}
                emptyLabel={t('brand_sentiment.no_samples', { default: '暂无数据' })}
                minHeight={200}
              >
                {renderDonut}
              </QueryStateView>
            ) : (
              renderDonut()
            );
          })()}
        </Card>

        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-2">
            <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_sentiment.by_engine_title')}
              <InfoTooltip text={t('brand_sentiment.by_engine_subtitle', { default: '按引擎统计' })} />
              {stackedIsMock && <MockDataBadge />}
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stackedChartData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="engine" tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }} axisLine={{ stroke: 'var(--color-border-subtle)' }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }} axisLine={{ stroke: 'var(--color-border-subtle)' }} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-btn)',
                  fontSize: 12,
                  boxShadow: 'var(--shadow-card-hover)',
                }}
              />
              <Bar dataKey="positive" stackId="a" fill="var(--color-chart-7)" />
              <Bar dataKey="neutral" stackId="a" fill="var(--color-chart-line-grid)" />
              <Bar dataKey="negative" stackId="a" fill="var(--color-danger)" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ② Sentiment trend (engine lines) */}
      <Card className="p-4">
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            {t('brand_sentiment.trend_title')}
            <InfoTooltip text={t('brand_sentiment.trend_subtitle')} />
            {trendIsMock && <MockDataBadge />}
          </h3>
        </div>
        <TrendChart
          data={isLive ? (trendDataLive ?? []) : SENTIMENT_TREND_BY_ENGINE}
          lines={trendLines}
          height={240}
        />
      </Card>

      {/* ③ Brand × Topic sentiment heatmap (diverging scale) */}
      <div>
        <div className="flex items-baseline justify-between mb-2 px-1">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            品牌 × Topic 情感热力图
            <InfoTooltip text="主品牌 + Top 7 竞品 × Top 8 Topic · 红负蓝正 · 点击进入 Topic 详情" />
            {sentimentHeatmapIsMock && <MockDataBadge />}
          </h3>
        </div>
        <BrandTopicHeatmap
          rows={sentimentHeatmapRows}
          scale="diverging"
          metric="sentiment"
          highlightBrandId={primary.id}
        />
      </div>

      {/* ④ Topic 归因：哪些 Topic 拉低了情感？ */}
      <Card className="p-4">
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            {t('brand_sentiment.topic_attribution_title', { default: '哪些 Topic 拉低了情感?' })}
            <InfoTooltip text={t('brand_sentiment.topic_attribution_subtitle', { default: '负面情感集中的主题识别' })} />
            {attributionIsMock && <MockDataBadge />}
          </h3>
        </div>
        <div className="flex flex-col gap-2.5">
          {(topicAttribution || []).slice(0, 5).map((topic: any, idx: number) => (
            <div
              key={idx}
              className="rounded-card bg-themed-subtle p-3 hover:bg-themed-subtle/80 transition-colors cursor-pointer border-l-4"
              style={{ borderLeftColor: 'var(--color-danger)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-themed-primary text-sm">{topic.topicName}</p>
                  <p className="text-xs text-themed-muted mt-1 leading-relaxed line-clamp-2">{topic.sampleSnippet}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <Badge variant="red" size="sm">{topic.negativeCount}条</Badge>
                  <p className="text-[10px] text-themed-muted mt-1 tabular-nums">
                    {Math.round(topic.negativeRatio * 100)}%
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ⑤ 正面/负面关键词 — Issue #1285: tabular layout replaces the previous
          badge-grid where text-[11px] labels were illegible. Two tables sit
          side-by-side via the existing lg:grid-cols-2 wrapper; the new
          SentimentKeywordsTable component uses .t-table styling matching
          IndustryLeaderboardTable.tsx (text-[13px] body / text-[11px]
          muted headers). */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <SentimentKeywordsTable
            title={t('brand_sentiment.positive_keywords')}
            keywords={positiveKeywords}
            polarity="positive"
            limit={10}
          />
        </Card>

        <Card className="p-4">
          <SentimentKeywordsTable
            title={t('brand_sentiment.negative_keywords')}
            keywords={negativeKeywords}
            polarity="negative"
            limit={10}
          />
        </Card>
      </div>

      {/* ⑥ Response 样本 */}
      <Card className="p-4">
        <div className="flex items-baseline justify-between mb-3">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            {t('brand_sentiment.samples_title')}
            {samplesIsMock && <MockDataBadge />}
          </h3>
          <span className="text-[11px] text-themed-muted">{responseWindowLabel}</span>
        </div>

        <div className="flex gap-1.5 mb-4">
          {['all', 'positive', 'negative'].map((pol) => (
            <button
              key={pol}
              aria-label={pol === 'all' ? 'All' : pol === 'positive' ? 'Positive' : 'Negative'}
              onClick={() => {
                // Issue #1248: polarity is now a pure client-side display
                // filter applied to already-loaded samples. We no longer
                // reset the response offset or wipe the accumulator,
                // because the backend always returns the all-view set
                // (see useMentionSamples call above).
                setPolarity(pol);
                setExpandedResponseKey(null);
              }}
              className="px-3 py-1.5 rounded-pill text-xs font-medium transition-colors"
              style={
                polarity === pol
                  ? { background: 'var(--color-accent-bg-light)', color: 'var(--color-text-accent)' }
                  : { background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-muted)' }
              }
            >
              {pol === 'all' && '全部'}
              {pol === 'positive' && '正面'}
              {pol === 'negative' && '负面'}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          {isLive && (
            <div className="rounded-card border border-dashed border-themed-subtle bg-themed-subtle/60 p-3">
              <p className="text-xs text-themed-muted leading-relaxed">
                {responseHasMore
                  ? `Loaded ${fetchedResponseCount} of ${responseTotal} matching responses${polarityFilterActive ? ` (${visibleResponseCount} match the ${polarity} filter)` : ''}. ${evidenceCount} evidence rows match the current scope.`
                  : `All ${fetchedResponseCount} loaded responses are visible for the current scope${polarityFilterActive ? ` (${visibleResponseCount} match the ${polarity} filter)` : ''}. ${evidenceCount} evidence rows match the API filters.`}
              </p>
              {responseHasMore && <p className="text-[11px] text-themed-muted mt-1">{responseApiNeed}</p>}
            </div>
          )}

          {filteredResponses.length > 0 && (
            <SentimentSamplesTable
              rows={filteredResponses}
              expandedKey={expandedResponseKey}
              onExpandedKeyChange={setExpandedResponseKey}
              responseApiNeed={responseApiNeed}
            />
          )}

          {responseHasMore && (
            <div className="flex justify-center pt-1">
              <button
                type="button"
                onClick={handleLoadMoreResponses}
                disabled={samplesQ.isFetching}
                className="px-3 py-1.5 rounded-pill text-xs font-medium transition-colors"
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {samplesQ.isFetching ? 'Loading responses...' : 'Load more responses'}
              </button>
            </div>
          )}

          {filteredResponses.length === 0 && (
            <div className="text-center py-8">
              <p className="text-themed-muted text-sm">
                {t('brand_sentiment.no_samples', { default: '暂无数据' })}
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
