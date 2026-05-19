import React from 'react';
import { Badge, Card } from '../../../ui';
import type { TFunction } from '../lib/format';

export type Diagnostic = {
  id: string;
  severity: string;
  title: string;
  engine?: string;
};

export type AlertEmptyState = 'empty' | 'incomplete' | 'unavailable' | 'loading';

type AlertBarProps = {
  diagnostics: Diagnostic[] | null | undefined;
  emptyState?: AlertEmptyState;
  onAlertClick: (d: Diagnostic) => void;
  t: TFunction;
};

function emptyStateConfig(state: AlertEmptyState) {
  if (state === 'incomplete') {
    return {
      messageKey: 'dashboard.alerts.incomplete',
      borderColor: 'var(--color-warning)',
      textClass: 'text-themed-warning',
    };
  }
  if (state === 'unavailable') {
    return {
      messageKey: 'dashboard.alerts.unavailable',
      borderColor: 'var(--color-warning)',
      textClass: 'text-themed-warning',
    };
  }
  if (state === 'loading') {
    return {
      messageKey: 'dashboard.alerts.loading',
      borderColor: 'var(--color-border-strong)',
      textClass: 'text-themed-muted',
    };
  }
  return {
    messageKey: 'dashboard.alerts.no_p0p1',
    borderColor: 'var(--color-border-strong)',
    textClass: 'text-themed-muted',
  };
}

export default function AlertBar({ diagnostics, emptyState = 'empty', onAlertClick, t }: AlertBarProps) {
  if (!diagnostics || diagnostics.length === 0) {
    const config = emptyStateConfig(emptyState);
    return (
      <Card className="p-3 flex items-center gap-2 border-l-4" style={{ borderLeftColor: config.borderColor }}>
        <span className={`text-sm ${config.textClass}`}>{t(config.messageKey)}</span>
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
