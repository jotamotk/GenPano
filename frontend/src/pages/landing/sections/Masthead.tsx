/**
 * Masthead — sticky top nav with logo, links, locale toggle, login & register.
 *
 * Moved verbatim from LandingPage.tsx (lines 512-612).
 */
import { Link } from 'react-router-dom';
import { Globe, Sparkles } from 'lucide-react';
import LandingNavQuickCreateButton from '../../../components/landing/LandingNavQuickCreateButton';
import { LogoMark } from '../components/LogoMark';
import { track, type Locale } from '../hooks/useLocale';
import { MAX_W } from '../layout';
import type { CopyBag } from '../types';

interface MastheadProps {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: CopyBag;
}

export function Masthead({ locale, setLocale, t }: MastheadProps) {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        backgroundColor: 'rgba(255,255,255,0.85)',
        backdropFilter: 'saturate(180%) blur(8px)',
        borderBottom: '1px solid var(--color-border-card)',
      }}
    >
      <div className={`${MAX_W} flex items-center justify-between`} style={{ height: 64 }}>
        <Link to="/" className="flex items-center gap-2" aria-label="GENPANO home">
          <LogoMark size={28} />
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}>
            GENPANO
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-7">
          {[
            { label: t.nav.product, href: '#product' },
            { label: t.nav.method, href: '#method' },
            { label: t.nav.industries, href: '#industries' },
            { label: t.nav.agents, href: '#agents' },
          ].map((l) => (
            <a
              key={l.href}
              href={l.href}
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--color-text-body-soft)',
                textDecoration: 'none',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-text-primary)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-body-soft)')}
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              const next = locale === 'zh-CN' ? 'en-US' : 'zh-CN';
              setLocale(next);
              track('landing_locale_switch', { from: locale, to: next });
            }}
            className="inline-flex items-center gap-1.5"
            style={{
              height: 32,
              padding: '0 10px',
              borderRadius: 'var(--radius-btn)',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--color-text-body-soft)',
              backgroundColor: 'transparent',
              border: '1px solid var(--color-border-card)',
              cursor: 'pointer',
            }}
            aria-label="Toggle language"
          >
            <Globe size={12} strokeWidth={2} />
            {locale === 'zh-CN' ? 'EN' : '中文'}
          </button>

          {/* PRD §4.1.1d E3 — Landing nav quick-create button.
              Three auth/project states live inside the component; it is intentionally
              low-contrast so it never out-weighs the hero CTA. */}
          <LandingNavQuickCreateButton />

          <Link
            to="/login?from=landing_nav"
            onClick={() => track('landing_cta_click', { cta: 'tertiary', from: 'nav' })}
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: 'var(--color-text-body-soft)',
              textDecoration: 'none',
            }}
          >
            {t.nav.login}
          </Link>
          <Link
            to="/register?from=landing_nav"
            onClick={() => track('landing_cta_click', { cta: 'primary', from: 'nav' })}
            className="t-btn-primary inline-flex items-center gap-2"
            style={{ paddingLeft: 16, paddingRight: 16, height: 36, fontSize: 13 }}
          >
            <Sparkles size={14} strokeWidth={2} />
            {t.nav.register}
          </Link>
        </div>
      </div>
    </header>
  );
}
