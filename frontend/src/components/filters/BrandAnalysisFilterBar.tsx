/*
 * BrandAnalysisFilterBar — PRD §4.6-IA-v2.K (2026-04-20, Session T6')
 * ────────────────────────────────────────────────────────────────────
 * Shared filter bar for Brand Mode deep-analysis pages (Visibility /
 * Topics / Sentiment / Citations / Products / Competitors). State
 * lives in URL (via useBrandAnalysisFilters hook) so it persists
 * across sidebar sub-view switches.
 *
 * Layout:
 *   主行 (始终可见):  [时间段] [引擎多选] [画像下拉] [更多筛选 ▾]  [重置]
 *   扩展行 (展开后):  [维度多选] [Intent 多选]
 *
 * Harness C10-1 requires every Brand Mode analysis page to import
 * this component or the hook directly.
 */
import React, { useState } from 'react';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';
import ProfileGroupFilter from './ProfileGroupFilter';
import { useLocale } from '../../contexts/LocaleContext';

const RANGE_PRESETS = [
  { id: '7d',  labelKey: 'filters.range.7d',  fallback: '近 7 天' },
  { id: '14d', labelKey: 'filters.range.14d', fallback: '近 14 天' },
  { id: '30d', labelKey: 'filters.range.30d', fallback: '近 30 天' },
  { id: '90d', labelKey: 'filters.range.90d', fallback: '近 90 天' },
];

const ENGINE_OPTIONS = [
  { id: 'chatgpt',  label: 'ChatGPT',  color: 'var(--color-engine-chatgpt)' },
  { id: 'doubao',   label: '豆包',      color: 'var(--color-engine-doubao)' },
  { id: 'deepseek', label: 'DeepSeek', color: 'var(--color-engine-deepseek)' },
];

const DIMENSION_OPTIONS = [
  { id: '品类', label: '品类' },
  { id: '品牌', label: '品牌' },
  { id: '产品', label: '产品' },
  { id: '关系', label: '关系' },
];

const INTENT_OPTIONS = [
  { id: 'informational',  label: 'Info' },
  { id: 'commercial',     label: 'Comm' },
  { id: 'transactional',  label: 'Txn' },
  { id: 'navigational',   label: 'Nav' },
];

const PROMPT_SCOPE_OPTIONS = [
  { id: 'non_branded', label: 'Non-brand' },
  { id: 'branded',     label: 'Branded' },
  { id: 'competitive', label: 'Competitive' },
];

function Chip({ active, onClick, children, ariaPressed }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ariaPressed ?? active}
      className="px-2.5 py-1 rounded-pill text-[11px] font-medium transition-colors"
      style={{
        background: active ? 'var(--color-accent-bg-light)' : 'var(--color-bg-card)',
        color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
        border: `1px solid ${active ? 'var(--color-accent-alpha-27)' : 'var(--color-border-subtle)'}`,
      }}
    >
      {children}
    </button>
  );
}

