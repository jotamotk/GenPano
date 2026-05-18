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
  endpointState?: string | null;
  stateReason?: string | null;
  missingInputs?: string[];
  configuredCompetitorCount?: number | null;
};

type CompetitorQuadrantProps = {
  data: BubbleDatum[] | null | undefined;
  primaryName: string;
  t: TFunction;
};

function labelize(value: string | null | undefined) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

// Issue #1185 follow-up — partial state_reasons whose payload still carries
// usable competitor rows. Mirrors BrandCompetitorsPage.tsx:136-140 (PR #1253).
const PARTIAL_REASONS_THAT_STILL_RENDER_DATA = new Set([
  'partial_competitor_data',
  'partial_data',
  'partial_analyzer_data',
]);

export default function CompetitorQuadrant({ data, primaryName, t }: CompetitorQuadrantProps) {
  const rows = Array.isArray(data) ? data : [];
  const endpointStateRow = rows.find((row) => row.endpointState && row.endpointState !== 'ok');
  const chartRows = rows.filter((row) => row.brand);
  const axisReadyRows = chartRows.filter(
    (row): row is BubbleDatum & { sov: number; sentiment: number } =>
      Number.isFinite(row.sov) && Number.isFinite(row.sentiment),
  );
  const axisIncompleteCount = chartRows.length - axisReadyRows.length;
  const missingWeightCount = axisReadyRows.filter((row) => !Number.isFinite(row.mentions) || row.mentions <= 0).length;

  // When endpoint state is non-ok but the partiality is just "data is partial,
  // rows are still scoped and usable", fall through to plot bubbles and surface
  // the partiality as a small badge above the chart. Metric-trust failures
  // (missing_formula_inputs, missing_required_inputs, missing_analyzer_rows)
  // keep the full suppression below because the numbers themselves can't be
  // trusted.
  const stateReasonNormalized = String(endpointStateRow?.stateReason || '').toLowerCase();
  const renderableDespitePartial =
    !!endpointStateRow &&
    PARTIAL_REASONS_THAT_STILL_RENDER_DATA.has(stateReasonNormalized) &&
    axisReadyRows.length >= 1;

  if (endpointStateRow && !renderableDespitePartial) {
    const state = endpointStateRow.endpointState || 'partial';
    const reason = labelize(endpointStateRow.stateReason);
    const missingInputs = endpointStateRow.missingInputs?.map(labelize).filter(Boolean) ?? [];
    const configuredCount = endpointStateRow.configuredCompetitorCount;
    return (
      <div className="flex h-[300px] flex-col items-center justify-center gap-2 text-center">
        <div className="text-sm font-medium text-themed-primary">
          Competitor quadrant is {state}
        </div>
        <div className="max-w-sm text-xs leading-relaxed text-themed-muted">
          The metrics endpoint marked this competitive set as incomplete, so SoV and sentiment are not plotted as normal bubbles.
        </div>
        <div className="max-w-sm text-[11px] leading-relaxed text-themed-muted">
          {[reason, ...missingInputs].filter(Boolean).join(' · ')}
          {configuredCount != null && (
            <span>{`${reason || missingInputs.length ? ' · ' : ''}${configuredCount} configured competitor${configuredCount === 1 ? '' : 's'}`}</span>
          )}
        </div>
      </div>
    );
  }

  if (chartRows.length === 0) {
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
          SoV or sentiment evidence is incomplete for {chartRows.length} brand{chartRows.length === 1 ? '' : 's'}, so the axes are not trustworthy yet.
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
      {renderableDespitePartial && endpointStateRow && (
        <div className="rounded border border-themed-card bg-themed-subtle/40 px-3 py-2 text-[11px] leading-relaxed text-themed-muted">
          <span className="rounded border border-themed-card px-2 py-1">数据为 partial</span>
          {' '}
          {labelize(endpointStateRow.stateReason) || 'Partial Competitor Data'}
          {' '}— 竞品和指标已按当前可用证据计算，部分分析器质量信号尚未补齐。
        </div>
      )}
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
