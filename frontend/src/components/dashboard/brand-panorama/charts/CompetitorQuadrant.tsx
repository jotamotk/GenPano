import React from 'react';
import {
  ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import type { TFunction } from '../lib/format';

type BubbleDatum = {
  brand: string;
  sov: number;
  sentiment: number;
  mentions: number;
};

type CompetitorQuadrantProps = {
  data: BubbleDatum[] | null | undefined;
  primaryName: string;
  t: TFunction;
};

export default function CompetitorQuadrant({ data, primaryName, t }: CompetitorQuadrantProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sm text-themed-muted">
        暂无竞品共现数据
      </div>
    );
  }
  const xMax = Math.ceil(Math.max(...data.map((d) => d.sov)) * 1.1);
  const labels = {
    leader:    { x: xMax * 0.78, y: 0.92, text: t('dashboard.competition.q_leader') },
    highRisk:  { x: xMax * 0.78, y: 0.55, text: t('dashboard.competition.q_high_risk') },
    challenger:{ x: xMax * 0.18, y: 0.92, text: t('dashboard.competition.q_challenger') },
    warning:   { x: xMax * 0.18, y: 0.55, text: t('dashboard.competition.q_warning') },
  };

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="sov"
          domain={[0, xMax]}
          name={t('dashboard.competition.quadrant_axis_x')}
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          label={{
            value: t('dashboard.competition.quadrant_axis_x'),
            position: 'insideBottomRight',
            offset: -4,
            fontSize: 10,
            fill: 'var(--color-text-muted)',
          }}
        />
        <YAxis
          type="number"
          dataKey="sentiment"
          domain={[0.5, 1]}
          name={t('dashboard.competition.quadrant_axis_y')}
          tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
          axisLine={{ stroke: 'var(--color-border-subtle)' }}
          tickLine={false}
          label={{
            value: t('dashboard.competition.quadrant_axis_y'),
            angle: -90,
            position: 'insideLeft',
            offset: 10,
            fontSize: 10,
            fill: 'var(--color-text-muted)',
          }}
        />
        <ZAxis type="number" dataKey="mentions" range={[120, 720]} />
        <ReferenceLine x={xMax / 2} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
        <ReferenceLine y={0.75} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ strokeDasharray: '3 3', stroke: 'var(--color-accent)' }}
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          formatter={(value, key) => {
            if (key === 'sov')       return [`${value}%`, 'SoV'];
            if (key === 'sentiment') return [(value as number).toFixed(2), t('dashboard.competition.quadrant_axis_y')]; // C4-exempt: scatter Y∈[0,1]
            if (key === 'mentions')  return [value, 'Mentions'];
            return [value, key];
          }}
          labelFormatter={() => ''}
        />
        <Scatter
          data={data}
          shape={(props) => {
            const { cx, cy, payload, node } = props as { cx: number; cy: number; payload: BubbleDatum; node?: { size?: number } };
            const r = Math.sqrt((node && node.size) || 200) / 2;
            const isPrimary = payload.brand === primaryName;
            return (
              <g>
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={isPrimary ? 'var(--color-accent)' : 'var(--color-chart-3)'}
                  fillOpacity={isPrimary ? 0.85 : 0.55}
                  stroke={isPrimary ? 'var(--color-text-primary)' : 'var(--color-border-subtle)'}
                  strokeWidth={isPrimary ? 1.5 : 1}
                />
                <text
                  x={cx}
                  y={cy + r + 12}
                  textAnchor="middle"
                  fontSize={isPrimary ? 11 : 10}
                  fontWeight={isPrimary ? 700 : 400}
                  fill="var(--color-text-primary)"
                >
                  {payload.brand}
                </text>
              </g>
            );
          }}
        />
        {Object.values(labels).map((lab) => (
          <text
            key={lab.text}
            x={`${(lab.x / xMax) * 100}%`}
            y={`${(1 - (lab.y - 0.5) / 0.5) * 92 + 4}%`}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-text-muted)"
            opacity={0.7}
          >
            {lab.text}
          </text>
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
