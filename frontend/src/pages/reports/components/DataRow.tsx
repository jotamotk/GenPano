import type { ReactNode } from 'react';
import { deltaSign, deltaToneClass } from '../lib/exporters';

export function DataRow({
  label,
  value,
  delta,
}: {
  label: ReactNode;
  value: ReactNode;
  delta?: number;
}) {
  const deltaCls = deltaToneClass(delta ?? 0);
  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-themed-subtle last:border-b-0">
      <span className="text-xs text-themed-muted">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tabular-nums text-themed-primary">{value}</span>
        {delta !== undefined && (
          <span className={`text-[11px] tabular-nums ${deltaCls}`}>
            {deltaSign(delta)}{delta}
          </span>
        )}
      </span>
    </div>
  );
}
