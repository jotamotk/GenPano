/**
 * Voices — early-user testimonial cards.
 *
 * Moved verbatim from LandingPage.tsx (lines 1259-1313).
 */
import { Eyebrow } from '../components/Eyebrow';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function Voices({ t }: SectionProps) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.voices.eyebrow}</Eyebrow>
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
            {t.voices.title}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4" style={{ marginTop: 32 }}>
          {t.voices.items.map((v, i) => (
            <div key={i} className="t-card" style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 20 }}>
              <p
                style={{
                  fontSize: 15,
                  lineHeight: 1.65,
                  color: 'var(--color-text-primary)',
                  fontWeight: 500,
                }}
              >
                “{v.quote}”
              </p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 13, color: 'var(--color-text-body-soft)' }}>{v.who}</div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: 'var(--color-accent)',
                    backgroundColor: 'rgba(96, 91, 255, 0.10)',
                    padding: '3px 10px',
                    borderRadius: '999px',
                  }}
                >
                  {v.brand}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
