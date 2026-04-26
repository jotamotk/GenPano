/*
 * useBrandAnalysisFilters — PRD §4.6-IA-v2.K (2026-04-20, Session T6')
 * ────────────────────────────────────────────────────────────────────
 * Central URL-state bridge for Brand Mode deep-analysis pages.
 *
 * Fields (all URL-driven, no localStorage):
 *   - from         YYYY-MM-DD (default: 7d ago)
 *   - to           YYYY-MM-DD (default: today)
 *   - engines      comma-joined engine ids ('chatgpt,doubao,deepseek'); empty = all
 *   - profileGroup single id; empty/'all' = all
 *   - dimensions   comma-joined Topic dimensions ('品类,品牌,产品,关系'); empty = all
 *   - intents      comma-joined Intents ('informational,commercial,transactional,navigational'); empty = all
 *
 * Consumers: Brand Mode sub-views (Overview/Visibility/Topics/Sentiment/
 * Citations/Products/Competitors). Cross-view state persists via URL so
 * switching sidebar items keeps the filter applied.
 *
 * Harness C10-1/C10-2 (DESIGN_TOKENS.md) enforce import presence +
 * forbid local useState for time ranges.
 */
import { useSearchParams } from 'react-router-dom';

const QK = {
  from: 'from',
  to: 'to',
  engines: 'engines',
  profileGroup: 'profileGroup',
  dimensions: 'dimensions',
  intents: 'intents',
};

function readCsv(sp, key) {
  const v = sp.get(key);
  return v ? v.split(',').filter(Boolean) : [];
}

function writeCsv(nextSp, key, arr) {
  if (!arr || arr.length === 0) {
    nextSp.delete(key);
  } else {
    nextSp.set(key, arr.join(','));
  }
}

function defaultFrom(days = 7) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function defaultTo() {
  return new Date().toISOString().slice(0, 10);
}

export function useBrandAnalysisFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = {
    from: searchParams.get(QK.from) || defaultFrom(7),
    to: searchParams.get(QK.to) || defaultTo(),
    engines: readCsv(searchParams, QK.engines),
    profileGroup: searchParams.get(QK.profileGroup) || 'all',
    dimensions: readCsv(searchParams, QK.dimensions),
    intents: readCsv(searchParams, QK.intents),
  };

  const isDefault =
    !searchParams.get(QK.from) &&
    !searchParams.get(QK.to) &&
    filters.engines.length === 0 &&
    (filters.profileGroup === 'all' || !searchParams.get(QK.profileGroup)) &&
    filters.dimensions.length === 0 &&
    filters.intents.length === 0;

  const extendedActiveCount =
    (filters.dimensions.length > 0 ? 1 : 0) + (filters.intents.length > 0 ? 1 : 0);

  function setFilter(key, value) {
    const next = new URLSearchParams(searchParams);
    if (key === 'engines' || key === 'dimensions' || key === 'intents') {
      writeCsv(next, QK[key], value);
    } else if (key === 'profileGroup') {
      if (!value || value === 'all') next.delete(QK.profileGroup);
      else next.set(QK.profileGroup, value);
    } else if (key === 'from' || key === 'to') {
      if (!value) next.delete(QK[key]);
      else next.set(QK[key], value);
    }
    setSearchParams(next, { replace: false });
  }

  function setRange(preset) {
    // preset: '7d' | '14d' | '30d' | '90d'
    const days = { '7d': 7, '14d': 14, '30d': 30, '90d': 90 }[preset] || 7;
    const next = new URLSearchParams(searchParams);
    next.set(QK.from, defaultFrom(days));
    next.set(QK.to, defaultTo());
    setSearchParams(next, { replace: false });
  }

  function resetFilters() {
    const next = new URLSearchParams(searchParams);
    Object.values(QK).forEach((k) => next.delete(k));
    setSearchParams(next, { replace: false });
  }

  return {
    filters,
    isDefault,
    extendedActiveCount,
    setFilter,
    setRange,
    resetFilters,
  };
}
