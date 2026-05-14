import React from 'react';
import { Card, MetricLabel } from '../../../ui';
import { MiniSparkline } from '../../../charts';
import { KPI_TONE } from '../lib/constants';

type KpiCardProps = {
  label: React.ReactNode;
  fullLabel?: React.ReactNode;
  value: React.ReactNode;
  delta?: number | null;
  helpText?: React.ReactNode;
  sparkData?: number[];
  trendIsRank?: boolean;
  onClick?: () => void;
};

export default function KpiCard({
  label, fullLabel, value, delta, helpText, sparkData, trendIsRank, onClick,
}: KpiCardProps) {
  const hasDelta = delta !== undefined && delta !== null;
  const positive = hasDelta && (trendIsRank ? delta > 0 : delta > 0);
  const negative = hasDelta && (trendIsRank ? delta < 0 : delta < 0);
  const tone = positive ? KPI_TONE.pos : negative ? KPI_TONE.neg : KPI_TONE.flat;
  const arrow = positive ? '↗' : negative ? '↘' : '→';
  const deltaStr = trendIsRank
    ? (delta! > 0 ? `↑${delta}` : delta! < 0 ? `↓${Math.abs(delta!)}` : '·')
    : (delta! > 0 ? `+${delta}` : `${delta}`);

  return (
    <Card
      className={`p-4 transition-shadow ${onClick ? 'cursor-pointer hover:shadow-card-hover' : ''}`.trim()}
      onClick={onClick}
    >
      <div className="flex items-baseline justify-between mb-1.5">
        <MetricLabel helpText={helpText} className="text-xs font-medium text-themed-muted">
          {label}
        </MetricLabel>
        <span className="text-[10px] uppercase tracking-wider text-themed-muted opacity-60">{fullLabel}</span>
      </div>
      <div className="flex items-end justify-between mb-2">
        <span className="text-2xl font-brand font-bold text-themed-primary tabular-nums leading-none">{value}</span>
        {hasDelta && <span className={`text-xs font-medium tabular-nums ${tone}`}>{arrow} {deltaStr}</span>}
      </div>
      {sparkData && sparkData.length > 0 && (
        <div className="h-7 -mx-1">
          <MiniSparkline data={sparkData} color="var(--color-accent)" />
        </div>
      )}
    </Card>
  );
}
