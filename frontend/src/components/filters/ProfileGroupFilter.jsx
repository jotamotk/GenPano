/*
 * ProfileGroupFilter — PRD §4.2.3a / §4.6.1a (Dashboard) / §4.6.1b (BrandDetail) / §4.2.5 (Topics)
 * ────────────────────────────────────────────────────────────────────────────
 * Single-select audience filter wired to URL `?profileGroup=<id>`.
 *
 * Wired into:
 *   - DashboardPage toolbar
 *   - BrandDetailPage toolbar (overview / diagnostics / engines tabs)
 *   - TopicsPage filter row
 *
 * NOT wired into:
 *   - BrandProductDetailPage (product-level samples are too sparse — PRD §4.6.1d)
 *
 * API surface deliberately kept minimal so it can be swapped to
 * `@radix-ui/react-select` in production without touching the call sites
 * (Production build uses Radix Select; in this
 * prototype we mirror the same pattern as <ProjectSelector> with a custom
 * accessible button + panel).
 *
 * Companion: <ProfileGroupSampleWarning> renders the yellow degradation
 * banner when sampleCount < threshold, per PRD §4.2.3a "聚合语义".
 */
import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  PROFILE_GROUPS,
  PROFILE_GROUP_SAMPLE_THRESHOLD,
  getProfileGroupSampleCount,
  hasEnoughSamplesInGroup,
} from '../../data/mock';
import { useLocale } from '../../contexts/LocaleContext';

const QUERY_KEY = 'profileGroup';
const DEFAULT_GROUP_ID = 'all';

/* ──────────────────────────────────────────────────────────────
   Hook: useProfileGroupFilter
   Centralizes the URL ↔ state bridge so consumers don't repeat
   useSearchParams plumbing. Returns the active group object,
   sample status, and a setter that updates the URL.
─────────────────────────────────────────────────────────────── */
export function useProfileGroupFilter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const id = searchParams.get(QUERY_KEY) || DEFAULT_GROUP_ID;
  const group = PROFILE_GROUPS.find((g) => g.id === id) || PROFILE_GROUPS[0];

  const setGroupId = (nextId) => {
    const next = new URLSearchParams(searchParams);
    if (!nextId || nextId === DEFAULT_GROUP_ID) {
      next.delete(QUERY_KEY);
    } else {
      next.set(QUERY_KEY, nextId);
    }
    setSearchParams(next, { replace: false });
  };

  const sampleCount = getProfileGroupSampleCount(group.id);
  const sufficient = hasEnoughSamplesInGroup(group.id);

  return {
    group,
    groupId: group.id,
    setGroupId,
    sampleCount,
    sufficient,
    threshold: PROFILE_GROUP_SAMPLE_THRESHOLD,
    isDefault: group.id === DEFAULT_GROUP_ID,
  };
}

