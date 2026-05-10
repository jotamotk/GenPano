import React, { useMemo } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { Card, MetricLabel } from '../ui';

/* ─────────────────────────────────────────────────────────────
   AuthorityShareTimeSeries — PRD §4.2.7.A 归因方法时序堆叠图
   ─────────────────────────────────────────────────────────────
   数据形状 (AUTHORITY_SHARE_SERIES):
     [{ date, official_domain_pct, co_occurrence_pct, text_match_pct }, ...]

   语义编码 (低→高归因强度):
     - text_match      → 最弱归因 (仅出现品牌文字)         → warning 色
     - co_occurrence   → 中等 (品牌名与 URL 在同句/段共现) → accent 色
     - official_domain → 强归因 (brand.domains 官方域命中) → success 色

   触发故事: 当 official_domain% 连续下降, 说明"被引用但不归因到你",
             对应 citation_attribution_mismatch P2 Alert (§4.2.7.A).

   颜色走 var(--color-*) token, 禁硬编码 hex (DESIGN_TOKENS §1).
   尺寸走 ResponsiveContainer 100% (C1 chart contract).
─────────────────────────────────────────────────────────────── */
export default function AuthorityShareTimeSeries({
  data = [],
  title,
  subtitle,
  height = 240,
  className = '',
}) {
  const lastPoint = data[data.length - 1] || {};
  const firstPoint = data[0] || {};

  const officialDelta = useMemo(() => {
    const d =
      (lastPoint.official_domain_pct ?? 0) - (firstPoint.official_domain_pct ?? 0);
    return Math.round(d * 10) / 10;
  }, [data]);

  return (
    <Card className={`p-5 ${className}`}>
      {(title || subtitle) && (
        <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-themed-primary">
                <MetricLabel helpText={subtitle}>{title}</MetricLabel>
              </h3>
            )}
          </div>
          {data.length >= 2 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-themed-muted">
                <MetricLabel helpText="当前周期末与周期初的官方域归因占比差值。">
                  官方域占比变化
                </MetricLabel>
              </span>
              <span
                className="font-semibold tabular-nums"
                style={{
                  color:
                    officialDelta >= 0
                      ? 'var(--color-success)'
                      : 'var(--color-danger)',
                }}
              >
                {officialDelta >= 0 ? '+' : ''}
                {officialDelta} pp
              </span>
            </div>
          )}
        </div>
      )}

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
          stackOffset="expand"
        >
          <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
            axisLine={{ stroke: 'var(--color-border-subtle)' }}
            tickLine={false}
            tickFormatter={(d) => (d || '').slice(5)}
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
            axisLine={{ stroke: 'var(--color-border-subtle)' }}
            tickLine={false}
            tickFormatter={(v) => `${Math.round(v * 100)}%`}
            domain={[0, 1]}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              borderRadius: 'var(--radius-btn)',
              fontSize: 12,
              boxShadow: 'var(--shadow-card-hover)',
            }}
            formatter={(value, name) => [`${value}%`, name]}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
            iconType="square"
          />
          <Area
            type="monotone"
            dataKey="official_domain_pct"
            name="官方域归因"
            stackId="authority"
            stroke="var(--color-chart-7)"
            fill="var(--color-chart-7)"
            fillOpacity={0.85}
          />
          <Area
            type="monotone"
            dataKey="co_occurrence_pct"
            name="共现归因"
            stackId="authority"
            stroke="var(--color-chart-5)"
            fill="var(--color-chart-5)"
            fillOpacity={0.8}
          />
          <Area
            type="monotone"
            dataKey="text_match_pct"
            name="文本匹配归因"
            stackId="authority"
            stroke="var(--color-chart-6)"
            fill="var(--color-chart-6)"
            fillOpacity={0.75}
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}
