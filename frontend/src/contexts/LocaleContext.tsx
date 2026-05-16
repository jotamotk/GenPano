/*
 * LocaleContext — GENPANO 前端 i18n 底座
 * ─────────────────────────────────────────────────
 * 目标: 给 React (非-Next) 环境提供和 next-intl 对齐的 API
 *       (t / formatDate / formatNumber / formatBrand),
 *       让页面代码在正式迁移到 Next.js App Router 时
 *       只需换 import 路径, 不需要重写.
 *
 * 对应 PRD 4.10.4:
 *   - 默认 zh-CN, 英文用户手动切换
 *   - 用户 locale 偏好持久化 (localStorage, 对应 User.locale)
 *   - 数字/日期通过 Intl.* 按 locale 格式化
 *   - 品牌名按 locale 返回 nameZh / nameEn, 回退 primaryName
 *   - 专有名词 (PANO Score / GEO / Topic / SoV) 保持原文, 在字典里就是这么写的
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { MESSAGES, formatMessage, resolveKey } from '../i18n/messages';

const DEFAULT_LOCALE = 'zh-CN';
const SUPPORTED = ['zh-CN', 'en-US'];
const STORAGE_KEY = 'genpano.locale';

const LocaleContext = createContext({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
  t: (key, params) => key,
  formatDate: (d) => String(d),
  formatDateRange: () => '',
  formatNumber: (n) => String(n),
  formatBrand: (b) => (b && (b.primaryName || b.nameZh || b.nameEn || '')) || '',
  formatProfileGroup: (g) => (g && (g.nameZh || g.nameEn || g.id || '')) || '',
});

function detectBrowserLocale() {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;
  const raw = (navigator.language || navigator.userLanguage || DEFAULT_LOCALE).toLowerCase();
  if (raw.startsWith('zh')) return 'zh-CN';
  if (raw.startsWith('en')) return 'en-US';
  return DEFAULT_LOCALE;
}

function readStoredLocale() {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage?.getItem(STORAGE_KEY);
    return SUPPORTED.includes(v) ? v : null;
  } catch {
    return null;
  }
}

export function LocaleProvider({ children, initialLocale }) {
  const [locale, setLocaleState] = useState(() =>
    initialLocale || readStoredLocale() || detectBrowserLocale()
  );

  useEffect(() => {
    try {
      window.localStorage?.setItem(STORAGE_KEY, locale);
    } catch {
      /* ignore storage errors (private mode, etc.) */
    }
    if (typeof document !== 'undefined') {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  const setLocale = useCallback((next) => {
    if (!SUPPORTED.includes(next)) return;
    setLocaleState(next);
  }, []);

  const dict = MESSAGES[locale] || MESSAGES[DEFAULT_LOCALE];

  const t = useCallback(
    (key, params) => {
      const template = resolveKey(dict, key);
      if (typeof template !== 'string') {
        // Fallback to default locale, then the raw key as a last resort.
        const fallback = resolveKey(MESSAGES[DEFAULT_LOCALE], key);
        if (typeof fallback !== 'string') return key;
        return formatMessage(fallback, params);
      }
      return formatMessage(template, params);
    },
    [dict]
  );

  const formatDate = useCallback(
    (input, options) => {
      if (!input) return '';
      const d = input instanceof Date ? input : new Date(input);
      if (Number.isNaN(d.getTime())) return String(input);
      return new Intl.DateTimeFormat(locale, options || { year: 'numeric', month: 'short', day: 'numeric' }).format(d);
    },
    [locale]
  );

  const formatDateRange = useCallback(
    (start, end) => {
      if (!start || !end) return '';
      const s = start instanceof Date ? start : new Date(start);
      const e = end instanceof Date ? end : new Date(end);
      if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return `${start} ~ ${end}`;
      const fmt = new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'short', day: 'numeric' });
      return `${fmt.format(s)} — ${fmt.format(e)}`;
    },
    [locale]
  );

  const formatNumber = useCallback(
    (value, options) => {
      if (value === undefined || value === null) return '';
      return new Intl.NumberFormat(locale, options).format(value);
    },
    [locale]
  );

  /**
   * Locale-aware brand name resolver.
   * Brand shape matches PRD 4.10.2: { primaryName, nameZh, nameEn, aliases? }.
   * Also accepts plain strings for backward compatibility with legacy mock data.
   */
  const formatBrand = useCallback(
    (brand) => {
      if (!brand) return '';
      if (typeof brand === 'string') return brand;
      if (locale === 'zh-CN') {
        return brand.nameZh || brand.primaryName || brand.nameEn || '';
      }
      return brand.nameEn || brand.primaryName || brand.nameZh || '';
    },
    [locale]
  );

  /**
   * Locale-aware Profile Group name resolver — PRD §4.2.3a / §4.6.1a.
   * Single entry point: never read `group.name` directly in components, always
   * call `formatProfileGroup(group)` so locale switching works uniformly.
   *
   * Accepts:
   *   - { id, nameZh, nameEn } (canonical PROFILE_GROUPS shape)
   *   - string id (will look up the dictionary in i18n's `profile_groups.<id>`)
   */
  const formatProfileGroup = useCallback(
    (group) => {
      if (!group) return '';
      if (typeof group === 'string') {
        const fromDict = resolveKey(dict, `profile_groups.${group}`);
        if (typeof fromDict === 'string') return fromDict;
        return group; // fall back to id
      }
      if (locale === 'zh-CN') {
        return group.nameZh || group.nameEn || group.id || '';
      }
      return group.nameEn || group.nameZh || group.id || '';
    },
    [locale, dict]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, formatDate, formatDateRange, formatNumber, formatBrand, formatProfileGroup }),
    [locale, setLocale, t, formatDate, formatDateRange, formatNumber, formatBrand, formatProfileGroup]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  return useContext(LocaleContext);
}
