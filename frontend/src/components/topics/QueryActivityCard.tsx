/**
 * QueryActivityCard — TopicsPage live data slice (PRD §4.2 supplement).
 *
 * 渲染品牌维度的 Query 活动指标，数据来自 `/api/admin/queries/analytics`，
 * 由 `useQueryAnalytics(brandId)` 拉取，再经 `queryAnalyticsAdapter` 转成
 * 复用图表组件（TrendChart / DonutChart / HorizontalBar）需要的 props。
 *
 * 上游：`pages/TopicsPage.tsx` 在顶部 FilterBar 与现有 4 层下钻之间挂载本卡。
 * 下游：所有 chart 组件位于 `components/charts/`，使用 token 化样式。
 */

import React from 'react';
import { Card } from '../ui';
import TrendChart from '../charts/TrendChart';
import DonutChart from '../charts/DonutChart';
import HorizontalBar from '../charts/HorizontalBar';
import { useQueryAnalytics } from '../../hooks/useQueryAnalytics';
import {
  toEngineBars,
  toKpis,
  toPositionBars,
  toSentimentDonut,
  toTopicBars,
  toTrendSeries,
} from '../../adapters/queryAnalyticsAdapter';

interface QueryActivityCardProps {
  brandId: number | null | undefined;
  brandName?: string;
  dateFrom?: string;
  dateTo?: string;
}

const TREND_LINES = [
  { key: 'mentionRate', label: '命中率', color: 'var(--color-chart-2)' },
  { key: 'sentiment', label: '情感分', color: 'var(--color-chart-6)' },
  { key: 'geoScore', label: 'GEO 分', color: 'var(--color-chart-3)' },
];

function fmtPct(v: number | null): string {
  return v == null ? '—' : `${(v * 100).toFixed(1)}%`;
}

function fmtScore(v: number | null): string {
  return v == null ? '—' : v.toFixed(2);
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card-lg bg-surface border border-b-card p-4 flex-1">
      <div className="text-[11px] text-ink-muted">{label}</div>
      <div className="text-[22px] font-bold text-ink tabular-nums mt-1">{value}</div>
      {hint && <div className="text-[10px] text-ink-faint mt-0.5">{hint}</div>}
    </div>
  );
}

export default function QueryActivityCard({
  brandId,
  brandName,
  dateFrom,
  dateTo,
}: QueryActivityCardProps) {
  const { data, isLoading, isError, error } = useQueryAnalytics({
    brandId,
    dateFrom,
    dateTo,
  });

  if (!brandId) {
    return (
      <Card className="p-6 text-center text-[12px] text-ink-muted">
        请选择品牌以查看查询活动指标
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card className="p-6 text-center text-[12px] text-ink-muted">
        加载查询活动指标…
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-6 text-center text-[12px] text-danger">
        加载失败：{(error as Error)?.message || '未知错误'}
      </Card>
    );
  }

  const kpis = toKpis(data);
  const trend = toTrendSeries(data?.daily_trend);
  const sentimentSlices = toSentimentDonut(data?.sentiment_distribution);
  const topicBars = toTopicBars(data?.by_topic);
  const engineBars = toEngineBars(data?.by_engine);
  const positionBars = toPositionBars(data?.position_distribution);
  const sentimentTotal = sentimentSlices.reduce((acc, s) => acc + s.value, 0);

  const headlineSuffix = brandName ? `· ${brandName}` : '';

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <h3 className="text-[14px] font-semibold text-ink">查询活动指标 {headlineSuffix}</h3>
          <div className="text-[11px] text-ink-muted">
            数据基于 LLM Response 分析（{data?.filters?.date_from} ~ {data?.filters?.date_to}）
          </div>
        </div>
        <div className="text-[11px] text-ink-faint tabular-nums">
          总响应 {data?.totals?.responses ?? 0} · 已分析 {data?.totals?.analyzed ?? 0}
        </div>
      </div>

      {/* KPI 行 */}
      <div className="flex gap-3">
        <Kpi label="总查询" value={kpis.totalQueries.toLocaleString()} />
        <Kpi
          label="命中率"
          value={fmtPct(kpis.mentionRate)}
          hint={`${data?.totals?.mentions_target ?? 0} / ${data?.totals?.responses ?? 0}`}
        />
        <Kpi label="平均情感" value={fmtScore(kpis.avgSentiment)} />
        <Kpi label="平均 GEO 分" value={fmtScore(kpis.avgGeoScore)} />
      </div>

      {/* 趋势 */}
      <Card className="p-4">
        <div className="text-[12px] font-semibold text-ink mb-2">每日趋势</div>
        {trend.length > 0 ? (
          <TrendChart data={trend} lines={TREND_LINES} height={220} />
        ) : (
          <div className="text-center text-[11px] text-ink-muted py-12">该窗口无数据</div>
        )}
      </Card>

      {/* 情感分布 + Top Topics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">情感分布</div>
          {sentimentTotal > 0 ? (
            <div className="flex items-center gap-4">
              <DonutChart segments={sentimentSlices} size={160} />
              <div className="flex-1 space-y-1.5 text-[12px]">
                {sentimentSlices.map((s) => (
                  <div key={s.name} className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block w-2.5 h-2.5 rounded-full"
                        style={{ background: s.color }}
                      />
                      {s.name}
                    </span>
                    <span className="tabular-nums text-ink-muted">
                      {s.value}（{Math.round((s.value / sentimentTotal) * 100)}%）
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">该窗口无数据</div>
          )}
        </Card>

        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">Top Topics（命中率）</div>
          {topicBars.length > 0 ? (
            <HorizontalBar data={topicBars} valueSuffix="%" />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">该窗口无数据</div>
          )}
        </Card>
      </div>

      {/* 引擎对比 + 排名分布 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">引擎命中率</div>
          {engineBars.length > 0 ? (
            <HorizontalBar data={engineBars} valueSuffix="%" />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">该窗口无数据</div>
          )}
        </Card>

        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">品牌排名分布</div>
          {positionBars.some((b) => b.value > 0) ? (
            <HorizontalBar
              data={positionBars}
              valueSuffix=""
              defaultColor="var(--color-chart-3)"
            />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">该窗口无数据</div>
          )}
        </Card>
      </div>
    </div>
  );
}
