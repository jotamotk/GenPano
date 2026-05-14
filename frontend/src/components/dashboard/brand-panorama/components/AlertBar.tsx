import React from 'react';
import { Badge, Card } from '../../../ui';
import type { TFunction } from '../lib/format';

export type Diagnostic = {
  id: string;
  severity: string;
  title: string;
  engine?: string;
};

type AlertBarProps = {
  diagnostics: Diagnostic[] | null | undefined;
  onAlertClick: (d: Diagnostic) => void;
  t: TFunction;
};

export default function AlertBar({ diagnostics, onAlertClick, t }: AlertBarProps) {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <Card className="p-3 flex items-center gap-2 border-l-4" style={{ borderLeftColor: 'var(--color-success)' }}>
        <span className="text-sm text-themed-success">{t('dashboard.alerts.empty')}</span>
      </Card>
    );
  }
  return (
    <div className="space-y-2">
      {diagnostics.map((d) => {
        const isP0 = d.severity === 'P0';
        return (
          <Card
            key={d.id}
            className="p-3 flex items-center gap-3 border-l-4 cursor-pointer transition-colors hover:bg-themed-subtle"
            style={{ borderLeftColor: isP0 ? 'var(--color-danger)' : 'var(--color-warning)' }}
            onClick={() => onAlertClick(d)}
          >
            <Badge variant={isP0 ? 'red' : 'yellow'} size="sm">{d.severity}</Badge>
            <span className="text-sm text-themed-primary flex-1 truncate">{d.title}</span>
            <span className="text-xs text-themed-muted shrink-0 hidden md:inline">{d.engine}</span>
            <span className="text-xs text-themed-accent shrink-0">{t('dashboard.alerts.view')}</span>
          </Card>
        );
      })}
    </div>
  );
}
