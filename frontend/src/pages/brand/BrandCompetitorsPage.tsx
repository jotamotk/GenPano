import React, { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend, ResponsiveContainer,
} from 'recharts';
import { useLocale } from '../../contexts/LocaleContext';
import { useProject } from '../../contexts/ProjectContext';
import { Card, Badge, MockDataBadge, InfoTooltip, MetricLabel } from '../../components/ui';
import { TrendChart } from '../../components/charts';
import BrandTopicHeatmap from '../../components/charts/BrandTopicHeatmap';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useBrandOverview';
import { resolveLiveProjectId } from '../../lib/liveProject';
import { brandIdFromSearchParams, toProjectAnalysisParams } from '../../lib/projectAnalysisFilters';
import { useCompetitorMetrics, useCompetitorTrends } from '../../hooks/useBrandMetrics';
import {
  useAuthorityRadar,
  useGroupSharedDomains,
  useTopicHeatmap,
} from '../../hooks/useCharts';
import {
  adaptAuthorityRadar,
  adaptHeatmap,
  adaptGroupSharedDomains,
} from '../../adapters/chartAdapters';
import {
  adaptCompetitorMetricsToList,
  adaptCompetitorTrendsToTrendData,
} from '../../adapters/dashboardAdapter';
import {
  BRANDS,
  AUTHORITY_RADAR_DATA,
  SAME_GROUP_SHARED,
  COMPETITOR_SENTIMENT_BUBBLE,
  TIER2_COVERAGE_MATRIX,
} from '../../data/mock';

function finiteNumberOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function positiveGap(left, right) {
  const a = finiteNumberOrNull(left);
  const b = finiteNumberOrNull(right);
  if (a == null || b == null) return null;
  return Math.max(0, a - b);
}

