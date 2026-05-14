import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import type { TFunction } from '../lib/format';
import type { PanelBrand } from '../lib/normalize';

type TrendDatum = {
  day: number;
  panoScore: number;
  [key: string]: number | null | undefined;
};

type PanoTrendChartProps = {
  trendData: TrendDatum[] | null | undefined;
  primaryName: string;
  competitors: PanelBrand[];
  isLive: boolean | undefined;
  t: TFunction;
};

export default function PanoTrendChart({ trendData, primaryName, competitors, isLive, t: _t }: PanoTrendChartProps) {
  const data = useMemo(() => (trendData ?? []).map((d, i) => {
    const row: Record<string, number | string | null> = { name: `${d.day}d`, [primaryName]: d.panoScore };
    competitors.forEach((c, idx) => {
      if (isLive) {
        row[c.name] = (d[c.name] as number | null | undefined) ?? null;
      } else {
        const base = c.panoScore ?? 0;
        row[c.name] = Math.round(base + Math.sin((i + idx * 3) / 5) * 3);
      }
    });
    return row;
  }), [trendData, primaryName, competitors, isLive]);

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[280px] text-sm text-themed-muted">
        暂无趋势数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-chart-line-grid)" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          interval={4}
        />
        <YAxis
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          domain={[60, 90]}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          cursor={{ stroke: 'var(--color-accent)', strokeDasharray: '3 3' }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }} />
        <Line
          type="monotone"
          dataKey={primaryName}
          stroke="var(--color-accent)"
          strokeWidth={2.4}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
        {competitors.map((c) => (
          <Line
            key={c.id}
            type="monotone"
            dataKey={c.name}
            stroke="var(--color-chart-line-grid)"
            strokeWidth={1.4}
            dot={false}
            opacity={0.6}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
