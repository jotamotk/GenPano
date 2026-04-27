import React from 'react';
import {
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  Radar, Legend, Tooltip,
} from 'recharts';
import { Card, Badge } from '../ui';

/* ─────────────────────────────────────────────────────────────
   AuthorityRadarChart — PRD §4.2.7.D v1.1 竞品解构 (5 Tier 雷达)
   ─────────────────────────────────────────────────────────────
   数据形状 (AUTHORITY_RADAR_DATA):
     [{ tier: 'Tier 0..4', me, industryMedian, topCompetitor }]
   每品牌 5 Tier 之和 = 100.

   阅读故事: 你在哪个 Tier 层级"过重/过轻" — 比如 Tier 3 (KOL) 占比
              42 但 Tier 2 (权威媒体) 仅 11 (远低于行业中位 25), 说明
              背书结构"头轻脚重", 风险是 AI 权威降级.
─────────────────────────────────────────────────────────────── */
export default function AuthorityRadarChart({
  data = [],
  title = '引用来源层级分布',
  subtitle = '5 个 Tier 占比对比 · 你 vs 行业中位 vs Top 竞品',
  height = 320,
  className = '',
}) {
  const myTier2 = data.find((d) => d.tier?.startsWith('Tier 2'))?.me || 0;
  const medianTier2 =
    data.find((d) => d.tier?.startsWith('Tier 2'))?.industryMedian || 0;
  const tier2Gap = myTier2 - medianTier2;

  return (
    <Card className={`p-5 ${className}`}>
      <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-themed-primary">{title}</h3>
          <p className="text-xs text-themed-muted mt-0.5">{subtitle}</p>
        </div>
        {tier2Gap < 0 && (
          <Badge variant="orange" size="sm">
            Tier 2 权威媒体缺口 {Math.abs(tier2Gap)}pp
          </Badge>
        )}
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="var(--color-chart-line-grid)" />
          <PolarAngleAxis
            dataKey="tier"
            tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 50]}
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            axisLine={false}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              borderRadius: 'var(--radius-btn)',
              fontSize: 12,
              boxShadow: 'var(--shadow-card-hover)',
            }}
            formatter={(value) => [`${value}%`, undefined]}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} iconType="line" />
          <Radar
            name="Top 竞品"
            dataKey="topCompetitor"
            stroke="var(--color-chart-6)"
            fill="var(--color-chart-6)"
            fillOpacity={0.2}
          />
          <Radar
            name="行业中位"
            dataKey="industryMedian"
            stroke="var(--color-chart-3)"
            fill="var(--color-chart-3)"
            fillOpacity={0.15}
          />
          <Radar
            name="我"
            dataKey="me"
            stroke="var(--color-accent)"
            fill="var(--color-accent)"
            fillOpacity={0.35}
          />
        </RadarChart>
      </ResponsiveContainer>
    </Card>
  );
}