function labelizeContractValue(value) {
  if (value == null) return '';
  const raw = typeof value === 'string'
    ? value
    : value.field || value.source || value.reason || '';
  return String(raw)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/* ─────────────────────────────────────────────────────────────
   BrandCompetitorsPage — /brand/competitors (§4.6-IA-v2.C.2.2 + M)
   ─────────────────────────────────────────────────────────────
   T6' rebuild (2026-04-20): "我在哪些维度输给谁"
   The old page listed 7 competitor-related charts with no narrative.
   New structure answers one question, top-down:

     ① Top 3 威胁卡 — 基于 PanoGap × SoV × Sentiment 综合威胁分
     ② 选中竞品的深度拆解:
        - Authority Radar 5 维对比 (我 vs 所选竞品 vs 行业中位)
        - Brand × Topic 提及率热力图 (我 vs 所选竞品)
        - 30d PANO 趋势对比
     ③ 结构上下文 (非主干): Same-Group 共享域

   Compact spacing, shared filter bar.
*/
export default function BrandCompetitorsPage() {
  const { t } = useLocale();
  const { activeProject } = useProject();
  const mockPrimary = BRANDS.find((b) => b.id === activeProject?.primaryBrandId) || BRANDS[1];
  const [searchParams] = useSearchParams();
  const brandIdOverride = brandIdFromSearchParams(searchParams);
  const { filters } = useBrandAnalysisFilters(); // C10
  const chartFilters = toProjectAnalysisParams(filters, brandIdOverride);

  // ── Live data hooks ──
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const isLive = isLiveProjectId(liveProjectId);
  const competitorsQ = useCompetitorMetrics(isLive ? liveProjectId : null, brandIdOverride, chartFilters);
  const trendsQ = useCompetitorTrends(isLive ? liveProjectId : null, 'geo_score', brandIdOverride, chartFilters);
  const radarQ = useAuthorityRadar(isLive ? liveProjectId : null);
  const groupQ = useGroupSharedDomains(isLive ? liveProjectId : null);
  const heatmapQ = useTopicHeatmap(isLive ? liveProjectId : null, {
    metric: 'mention_rate',
    topN: 8,
    filters: chartFilters,
  });

  const liveCompetitorPayload = competitorsQ.data
    ? adaptCompetitorMetricsToList(competitorsQ.data)
    : null;
  const liveCompetitors = liveCompetitorPayload?.competitors ?? [];
  const analyticsPrimary = isLive && liveCompetitorPayload?.primary
    ? liveCompetitorPayload.primary
    : mockPrimary;
  // Issue #1185 follow-up — bestCoffer (live brand_id=24) is not in the
  // mock `BRANDS` array, so the original `find(...) || BRANDS[1]` lookup
  // silently fell back to the second cosmetics mock entry (雅诗兰黛).
  // That mock leaked into chart titles ("Authority Radar · 雅诗兰黛 vs
  // IBM Security") even though the actual chart data was correctly
  // hydrated from live API. Rebind `primary` to the live-aware
  // analyticsPrimary so titles + legends + chart series keys all agree
  // with the rendered data.
  const primary = analyticsPrimary;
  const competitors = useMemo(
    () =>
      isLive
        ? liveCompetitors
        : (activeProject?.competitorBrandIds || [])
            .map((id) => BRANDS.find((b) => b.id === id))
            .filter(Boolean)
            .slice(0, 6),
    [activeProject, isLive, liveCompetitors],
  );
  const liveCompetitorEvidenceState = useMemo(() => {
    const payload = competitorsQ.data;
    if (!isLive || !payload || !payload.state || payload.state === 'ok') return null;
    const scopedCompetitors = payload.project_scope?.competitor_brand_ids;
    const configuredCompetitorCount = Array.isArray(scopedCompetitors)
      ? scopedCompetitors.length
      : finiteNumberOrNull(payload.evidence_counts?.competitor_brand_count);
    // Issue #1185 follow-up — when the partial state only signals
    // "data is partial" but `competitors[]` already carries scoped rows
    // (e.g. bestCoffer's recent window: state=partial,
    // state_reason=partial_competitor_data, 11 same-industry rows from
    // #1236's brands backfill), fall through to the normal render and
    // surface the partiality as a small badge instead of suppressing
    // the whole panel. Metric-trust failures (missing_formula_inputs,
    // missing_required_inputs, missing_analyzer_rows) keep the full
    // suppression because the numbers themselves can't be displayed.
    const stateReason = String(payload.state_reason || '').toLowerCase();
    const partialReasonsThatStillRenderData = new Set([
      'partial_competitor_data',
      'partial_data',
      'partial_analyzer_data',
    ]);
    const hasCompetitorRows = Array.isArray(payload.competitors) && payload.competitors.length > 0;
    const renderableDespitePartial = hasCompetitorRows && partialReasonsThatStillRenderData.has(stateReason);
    return {
      state: payload.state,
      reason: labelizeContractValue(payload.state_reason || payload.formula_status),
      missingInputs: (payload.missing_inputs || []).map(labelizeContractValue).filter(Boolean),
      configuredCompetitorCount,
      renderable: renderableDespitePartial,
    };
  }, [competitorsQ.data, isLive]);

  // ──────────────────────────────────────────────────────────────
  // ① Threat scoring. We rank competitors by a composite threat score:
  //   panoGap     = max(0, competitor.panoScore − primary.panoScore)
  //   sovStrength = competitor SoV (from COMPETITOR_SENTIMENT_BUBBLE if available, else mentionRate proxy)
  //   sentGap     = max(0, competitor.sentiment − primary.sentiment)
  //   threatScore = 0.45 × panoGap + 0.35 × sovStrength + 0.20 × sentGap*100
  // Higher = more threatening.
  // ──────────────────────────────────────────────────────────────
  const threatCards = useMemo(() => {
    if (liveCompetitorEvidenceState && !liveCompetitorEvidenceState.renderable) return [];
    const bubbleByName = isLive
      ? new Map()
      : new Map((COMPETITOR_SENTIMENT_BUBBLE || []).map((b) => [b.brand, b]));
    return competitors
      .map((c) => {
        const bubble = bubbleByName.get(c.name);
        const sov = isLive
          ? finiteNumberOrNull(c.sov)
          : bubble?.sov ?? (finiteNumberOrNull(c.mentionRate) ?? 0) * 100;
        const panoGap = positiveGap(c.panoScore, analyticsPrimary.panoScore);
        const sentGap = positiveGap(c.sentiment, analyticsPrimary.sentiment);
        const scoreParts = [
          panoGap == null ? null : 0.45 * panoGap,
          sov == null ? null : 0.35 * sov,
          sentGap == null ? null : 0.20 * sentGap * 100,
        ].filter((value) => value != null);
        const threatScore = scoreParts.length
          ? scoreParts.reduce((sum, value) => sum + value, 0)
          : null;

        // Identify which dimension they're beating us on hardest
        const wins = [];
        if (panoGap != null && panoGap >= 2) wins.push({ key: 'pano', label: 'PANO', delta: panoGap.toFixed(1) });
        const primarySov = isLive
          ? finiteNumberOrNull(analyticsPrimary.sov)
          : (finiteNumberOrNull(analyticsPrimary.mentionRate) ?? 0) * 100;
        if (sov != null && primarySov != null && sov > primarySov) wins.push({ key: 'sov', label: 'SoV', delta: `+${(sov - primarySov).toFixed(1)}%` });
        if (sentGap != null && sentGap >= 0.05) wins.push({ key: 'sentiment', label: '情感', delta: `+${Math.round(sentGap * 100)}pt` });
        return { brand: c, sov, panoGap, sentGap, threatScore, wins };
      })
      .filter((card) => !isLive || card.threatScore != null)
      .sort((a, b) => (b.threatScore ?? -Infinity) - (a.threatScore ?? -Infinity))
      .slice(0, 3);
  }, [competitors, analyticsPrimary, isLive, liveCompetitorEvidenceState]);

  const [focusCompetitorId, setFocusCompetitorId] = useState(
    threatCards[0]?.brand?.id || competitors[0]?.id,
  );
  const focus = (liveCompetitorEvidenceState && !liveCompetitorEvidenceState.renderable)
    ? null
    : competitors.find((c) => c.id === focusCompetitorId) || threatCards[0]?.brand || competitors[0];

  // ──────────────────────────────────────────────────────────────
  // ②a Authority Radar — 1:1 我 vs 所选竞品 vs 行业中位
  // ──────────────────────────────────────────────────────────────
  const liveRadar = adaptAuthorityRadar(radarQ.data);
  const radarSrc = isLive ? liveRadar : AUTHORITY_RADAR_DATA;
  const radarIsMock = !isLive;
  const radarData = useMemo(
    () =>
      (radarSrc || []).map((row: any) => ({
        dimension: row.tier,
        me: row.me,
        industryMedian: row.industryMedian,
        focus: row.topCompetitor,
      })),
    [radarSrc],
  );

  // ──────────────────────────────────────────────────────────────
  // ②b Brand × Topic mention-rate heatmap for me vs focus (sequential).
  //     Deterministic synthetic generator until API lands.
  // ──────────────────────────────────────────────────────────────
  const heatmapTopics = [
    { topicId: 'c1', topicLabel: '保湿精华推荐' },
    { topicId: 'c2', topicLabel: '抗老护肤品牌' },
    { topicId: 'c3', topicLabel: '敏感肌适用' },
    { topicId: 'c4', topicLabel: '高端美白面霜' },
    { topicId: 'c5', topicLabel: '抗皱眼霜对比' },
    { topicId: 'c6', topicLabel: '性价比精华' },
    { topicId: 'c7', topicLabel: '孕妇可用成分' },
    { topicId: 'c8', topicLabel: '夜间修护方案' },
  ];
  const rowSeeds = focus
    ? [
        { brandId: primary.id, brandName: primary.name, _base: primary.mentionRate || 0 },
        { brandId: focus.id, brandName: focus.name, _base: focus.mentionRate || 0 },
      ]
    : [];
  const mockCompareHeatmapRows = rowSeeds.map((r) => ({
    brandId: r.brandId,
    brandName: r.brandName,
    values: heatmapTopics.map((topic, i) => {
      const wave = Math.sin((r.brandName.length + i) * 1.23) * 0.07;
      const v = Math.max(0, Math.min(1, r._base + wave + (i % 2 === 0 ? 0.015 : -0.01)));
      return { topicId: topic.topicId, topicLabel: topic.topicLabel, value: v, sample: 36 + ((i + r.brandName.length) % 19) };
    }),
  }));
  const liveHeatmapRows = adaptHeatmap(heatmapQ.data, primary.id);
  const compareHeatmapRows =
    isLive
      ? liveHeatmapRows.filter(
          (r) => r.brandId === primary.id || (focus && String(r.brandId) === String(focus.id)),
        )
      : mockCompareHeatmapRows;
  const compareHeatmapIsMock = !isLive;

  // ──────────────────────────────────────────────────────────────
  // ②c PANO trend (我 vs focus)
  // ──────────────────────────────────────────────────────────────
  const liveTrendData =
    isLive && trendsQ.data
      ? adaptCompetitorTrendsToTrendData(trendsQ.data, null)
      : null;
  const trendData = useMemo(() => {
    if (isLive) {
      // Convert {day, panoScore, [brand_name]: score} → recharts line shape
      return (liveTrendData || []).map((p, i) => ({
        name: p.day != null ? `D${p.day}` : `D${i + 1}`,
        ...p,
      }));
    }
    const maxDays = primary.sparkPano?.length || 14;
    return Array.from({ length: maxDays }, (_, i) => {
      const point: Record<string, any> = { name: `D${i + 1}` };
      point[primary.id] = primary.sparkPano?.[i] || 0;
      if (focus) point[focus.id] = focus.sparkPano?.[i] || 0;
      return point;
    });
  }, [primary, focus, liveTrendData, isLive]);
  const trendIsMock = !isLive;

  const trendLines = focus
    ? liveTrendData
      ? [
          { key: 'panoScore', label: analyticsPrimary.name, color: 'var(--color-accent)', area: true },
          { key: focus.name, label: focus.name, color: 'var(--color-chart-3)', area: false, dashed: true },
        ]
      : [
          { key: primary.id, label: primary.name, color: 'var(--color-accent)', area: true },
          { key: focus.id, label: focus.name, color: 'var(--color-chart-3)', area: false, dashed: true },
        ]
    : [];

  // ──────────────────────────────────────────────────────────────
  // ③ Structural context (kept but pushed below the fold)
  // ──────────────────────────────────────────────────────────────
  const liveGroup = adaptGroupSharedDomains(groupQ.data);
  const groupSrc = isLive ? liveGroup : SAME_GROUP_SHARED;
  const groupIsMock = !isLive;
  const sameGroupItems =
    groupSrc?.sharedDomains?.filter((d: any) => d.domain !== `${primary.id}.com.cn`) || [];

  // ──────────────────────────────────────────────────────────────
  // ④ Tier 2 权威媒体覆盖矩阵 (我 vs 3 主要竞品)
  // ──────────────────────────────────────────────────────────────
  const tier2Matrix = isLive ? null : TIER2_COVERAGE_MATRIX;
  const tier2MaxCount = useMemo(() => {
    if (!tier2Matrix?.brands) return 1;
    let max = 0;
    tier2Matrix.brands.forEach((row) => {
      (row.counts || []).forEach((v) => {
        if (v > max) max = v;
      });
    });
    return max || 1;
  }, [tier2Matrix]);

  return (
    <div className="space-y-3 pb-4">
      {/* Page header */}
      <div>
        <h2 className="text-xl font-brand font-bold text-themed-primary">
          <MetricLabel helpText={t('brand_competitors.page_subtitle', { brand: primary.name })}>
            {t('brand_competitors.page_title')}
          </MetricLabel>
        </h2>
      </div>

      {/* Shared filter bar */}
      <BrandAnalysisFilterBar />

      {/* ① Top 3 威胁卡 */}
      <div>
        <div className="flex items-baseline mb-1.5 px-1 gap-2">
          <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
            Top 3 威胁竞品
            <InfoTooltip text="按 PANO 差距 × SoV × 情感综合排序 · 点击卡片切换下方深度拆解" />
          </h3>
        </div>
        {threatCards.length === 0 ? (
          <Card className="p-3">
            {liveCompetitorEvidenceState ? (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-themed-primary">
                  Competitor comparison is {liveCompetitorEvidenceState.state}
                </p>
                <p className="text-xs text-themed-muted">
                  The configured competitive set is not ready for trustworthy SoV and sentiment scoring.
                </p>
                <p className="text-[11px] leading-relaxed text-themed-muted">
                  {[
                    liveCompetitorEvidenceState.reason,
                    ...liveCompetitorEvidenceState.missingInputs,
                    liveCompetitorEvidenceState.configuredCompetitorCount == null
                      ? ''
                      : `${liveCompetitorEvidenceState.configuredCompetitorCount} configured competitor${liveCompetitorEvidenceState.configuredCompetitorCount === 1 ? '' : 's'}`,
                  ].filter(Boolean).join(' · ')}
                </p>
              </div>
            ) : (
              <p className="text-xs text-themed-muted">暂未配置竞品，可在 Settings · 品牌 中添加 3-5 个竞品开始对比。</p>
            )}
          </Card>
        ) : (
          <div className="space-y-2">
            {liveCompetitorEvidenceState && liveCompetitorEvidenceState.renderable ? (
              <p className="text-[11px] text-themed-muted px-1">
                <Badge variant="muted" size="xs">数据为 partial</Badge>{' '}
                {liveCompetitorEvidenceState.reason || 'Partial Competitor Data'} —
                {' '}竞品和指标已按当前可用证据计算，部分分析器质量信号尚未补齐。
              </p>
            ) : null}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {threatCards.map((card, idx) => {
              const isFocus = card.brand.id === focusCompetitorId;
              return (
                <Card
                  key={card.brand.id}
                  className="p-3 cursor-pointer transition-all"
                  style={{
                    borderColor: isFocus ? 'var(--color-accent)' : 'var(--color-border-subtle)',
                    borderWidth: isFocus ? 2 : 1,
                    background: isFocus ? 'var(--color-accent-bg-light)' : 'var(--color-bg-card)',
                  }}
                  onClick={() => setFocusCompetitorId(card.brand.id)}
                >
                  <div className="flex items-start justify-between mb-1.5">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-semibold text-themed-muted">#{idx + 1} 威胁</span>
                        {isFocus && <Badge variant="accent" size="xs">聚焦中</Badge>}
                      </div>
                      <h4 className="text-sm font-semibold text-themed-primary mt-0.5">{card.brand.name}</h4>
                    </div>
                    <span className="text-lg font-brand font-bold text-themed-primary tabular-nums leading-none">
                      {card.threatScore == null ? '--' : card.threatScore.toFixed(0)}
                    </span>
                  </div>
                  <p className="text-[11px] text-themed-muted mb-1.5">在以下维度领先主品牌:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {card.wins.length === 0 ? (
                      <span className="text-[11px] text-themed-muted">整体略胜主品牌</span>
                    ) : (
                      card.wins.map((w) => (
                        <Badge key={w.key} variant="red" size="sm">
                          {w.label} {w.delta}
                        </Badge>
                      ))
                    )}
                  </div>
                </Card>
              );
            })}
            </div>
          </div>
        )}
      </div>

      {focus && (
        <>
          {/* ②a Authority Radar */}
          <Card className="p-3">
            <div className="flex items-baseline justify-between mb-1">
              <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
                Authority Radar · {primary.name} vs {focus.name}
                <InfoTooltip text="Tier 1 官方 / Tier 2 权威媒体 / Tier 3 KOL / Tier 4 UGC / 总覆盖" />
                {radarIsMock && <MockDataBadge />}
              </h3>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} margin={{ top: 12, right: 48, bottom: 12, left: 48 }}>
                <PolarGrid stroke="var(--color-border-subtle)" />
                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }} />
                <PolarRadiusAxis tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }} />
                <Radar name={primary.name} dataKey="me" stroke="var(--color-accent)" fill="var(--color-accent)" fillOpacity={0.2} strokeWidth={2} />
                <Radar name={focus.name} dataKey="focus" stroke="var(--color-chart-3)" fill="var(--color-chart-3)" fillOpacity={0.1} strokeWidth={1.5} />
                <Radar name="行业中位" dataKey="industryMedian" stroke="var(--color-chart-line-grid)" fill="var(--color-chart-line-grid)" fillOpacity={0.05} strokeWidth={1} />
                <Legend verticalAlign="bottom" height={24} iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }} />
              </RadarChart>
            </ResponsiveContainer>
          </Card>

          {/* ②b Brand × Topic heatmap */}
          <div>
            <div className="flex items-baseline justify-between mb-1.5 px-1">
              <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
                Topic 胜负图 · {primary.name} vs {focus.name}
                <InfoTooltip text="颜色越深 = 提及率越高 · 对比同一列看谁在该 Topic 占优" />
                {compareHeatmapIsMock && <MockDataBadge />}
              </h3>
            </div>
            <BrandTopicHeatmap
              rows={compareHeatmapRows}
              scale="sequential"
              metric="mentionRate"
              highlightBrandId={primary.id}
            />
          </div>

          {/* ②c PANO trend */}
          <Card className="p-3">
            <div className="flex items-baseline justify-between mb-1">
              <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
                PANO 趋势 · {primary.name} vs {focus.name}
                <InfoTooltip text="近 14 天走势" />
                {trendIsMock && <MockDataBadge />}
              </h3>
            </div>
            <TrendChart data={trendData} lines={trendLines} height={200} />
          </Card>
        </>
      )}

      {/* ③ Tier 2 权威媒体覆盖对比 */}
      {tier2Matrix?.brands?.length > 0 && (
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              Tier 2 权威媒体覆盖对比
              <InfoTooltip text="行 = 媒体域 · 列 = 品牌 · 单元格 = 近 30 天被引用次数 · 颜色越深 = 次数越多" />
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-themed-card">
                  <th className="py-1.5 px-2 text-left text-[10px] uppercase tracking-wider text-themed-muted font-medium">媒体域</th>
                  {tier2Matrix.brands.map((b) => (
                    <th
                      key={b.brandId}
                      className="py-1.5 px-2 text-right text-[10px] uppercase tracking-wider font-medium"
                      style={{
                        color: b.brandId === primary.id
                          ? 'var(--color-accent)'
                          : 'var(--color-text-muted)',
                      }}
                    >
                      {b.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tier2Matrix.domains.map((domain, di) => (
                  <tr key={domain} className="border-b border-themed-card last:border-b-0">
                    <td className="py-1.5 px-2 text-themed-primary tabular-nums">{domain}</td>
                    {tier2Matrix.brands.map((b) => {
                      const v = b.counts[di] ?? 0;
                      const intensity = Math.min(1, v / tier2MaxCount);
                      const isMe = b.brandId === primary.id;
                      // Use accent for me, neutral gray for competitors
                      const bg = isMe
                        ? `color-mix(in srgb, var(--color-accent) ${Math.round(intensity * 60)}%, transparent)`
                        : `color-mix(in srgb, var(--color-chart-line-grid) ${Math.round(intensity * 55)}%, transparent)`;
                      return (
                        <td
                          key={b.brandId}
                          className="py-1.5 px-2 text-right tabular-nums"
                          style={{
                            background: bg,
                            color: isMe && intensity > 0.3 ? 'var(--color-accent)' : 'var(--color-text-body)',
                            fontWeight: isMe ? 600 : 400,
                          }}
                        >
                          {v || '—'}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-themed-muted mt-2">
            {'读法: 同一行颜色最深的列 = 在该媒体拿到最多曝光的品牌; '}
            {'如果"我"一整列都很浅 = 在 Tier 2 权威媒体整体失声, 对应的行动面在 '}
            <span className="text-themed-primary font-medium">引用 → 内容缺口 / PR 目标</span>。
          </p>
        </Card>
      )}

      {/* ④ Same-Group 共享外链 (结构背景, 非胜负信号) */}
      {sameGroupItems.length > 0 && (
        <Card className="p-3">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="text-[13px] font-semibold text-themed-primary flex items-center gap-2">
              {t('brand_competitors.same_group_title')}
              {groupIsMock && <MockDataBadge />}
            </h3>
            <span className="text-[11px] text-themed-muted">
              {groupSrc?.group && `隶属集团: ${groupSrc.group}`}
              {groupSrc?.sharedRatio != null && ` · 共享占总引用 ${Math.round(groupSrc.sharedRatio * 100)}%`}
            </span>
          </div>
          <p className="text-[11px] text-themed-muted mb-2 leading-relaxed">
            {`你和以下子品牌属于同一母集团。当 AI 引擎引用这些官方/权威域名时, 母集团叙事会被加强, 但同一母集团的 `}
            <span className="text-themed-primary">兄弟品牌之间也会在同一 Topic 里互相稀释 SoV</span>
            {` — 这些不算"敌方竞品", 但在做 Topic 层策略时需要识别出来, 以免和自家人抢占位。`}
          </p>
          <div className="flex flex-col gap-1.5">
            {sameGroupItems.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between py-1.5 px-2 rounded bg-themed-subtle/40">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-themed-primary tabular-nums">{item.domain}</span>
                  <Badge variant="gray" size="xs">{`Tier ${item.tier}`}</Badge>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-themed-muted">子品牌:</span>
                  {(item.sharedWith || []).map((brand) => (
                    <Badge key={brand} variant={brand === primary.id ? 'blue' : 'gray'} size="xs">
                      {brand}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

    </div>
  );
}
