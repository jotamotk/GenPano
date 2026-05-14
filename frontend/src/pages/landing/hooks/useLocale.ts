/**
 * Locale hook — URL ?locale → localStorage → cookie → navigator → zh-CN
 * Contract: docs/LANDING_REDESIGN.md §7
 *
 * Moved verbatim from LandingPage.tsx (lines 365-417). Behavior preserved;
 * helpers picked up minimal types because TypeScript strict mode forbids the
 * implicit-any signatures that survived the original JS-as-TSX file.
 */
import { useCallback, useEffect, useState } from 'react';

export type Locale = 'zh-CN' | 'en-US';

declare global {
  interface Window {
    __genpano_track?: (event: string, props: Record<string, unknown>) => void;
  }
}

export function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]) : null;
}

export function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined') return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${oneYear}; Path=/; SameSite=Lax`;
}

export function detectInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'zh-CN';
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get('locale');
  if (fromUrl === 'zh-CN' || fromUrl === 'en-US') return fromUrl;
  const fromLs = window.localStorage?.getItem('genpano_locale');
  if (fromLs === 'zh-CN' || fromLs === 'en-US') return fromLs;
  const fromCookie = readCookie('genpano_locale');
  if (fromCookie === 'zh-CN' || fromCookie === 'en-US') return fromCookie;
  const nav = (navigator.language || 'zh-CN').toLowerCase();
  return nav.startsWith('zh') ? 'zh-CN' : 'en-US';
}

export function useLocale(): [Locale, (next: Locale) => void] {
  const [locale, setLocale] = useState<Locale>('zh-CN');
  useEffect(() => {
    setLocale(detectInitialLocale());
  }, []);
  const change = useCallback((next: Locale) => {
    setLocale(next);
    try {
      window.localStorage?.setItem('genpano_locale', next);
      writeCookie('genpano_locale', next);
    } catch {
      /* ignore */
    }
  }, []);
  return [locale, change];
}

/* ──────────────────────────────────────────────────────────────
   Analytics stub (landing_cta_click / landing_locale_switch)
   真实实现走 frontend/src/lib/analytics (PRD §4.11)
   ────────────────────────────────────────────────────────────── */
export function track(event: string, props: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined') return;
  if (window.__genpano_track) {
    try { window.__genpano_track(event, props); } catch { /* no-op */ }
  }
}
