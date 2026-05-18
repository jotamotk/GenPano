import React from 'react';
import {
  ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import type { TFunction } from '../lib/format';

type BubbleDatum = {
  brand: string;
  sov: number | null;
  sentiment: number | null;
  mentions: number;
};

type CompetitorQuadrantProps = {
  data: BubbleDatum[] | null | undefined;
  primaryName: string;
  t: TFunction;
};

export default function CompetitorQuadrant({ data, primaryName, t }: CompetitorQuadrantProps) {
  const rows = Array.isArray(data) ? data : [];
  const axisReadyRows = rows.filter(
    (row): row is BubbleDatum & { sov: number; sentiment: number } =>
      Number.isFinite(row.sov) && Number.isFinite(row.sentiment),
  );
  const axisIncompleteCount = rows.length - axisReadyRows.length;
  const missingWeightCount = axisReadyRows.filter((row) => !Number.isFinite(row.mentions) || row.mentions <= 0).length;

  if (rows.length === 0) {
    return (
      <div className="flex h-[300px] flex-col items-center justify-center gap-2 text-center">
        <div className="text-sm font-medium text-themed-primary">Competitor quadrant is waiting for evidence</div>
        <div className="max-w-sm text-xs leading-relaxed text-themed-muted">
          No co-mention rows are available yet, so Share of Voice, Sentiment, and sample weight cannot be plotted safely.
        </div>
      </div>
    );
  }

  if (axisReadyRows.length === 0) {
    return (
      <div className="flex h-[300px] flex-col items-center justify-center gap-2 text-center">
        <div className="text-sm font-medium text-themed-primary">Competitor quadrant is partial</div>
        <div className="max-w-sm text-xs leading-relaxed text-themed-muted">
          SoV or sentiment evidence is incomplete for {rows.length} brand{rows.length === 1 ? '' : 's'}, so the axes are not trustworthy yet.
        </div>
      </div>
    );
  }

  const xMax = Math.max(10, Math.ceil(Math.max(...axisReadyRows.map((d) => d.sov)) * 1.1));
  const labels = {
    leader: { x: xMax * 0.78, y: 0.72, text: t('dashboard.competition.q_leader') },
    highRisk: { x: xMax * 0.78, y: -0.72, text: t('dashboard.competition.q_high_risk') },
    challenger: { x: xMax * 0.18, y: 0.72, text: t('dashboard.competition.q_challenger') },
    warning: { x: xMax * 0.18, y: -0.72, text: t('dashboard.competition.q_warning') },
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-themed-muted">
        <span className="rounded border border-themed-card px-2 py-1">X: Share of Voice</span>
        <span className="rounded border border-themed-card px-2 py-1">Y: Sentiment</span>
        <span className="rounded border border-themed-card px-2 py-1">Bubble: co-mentions / evidence count</span>
      </div>
      {(axisIncompleteCount > 0 || missingWeightCount > 0) && (
        <div className="rounded border border-themed-card bg-themed-subtle/40 px-3 py-2 text-[11px] leading-relaxed text-themed-muted">
          {axisIncompleteCount > 0 && (
            <span>
              {axisIncompleteCount} brand{axisIncompleteCount === 1 ? '' : 's'} has incomplete SoV or sentiment evidence.
            </span>
          )}
          {axisIncompleteCount > 0 && missingWeightCount > 0 && <span> </span>}
          {missingWeightCount > 0 && (
            <span>
              {missingWeightCount} plotted brand{missingWeightCount === 1 ? '' : 's'} lacks positive sample weight.
            </span>
          )}
        </div>
      )}
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
            domain={[-1, 1]}
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
          <ReferenceLine y={0} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
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
              if (key === 'sov') return [`${value}%`, 'SoV'];
              if (key === 'sentiment') return [(value as number).toFixed(2), t('dashboard.competition.quadrant_axis_y')];
              if (key === 'mentions') return [value, 'Co-mentions'];
              return [value, key];
            }}
            labelFormatter={() => ''}
          />
          <Scatter
            data={axisReadyRows}
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
              y={`${(1 - (lab.y + 1) / 2) * 92 + 4}%`}
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
    </div>
  );
}
