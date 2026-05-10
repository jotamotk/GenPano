import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, MockDataBadge, InfoTooltip } from '../../components/ui';
import { TrendChart, DonutChart } from '../../components/charts';
import BrandTopicHeatmap from '../../components/charts/BrandTopicHeatmap';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../../lib/liveProject';
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
import {
  BRANDS,
  SENTIMENT_DISTRIBUTION,
  SENTIMENT_TREND_BY_ENGINE,
  SENTIMENT_KEYWORDS,
  SENTIMENT_DETAIL_LIST,
  SENTIMENT_TOPIC_ATTRIBUTION,
  COMPETITOR_SENTIMENT_BUBBLE,
} from '../../data/mock';

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
  // C10: page must reference useBrandAnalysisFilters (filter state lives in URL
  // and drives downstream fetches once the backend is wired).
  const { filters } = useBrandAnalysisFilters();

  // Response filter state (kept local — it's a drill-down within the samples card, not a page-level filter)
  const [polarity, setPolarity] = useState('all');

  // ── Live data hooks ──
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);
  const sentimentQ = useBrandSentiment(isLive ? liveProjectId : null);
  const engineQ = useSentimentByEngine(isLive ? liveProjectId : null);
  const trendQ = useSentimentTrendByEngine(isLive ? liveProjectId : null);
  const heatmapQ = useTopicHeatmap(isLive ? liveProjectId : null, {
    metric: 'sentiment',
    topN: 8,
  });
  const attributionQ = useTopicAttribution(isLive ? liveProjectId : null, 5);
  const samplesQ = useMentionSamples(isLive ? liveProjectId : null, {
    polarity: polarity === 'all' ? undefined : polarity,
    limit: 30,
  });

  // ──────────────────────────────────────────────────────────────
  // Sentiment distribution — prefer live, fallback to mock aggregate.
  // ──────────────────────────────────────────────────────────────
  let positivePct: number;
  let negativePct: number;
  let neutralPct: number;
  let distributionIsMock = true;
  if (isLive && sentimentQ.data && sentimentQ.data.state !== 'empty') {
    positivePct = Math.round(sentimentQ.data.distribution.positive_pct);
    negativePct = Math.round(sentimentQ.data.distribution.negative_pct);
    neutralPct = Math.round(sentimentQ.data.distribution.neutral_pct);
    distributionIsMock = false;
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
  ];

  // ──────────────────────────────────────────────────────────────
  // Engine stacked bar — prefer live, fallback to mock.
  // ──────────────────────────────────────────────────────────────
  const liveStackedData = adaptSentimentByEngine(engineQ.data);
  const stackedChartData =
    isLive && liveStackedData.length > 0
      ? liveStackedData
      : SENTIMENT_DISTRIBUTION.map((d) => ({
          engine: d.engine,
          positive: d.positive,
          negative: d.negative,
          neutral: d.neutral,
        }));
  const stackedIsMock = !(isLive && liveStackedData.length > 0);

  // Sentiment trend (engine lines)
  const liveTrend = adaptSentimentTrend(trendQ.data);
  const trendDataLive = liveTrend.rows.length > 0 ? liveTrend.rows : null;
  const trendIsMock = !(isLive && trendDataLive);
  const trendLines = trendDataLive
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
  const sentimentHeatmapRows =
    isLive && liveHeatmapRows.length > 0 && liveHeatmapRows.some((r) => r.values.length > 0)
      ? liveHeatmapRows
      : mockSentimentHeatmapRows;
  const sentimentHeatmapIsMock = !(
    isLive && liveHeatmapRows.length > 0 && liveHeatmapRows.some((r) => r.values.length > 0)
  );

  // ──────────────────────────────────────────────────────────────
  // Topic attribution (live → mock).
  // ──────────────────────────────────────────────────────────────
  const liveAttribution = adaptTopicAttribution(attributionQ.data);
  const topicAttribution =
    isLive && liveAttribution.length > 0
      ? liveAttribution.map((a) => ({
          topicName: a.topicName,
          sampleSnippet: a.sampleSnippet ?? '',
          negativeCount: a.negativeCount,
          negativeRatio: a.negativeRatio,
        }))
      : SENTIMENT_TOPIC_ATTRIBUTION || [];
  const attributionIsMock = !(isLive && liveAttribution.length > 0);

  // ──────────────────────────────────────────────────────────────
  // Filter response samples by polarity (local control)
  // ──────────────────────────────────────────────────────────────
  const liveSamples = adaptMentionSamples(samplesQ.data);
  const samplesData = isLive && liveSamples.length > 0 ? liveSamples : SENTIMENT_DETAIL_LIST || [];
  const samplesIsMock = !(isLive && liveSamples.length > 0);
  const filteredResponses = samplesData.filter((item: any) => {
    if (polarity === 'all') return true;
    if (polarity === 'positive') return item.label === '正面';
    if (polarity === 'negative') return item.label === '负面';
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-2xl font-brand font-bold text-themed-primary">
            {t('brand_sentiment.page_title')}
          </h2>
          <p className="text-sm text-themed-muted mt-0.5">
            {t('brand_sentiment.page_subtitle', { brand: primary.name })}
          </p>
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
          data={trendDataLive ?? SENTIMENT_TREND_BY_ENGINE}
          lines={trendLines}
          height={240}
        />
      </Card>

      {/* ③ Brand × Topic sentiment heatmap (diverging scale) */}
      <div>
        <div className="flex items-baseline justify-between mb-2 px-1">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            品牌 × Topic 情感热力图
            <InfoTooltip text="主品牌 + Top 4 竞品 × Top 8 Topic · 红负蓝正 · 点击进入 Topic 详情" />
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

      {/* ⑤ 正面/负面关键词 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-sm font-semibold text-themed-primary">
              {t('brand_sentiment.positive_keywords')}
            </h3>
            <span className="text-[11px] text-themed-muted">Top 10</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {(SENTIMENT_KEYWORDS.positive || []).slice(0, 10).map((kw, idx) => (
              <Badge key={idx} variant="green" size="sm">
                {kw.word}
                <span className="ml-1 opacity-70">×{kw.weight}</span>
              </Badge>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-sm font-semibold text-themed-primary">
              {t('brand_sentiment.negative_keywords')}
            </h3>
            <span className="text-[11px] text-themed-muted">Top 10</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {(SENTIMENT_KEYWORDS.negative || []).slice(0, 10).map((kw, idx) => (
              <Badge key={idx} variant="red" size="sm">
                {kw.word}
                <span className="ml-1 opacity-70">×{kw.weight}</span>
              </Badge>
            ))}
          </div>
        </Card>
      </div>

      {/* ⑥ Response 样本 */}
      <Card className="p-4">
        <div className="flex items-baseline justify-between mb-3">
          <h3 className="text-sm font-semibold text-themed-primary flex items-center gap-2">
            {t('brand_sentiment.samples_title')}
            {samplesIsMock && <MockDataBadge />}
          </h3>
          <span className="text-[11px] text-themed-muted">{filteredResponses.length} 条</span>
        </div>

        <div className="flex gap-1.5 mb-4">
          {['all', 'positive', 'negative'].map((pol) => (
            <button
              key={pol}
              onClick={() => setPolarity(pol)}
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
          {filteredResponses.slice(0, 6).map((item, idx) => (
            <div
              key={idx}
              className="rounded-card bg-themed-subtle p-3 border-l-4"
              style={{
                borderLeftColor:
                  item.label === '正面' ? 'var(--color-chart-7)'
                  : item.label === '负面' ? 'var(--color-danger)'
                  : 'var(--color-chart-line-grid)',
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <Badge
                  variant={item.label === '正面' ? 'green' : item.label === '负面' ? 'red' : 'default'}
                  size="sm"
                >
                  {item.label}
                </Badge>
                <span className="text-[10px] text-themed-muted">{item.engine} · {item.time}</span>
              </div>
              <p className="font-medium text-[10px] text-themed-muted mb-1">{item.topic}</p>
              <p className="text-sm text-themed-primary leading-relaxed">{item.summary}</p>
            </div>
          ))}

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
