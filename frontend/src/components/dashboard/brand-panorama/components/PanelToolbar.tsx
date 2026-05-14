import React from 'react';
import { Card } from '../../../ui';
import ProfileGroupFilter from '../../../filters/ProfileGroupFilter';
import FilterPill from './FilterPill';
import type { TFunction } from '../lib/format';

type Engine = { name: string; color?: string };

type PanelToolbarProps = {
  range: string;
  engines: Engine[];
  selectedEngines: string[];
  onRangeChange: (next: string) => void;
  onEngineToggle: (name: string) => void;
  onEngineAll: () => void;
  dimension: string;
  onDimensionChange: (next: string) => void;
  intent: string;
  onIntentChange: (next: string) => void;
  filtersExpanded: boolean;
  onToggleFilters: () => void;
  t: TFunction;
};

export default function PanelToolbar({
  range, engines, selectedEngines,
  onRangeChange, onEngineToggle, onEngineAll,
  dimension, onDimensionChange,
  intent, onIntentChange,
  filtersExpanded, onToggleFilters,
  t,
}: PanelToolbarProps) {
  const ranges = [
    { id: '7d',  label: t('dashboard.toolbar.range_7d')  },
    { id: '30d', label: t('dashboard.toolbar.range_30d') },
    { id: '90d', label: t('dashboard.toolbar.range_90d') },
  ];
  const allEnginesSelected = selectedEngines.length === engines.length;

  const dimensions = [
    { id: '',          label: t('dashboard.toolbar.dimension_all') },
    { id: '品类',      label: t('dashboard.toolbar.dimension_category') },
    { id: '品牌',      label: t('dashboard.toolbar.dimension_brand') },
    { id: '产品',      label: t('dashboard.toolbar.dimension_product') },
    { id: '竞品',      label: t('dashboard.toolbar.dimension_competitor') },
  ];
  const intents = [
    { id: '',              label: t('dashboard.toolbar.intent_all') },
    { id: 'informational', label: t('dashboard.toolbar.intent_informational') },
    { id: 'commercial',    label: t('dashboard.toolbar.intent_commercial') },
    { id: 'transactional', label: t('dashboard.toolbar.intent_transactional') },
    { id: 'navigational',  label: t('dashboard.toolbar.intent_navigational') },
  ];

  const expandedActiveCount = (dimension ? 1 : 0) + (intent ? 1 : 0);

  return (
    <Card className="p-3">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.range_label')}</span>
          <div className="flex gap-1">
            {ranges.map((r) => (
              <FilterPill key={r.id} active={range === r.id} onClick={() => onRangeChange(r.id)}>
                {r.label}
              </FilterPill>
            ))}
          </div>
        </div>

        <div className="h-5 w-px bg-themed-card" />

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.engine_label')}</span>
          <FilterPill active={allEnginesSelected} onClick={onEngineAll}>
            {t('dashboard.toolbar.engine_all')}
          </FilterPill>
          {engines.map((e) => {
            const active = selectedEngines.includes(e.name);
            return (
              <FilterPill key={e.name} active={active} onClick={() => onEngineToggle(e.name)}>
                <span className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle" style={{ background: e.color }} />
                {e.name}
              </FilterPill>
            );
          })}
        </div>

        <div className="h-5 w-px bg-themed-card" />
        <ProfileGroupFilter />

        <div className="h-5 w-px bg-themed-card" />
        <button
          onClick={onToggleFilters}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors text-themed-muted hover:text-themed-primary"
          style={{
            background: filtersExpanded ? 'var(--color-accent-bg-light)' : 'transparent',
            border: filtersExpanded ? 'none' : '1px solid var(--color-border-subtle)',
          }}
        >
          {filtersExpanded ? t('dashboard.toolbar.collapse_filters') : t('dashboard.toolbar.more_filters')}
          {expandedActiveCount > 0 && !filtersExpanded && (
            <span
              className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold"
              style={{ background: 'var(--color-accent)', color: 'var(--color-text-inverse)' }}
            >
              {expandedActiveCount}
            </span>
          )}
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className={`transition-transform ${filtersExpanded ? 'rotate-180' : ''}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {!filtersExpanded && expandedActiveCount > 0 && (
          <div className="flex items-center gap-1.5">
            {dimension && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-pill text-[10px] font-medium text-themed-accent"
                style={{ background: 'var(--color-accent-bg-light)' }}>
                {t('dashboard.toolbar.dimension_label')}: {dimensions.find(d => d.id === dimension)?.label}
                <button onClick={() => onDimensionChange('')} className="ml-0.5 opacity-60 hover:opacity-100">×</button>
              </span>
            )}
            {intent && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-pill text-[10px] font-medium text-themed-accent"
                style={{ background: 'var(--color-accent-bg-light)' }}>
                {t('dashboard.toolbar.intent_label')}: {intents.find(i => i.id === intent)?.label}
                <button onClick={() => onIntentChange('')} className="ml-0.5 opacity-60 hover:opacity-100">×</button>
              </span>
            )}
          </div>
        )}
      </div>

      {filtersExpanded && (
        <div className="flex items-center gap-4 flex-wrap mt-3 pt-3" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
          <div className="flex items-center gap-2">
            <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.dimension_label')}</span>
            <div className="flex gap-1">
              {dimensions.map((d) => (
                <FilterPill key={d.id} active={(d.id === '' && !dimension) || d.id === dimension} onClick={() => onDimensionChange(d.id)}>
                  {d.label}
                </FilterPill>
              ))}
            </div>
          </div>

          <div className="h-5 w-px bg-themed-card" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-themed-muted shrink-0">{t('dashboard.toolbar.intent_label')}</span>
            <div className="flex gap-1">
              {intents.map((i) => (
                <FilterPill key={i.id} active={(i.id === '' && !intent) || i.id === intent} onClick={() => onIntentChange(i.id)}>
                  {i.label}
                </FilterPill>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
