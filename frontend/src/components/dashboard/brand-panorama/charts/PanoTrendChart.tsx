import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import type { TFunction } from '../lib/format';
import type { PanelBrand } from '../lib/normalize';

type TrendDatum = {
  day?: number;
  date?: string | null;
  name?: string | null;
  panoScore: number | null;
  [key: string]: number | string | null | undefined;
};

type PanoTrendChartProps = {
  trendData: TrendDatum[] | null | undefined;
  primaryName: string;
  competitors: PanelBrand[];
  isLive: boolean | undefined;
  t: TFunction;
};

const ISO_DATE_PREFIX = /^\d{4}-\d{2}-\d{2}/;

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function concreteDateLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!ISO_DATE_PREFIX.test(trimmed)) return null;
  return trimmed.slice(0, 10);
}

function fallbackText(t: TFunction, key: string, fallback: string): string {
  const value = t(key);
  return value === key ? fallback : value;
}

export default function PanoTrendChart({ trendData, primaryName, competitors, isLive, t: _t }: PanoTrendChartProps) {
  const normalized = useMemo(() => (trendData ?? []).map((d, i) => {
    const liveLabel = concreteDateLabel(d.date) || concreteDateLabel(d.name);
    const demoLabel =
      d.day != null
        ? `${d.day}d`
        : typeof d.name === 'string' && d.name.trim()
          ? d.name.trim()
          : `D${i + 1}`;
    const label = isLive ? liveLabel : demoLabel;
    if (!label) return null;

    const row: Record<string, number | string | null> = {
      name: label,
      [primaryName]: finiteNumber(d.panoScore),
    };
    competitors.forEach((c, idx) => {
      if (isLive) {
        row[c.name] = finiteNumber(d[c.name]);
      } else {
        const base = c.panoScore ?? 0;
        row[c.name] = Math.round(base + Math.sin((i + idx * 3) / 5) * 3);
      }
    });
    return row;
  }), [trendData, primaryName, competitors, isLive]);

  const data = normalized.filter((row): row is Record<string, number | string | null> => Boolean(row));
  const hasSourceRows = (trendData ?? []).length > 0;
  const hasMissingLiveDates = Boolean(isLive && hasSourceRows && normalized.some((row) => row == null));
  const seriesKeys = [primaryName, ...competitors.map((c) => c.name)];
  const hasTrendValues = data.some((row) =>
    seriesKeys.some((key) => typeof row[key] === 'number' && Number.isFinite(row[key] as number)),
  );

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[280px] text-sm text-themed-muted">
        {hasMissingLiveDates
          ? fallbackText(_t, 'dashboard.trend.dates_missing', 'Live trend dates are missing.')
          : fallbackText(_t, 'dashboard.trend.empty', 'No trend data yet.')}
      </div>
    );
  }

  if (!hasTrendValues) {
    return (
      <div className="flex items-center justify-center h-[280px] text-sm text-themed-muted">
        {fallbackText(_t, 'dashboard.trend.values_missing', 'Live trend values are unavailable.')}
      </div>
    );
  }

  return (
    <>
      {hasMissingLiveDates && (
        <div className="mb-2 text-xs text-themed-muted">
          {fallbackText(_t, 'dashboard.trend.partial_dates', 'Some live trend points are missing dates.')}
        </div>
      )}
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
    </>
  );
}
