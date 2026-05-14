import React from 'react';
import { MiniSparkline } from '../../../charts';

type SparklineRow = {
  label: string;
  spark: number[];
  value: React.ReactNode;
  color?: string;
};

type KpiSparklineSummaryProps = {
  rows: SparklineRow[];
};

export default function KpiSparklineSummary({ rows }: KpiSparklineSummaryProps) {
  return (
    <div className="space-y-4">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-4">
          <span className="text-xs text-themed-muted w-20 shrink-0">{r.label}</span>
          <div className="flex-1 h-10">
            <MiniSparkline data={r.spark} color={r.color || 'var(--color-accent)'} />
          </div>
          <span className="text-sm font-semibold tabular-nums text-themed-primary w-16 text-right">
            {r.value}
          </span>
        </div>
      ))}
    </div>
  );
}
