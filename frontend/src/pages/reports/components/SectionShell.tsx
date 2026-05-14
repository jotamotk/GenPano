import type { ReactNode } from 'react';
import { Badge, Card } from '../../../components/ui';
import type { TFn } from '../lib/types';
import { ReaderBadge } from './ReaderBadge';
import { StackLayerBadges } from './StackLayerBadges';

export function SectionShell({
  order,
  title,
  variantLabel,
  narrative,
  children,
  emphasized,
  primaryReader,
  insightStackLayers,
  t,
}: {
  order: number;
  title: ReactNode;
  variantLabel?: ReactNode;
  narrative?: ReactNode;
  children?: ReactNode;
  emphasized?: boolean;
  primaryReader?: string;
  insightStackLayers?: number[];
  t: TFn;
}) {
  return (
    <Card
      className={`p-6 ${emphasized ? 'border border-themed-strong' : ''}`}
      style={emphasized ? { background: 'var(--color-accent-subtle)' } : undefined}
    >
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-themed-inverse bg-themed-gradient-accent"
        >
          {order}
        </span>
        <h3 className="text-sm font-semibold text-themed-primary flex-1">{title}</h3>
        <ReaderBadge reader={primaryReader} t={t} />
        <StackLayerBadges layers={insightStackLayers} />
        {variantLabel && <Badge variant="accent" size="sm">{variantLabel}</Badge>}
      </div>
      {children && <div className="mb-4">{children}</div>}
      {narrative && (
        <div className="pt-4 border-t border-themed-subtle">
          <p className="text-[11px] uppercase tracking-wider text-themed-muted mb-1.5">LLM</p>
          <p className="text-sm text-themed-body leading-relaxed">{narrative}</p>
        </div>
      )}
    </Card>
  );
}
