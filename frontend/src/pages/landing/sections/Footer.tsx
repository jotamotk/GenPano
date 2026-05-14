/**
 * Footer — site footer with logo, tagline, three link columns and copyright bar.
 *
 * Moved verbatim from LandingPage.tsx (lines 1491-1539).
 */
import { Link } from 'react-router-dom';
import { Globe } from 'lucide-react';
import { FooterCol } from '../components/FooterCol';
import { LogoMark } from '../components/LogoMark';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function Footer({ t }: SectionProps) {
  return (
    <footer
      style={{
        backgroundColor: 'var(--color-bg-card)',
        borderTop: '1px solid var(--color-border-card)',
        paddingTop: 56,
        paddingBottom: 40,
      }}
    >
      <div className={MAX_W}>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          <div>
            <Link to="/" className="flex items-center gap-2" style={{ textDecoration: 'none' }}>
              <LogoMark size={28} />
              <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}>
                GENPANO
              </span>
            </Link>
            <p style={{ marginTop: 14, fontSize: 13, lineHeight: 1.55, color: 'var(--color-text-body-soft)' }}>
              {t.footer.tagline}
            </p>
          </div>

          <FooterCol title={t.footer.col_product} links={t.footer.links.product} />
          <FooterCol title={t.footer.col_resources} links={t.footer.links.resources} />
          <FooterCol title={t.footer.col_company} links={t.footer.links.company} />
        </div>

        <div
          className="flex items-center justify-between flex-wrap gap-4"
          style={{
            marginTop: 40,
            paddingTop: 24,
            borderTop: '1px solid var(--color-border-card)',
            fontSize: 13,
            color: 'var(--color-text-body-soft)',
          }}
        >
          <span>{t.footer.copyright}</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Globe size={13} strokeWidth={2} />
            {t.footer.lang_label}
          </span>
        </div>
      </div>
    </footer>
  );
}
