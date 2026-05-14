/**
 * Industries — table of live industries with per-row drill-in links.
 *
 * Moved verbatim from LandingPage.tsx (lines 1131-1257).
 */
import { Link } from 'react-router-dom';
import { Eyebrow } from '../components/Eyebrow';
import { SecondaryCTA } from '../components/SecondaryCTA';
import { track } from '../hooks/useLocale';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function Industries({ t }: SectionProps) {
  return (
    <section id="industries" style={{ backgroundColor: 'var(--color-bg-page)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 760 }}>
          <Eyebrow>{t.industries.eyebrow}</Eyebrow>
          <h2
            style={{
              marginTop: 16,
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.industries.title}
          </h2>
          <p style={{ marginTop: 12, fontSize: 16, color: 'var(--color-text-body-soft)', lineHeight: 1.55 }}>
            {t.industries.subtitle}
          </p>
        </div>

        <div className="t-card" style={{ marginTop: 28, padding: 8, overflow: 'hidden' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFeatureSettings: '"tnum"',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border-card)' }}>
                {['', t.industries.col.brand, t.industries.col.query, t.industries.col.engine, t.industries.col.status, ''].map(
                  (h, i) => (
                    <th
                      key={i}
                      style={{
                        textAlign: i === 0 || i === 5 ? 'left' : 'right',
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--color-text-body-soft)',
                        padding: '14px 16px',
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {t.industries.table.map((row, i) => (
                <tr
                  key={row.slug}
                  style={{
                    borderBottom:
                      i === t.industries.table.length - 1 ? 'none' : '1px solid var(--color-border-card)',
                  }}
                >
                  <td
                    style={{
                      padding: '18px 16px',
                      fontSize: 15,
                      fontWeight: 600,
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {row.name}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.brands}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.queries}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.engines}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right' }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--color-success, #16A34A)',
                        backgroundColor: 'rgba(22, 163, 74, 0.10)',
                        padding: '3px 8px',
                        borderRadius: '999px',
                      }}
                    >
                      ● {row.status}
                    </span>
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right' }}>
                    <Link
                      to={`/industry?category=${row.slug}&from=landing_industries_row`}
                      onClick={() =>
                        track('landing_cta_click', { cta: 'industries_row', from: 'industries_row', category: row.slug })
                      }
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--color-accent)',
                        textDecoration: 'none',
                      }}
                    >
                      {t.industries.view}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center' }}>
          <SecondaryCTA to="/industry" from="industries_browse_all">
            {t.industries.browse_all}
          </SecondaryCTA>
        </div>
      </div>
    </section>
  );
}
