/**
 * Method — PANO Score formula + 5 dimension cards.
 *
 * Moved verbatim from LandingPage.tsx (lines 962-1050).
 */
import { Eyebrow } from '../components/Eyebrow';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function Method({ t }: SectionProps) {
  return (
    <section id="method" style={{ backgroundColor: 'var(--color-bg-page)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.method.eyebrow}</Eyebrow>
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
            {t.method.title}
          </h2>
          <p style={{ marginTop: 12, fontSize: 17, color: 'var(--color-text-body-soft)', lineHeight: 1.55 }}>
            {t.method.subtitle}
          </p>
        </div>

        {/* Formula card */}
        <div
          className="t-card"
          style={{ marginTop: 32, padding: 24, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: 'var(--color-text-body-soft)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            {t.method.formula_label}
          </span>
          <code
            style={{
              fontFamily: 'Nunito, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
              fontSize: 14,
              color: 'var(--color-text-primary)',
              fontWeight: 600,
              backgroundColor: 'var(--color-bg-page)',
              padding: '10px 14px',
              borderRadius: 'var(--radius-btn)',
              border: '1px solid var(--color-border-card)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {t.method.formula}
          </code>
        </div>

        {/* 5 dim cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3" style={{ marginTop: 20 }}>
          {t.method.dims.map((d, i) => (
            <div key={i} className="t-card" style={{ padding: 18 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: `var(--color-${d.tone})`,
                  marginBottom: 10,
                }}
              />
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: 'var(--color-text-primary)',
                  marginBottom: 6,
                }}
              >
                {d.k}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--color-text-body-soft)' }}>
                {d.v}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