function RangeGroup() {
  const { filters, setRange } = useBrandAnalysisFilters();
  // Detect which preset is active by span days
  const activePreset = React.useMemo(() => {
    if (!filters.from || !filters.to) return '7d';
    const msPerDay = 86400000;
    const days = Math.round(
      (new Date(filters.to).getTime() - new Date(filters.from).getTime()) / msPerDay,
    );
    const match = RANGE_PRESETS.find((p) => Number(p.id.replace('d', '')) === days);
    return match ? match.id : '7d';
  }, [filters.from, filters.to]);

  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">时间</span>
      <div className="inline-flex rounded-pill overflow-hidden" style={{ border: '1px solid var(--color-border-subtle)' }}>
        {RANGE_PRESETS.map((p) => {
          const active = activePreset === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => setRange(p.id)}
              className="px-2.5 py-1 text-[11px] font-medium transition-colors"
              style={{
                background: active ? 'var(--color-accent-bg-light)' : 'transparent',
                color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
            >
              {p.fallback}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EngineGroup() {
  const { filters, setFilter } = useBrandAnalysisFilters();
  const selected = new Set(filters.engines);
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setFilter('engines', Array.from(next));
  };
  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">引擎</span>
      {ENGINE_OPTIONS.map((e) => (
        <Chip key={e.id} active={selected.has(e.id)} onClick={() => toggle(e.id)}>
          <span className="inline-flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: e.color }} />
            {e.label}
          </span>
        </Chip>
      ))}
    </div>
  );
}

function DimensionGroup() {
  const { filters, setFilter } = useBrandAnalysisFilters();
  const selected = new Set(filters.dimensions);
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setFilter('dimensions', Array.from(next));
  };
  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">维度</span>
      {DIMENSION_OPTIONS.map((d) => (
        <Chip key={d.id} active={selected.has(d.id)} onClick={() => toggle(d.id)}>
          {d.label}
        </Chip>
      ))}
    </div>
  );
}

function IntentGroup() {
  const { filters, setFilter } = useBrandAnalysisFilters();
  const selected = new Set(filters.intents);
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setFilter('intents', Array.from(next));
  };
  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">意图</span>
      {INTENT_OPTIONS.map((i) => (
        <Chip key={i.id} active={selected.has(i.id)} onClick={() => toggle(i.id)}>
          {i.label}
        </Chip>
      ))}
    </div>
  );
}

function PromptScopeGroup() {
  const { filters, setFilter } = useBrandAnalysisFilters();
  const active = filters.promptScope || '';
  const toggle = (id) => {
    setFilter('promptScope', active === id ? '' : id);
  };
  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">归类</span>
      {PROMPT_SCOPE_OPTIONS.map((opt) => (
        <Chip key={opt.id} active={active === opt.id} onClick={() => toggle(opt.id)}>
          {opt.label}
        </Chip>
      ))}
    </div>
  );
}

export default function BrandAnalysisFilterBar({ sticky = true, className = '' }) {
  const [expanded, setExpanded] = useState(false);
  const { extendedActiveCount, isDefault, resetFilters } = useBrandAnalysisFilters();

  return (
    <div
      className={`${className}`}
      style={
        sticky
          ? {
              position: 'sticky',
              top: 0,
              zIndex: 10,
              background: 'var(--color-bg)',
              paddingTop: 4,
              paddingBottom: 4,
            }
          : {}
      }
    >
      <div
        className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 rounded-card"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        <RangeGroup />
        <span className="w-px h-5" style={{ background: 'var(--color-border-subtle)' }} />
        <EngineGroup />
        <span className="w-px h-5" style={{ background: 'var(--color-border-subtle)' }} />
        <ProfileGroupFilter />
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-pill text-[11px] font-medium transition-colors"
          style={{
            background: extendedActiveCount > 0 ? 'var(--color-accent-bg-light)' : 'var(--color-bg-card)',
            color: extendedActiveCount > 0 ? 'var(--color-accent)' : 'var(--color-text-muted)',
            border: `1px solid ${extendedActiveCount > 0 ? 'var(--color-accent-alpha-27)' : 'var(--color-border-subtle)'}`,
          }}
        >
          更多筛选
          {extendedActiveCount > 0 && (
            <span
              className="ml-1 px-1.5 rounded-pill text-[9px]"
              style={{ background: 'var(--color-accent)', color: '#fff' }}
            >
              {extendedActiveCount}
            </span>
          )}
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        {!isDefault && (
          <button
            type="button"
            onClick={resetFilters}
            className="text-[11px] text-themed-muted hover:text-themed-primary transition-colors"
          >
            重置
          </button>
        )}
      </div>
      {expanded && (
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 mt-1.5 rounded-card"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
          }}
        >
          <DimensionGroup />
          <span className="w-px h-5" style={{ background: 'var(--color-border-subtle)' }} />
          <IntentGroup />
          <span className="w-px h-5" style={{ background: 'var(--color-border-subtle)' }} />
          <PromptScopeGroup />
        </div>
      )}
    </div>
  );
}