/* ──────────────────────────────────────────────────────────────
   <ProfileGroupFilter> — the dropdown trigger + panel
─────────────────────────────────────────────────────────────── */
export default function ProfileGroupFilter({ className = '' }) {
  const { t, formatProfileGroup, locale } = useLocale();
  const { group, setGroupId } = useProfileGroupFilter();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  // click-outside to close — mirrors ProjectSelector pattern
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const isDefault = group.id === DEFAULT_GROUP_ID;
  const displayName = formatProfileGroup(group);

  return (
    <div ref={containerRef} className={`relative inline-flex items-center gap-2 ${className}`}>
      <span className="text-xs text-themed-muted shrink-0">{t('filters.profile_group.label')}</span>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={t('filters.profile_group.tooltip_help')}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-xs font-medium transition-colors"
        style={{
          background: isDefault ? 'var(--color-bg-card)' : 'var(--color-accent-bg-light)',
          border: `1px solid ${isDefault ? 'var(--color-border-subtle)' : 'var(--color-accent-alpha-27)'}`,
          color: isDefault ? 'var(--color-text-muted)' : 'var(--color-accent)',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21v-1a8 8 0 0 1 16 0v1" />
        </svg>
        <span>{displayName}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Selected (non-default) tag with × clear */}
      {!isDefault && (
        <span
          className="inline-flex items-center gap-1 px-2 py-1 rounded-pill text-[10px] font-medium"
          style={{
            background: 'var(--color-accent-bg-light)',
            color: 'var(--color-accent)',
            border: '1px solid var(--color-accent-alpha-27)',
          }}
        >
          {t('filters.profile_group.tag_prefix')}: {displayName}
          <button
            type="button"
            onClick={() => setGroupId(DEFAULT_GROUP_ID)}
            aria-label={t('filters.profile_group.clear')}
            className="ml-0.5 hover:opacity-70 transition-opacity"
          >
            ×
          </button>
        </span>
      )}

      {open && (
        <div
          role="listbox"
          aria-label={t('filters.profile_group.label')}
          className="absolute left-0 top-full mt-1.5 z-50 w-64 rounded-card overflow-hidden"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            boxShadow: 'var(--shadow-card-hover)',
          }}
        >
          <div className="max-h-72 overflow-y-auto py-1">
            {PROFILE_GROUPS.map((g) => {
              const isSelected = g.id === group.id;
              const enough = hasEnoughSamplesInGroup(g.id);
              const desc = locale === 'zh-CN' ? g.description : g.descriptionEn;
              return (
                <button
                  key={g.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => { setGroupId(g.id); setOpen(false); }}
                  className="w-full flex items-start gap-2 px-3 py-2 text-left transition-colors"
                  style={{
                    background: isSelected ? 'var(--color-accent-bg-light)' : 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.background = 'var(--color-bg-subtle)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="text-xs font-medium truncate"
                        style={{ color: isSelected ? 'var(--color-accent)' : 'var(--color-text-primary)' }}
                      >
                        {formatProfileGroup(g)}
                      </span>
                      {!enough && (
                        <span
                          className="text-[9px] px-1.5 py-0.5 rounded-pill"
                          style={{
                            background: 'var(--color-warning-bg, rgba(245, 158, 11, 0.12))',
                            color: 'var(--color-warning, #d97706)',
                          }}
                          title={`${g.sampleCount} < ${PROFILE_GROUP_SAMPLE_THRESHOLD}`}
                        >
                          n={g.sampleCount}
                        </span>
                      )}
                    </div>
                    {desc && (
                      <div className="text-[10px] text-themed-muted mt-0.5 line-clamp-1">{desc}</div>
                    )}
                  </div>
                  {isSelected && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
   <ProfileGroupSampleWarning>
   Yellow degradation banner — render at the top of any page section
   that depends on the active profile group when it's below threshold.
   PRD §4.2.3a "聚合语义" — never silently fall back to all-profile data.
─────────────────────────────────────────────────────────────── */
export function ProfileGroupSampleWarning() {
  const { t, formatProfileGroup } = useLocale();
  const { group, sampleCount, sufficient, threshold, setGroupId, isDefault } = useProfileGroupFilter();

  if (isDefault || sufficient) return null;

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 px-3 py-2 rounded-card mb-3"
      style={{
        background: 'var(--color-warning-bg, rgba(245, 158, 11, 0.10))',
        border: '1px solid var(--color-warning-border, rgba(245, 158, 11, 0.35))',
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning, #d97706)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <div className="flex-1 min-w-0">
        <div className="text-xs leading-snug" style={{ color: 'var(--color-warning, #d97706)' }}>
          {t('filters.profile_group.insufficient_sample', { count: sampleCount, threshold })}
        </div>
        <div className="mt-1.5 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setGroupId(DEFAULT_GROUP_ID)}
            className="text-[11px] font-medium underline hover:opacity-80"
            style={{ color: 'var(--color-warning, #d97706)' }}
          >
            {t('filters.profile_group.switch_group')}
          </button>
          <span className="text-[11px] text-themed-muted">
            ({t('filters.profile_group.tag_prefix')}: {formatProfileGroup(group)})
          </span>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
   <ProfileGroupTag> — small "画像: {name}" pill for chart subtitles
   per PRD §4.6.1a "聚合语义" final bullet.
─────────────────────────────────────────────────────────────── */
export function ProfileGroupTag() {
  const { t, formatProfileGroup } = useLocale();
  const { group, isDefault } = useProfileGroupFilter();
  if (isDefault) return null;
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded-pill text-[10px] font-medium"
      style={{
        background: 'var(--color-accent-bg-light)',
        color: 'var(--color-accent)',
        border: '1px solid var(--color-accent-alpha-27)',
      }}
    >
      {t('filters.profile_group.tag_prefix')}: {formatProfileGroup(group)}
    </span>
  );
}
