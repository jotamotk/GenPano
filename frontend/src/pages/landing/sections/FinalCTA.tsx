/**
 * FinalCTA — bottom banner with two CTAs over a subtle gradient.
 *
 * Moved verbatim from LandingPage.tsx (lines 1436-1489).
 */
import { PrimaryCTA } from '../components/PrimaryCTA';
import { SecondaryCTA } from '../components/SecondaryCTA';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function FinalCTA({ t }: SectionProps) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 60, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 'var(--radius-banner)',
            padding: '56px 48px',
            background:
              'linear-gradient(135deg, rgba(96,91,255,0.08) 0%, rgba(139,92,246,0.08) 100%), var(--color-bg-card)',
            border: '1px solid rgba(96, 91, 255, 0.22)',
          }}
        >
          {/* Decorative glow */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: -120,
              right: -80,
              width: 360,
              height: 360,
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(96, 91, 255, 0.18) 0%, transparent 60%)',
              pointerEvents: 'none',
            }}
          />
          <div style={{ position: 'relative', maxWidth: 720 }}>
            <h2
              style={{
                fontSize: 'clamp(28px, 3.6vw, 40px)',
                lineHeight: 1.2,
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: 'var(--color-text-primary)',
              }}
            >
              {t.final.title}
            </h2>
            <p style={{ marginTop: 14, fontSize: 17, lineHeight: 1.55, color: 'var(--color-text-body-soft)' }}>
              {t.final.subtitle}
            </p>
            <div style={{ marginTop: 28 }} className="flex flex-wrap gap-3">
              <PrimaryCTA to="/register" from="final_primary">{t.final.cta_primary}</PrimaryCTA>
              <SecondaryCTA to="/industry" from="final_secondary">{t.final.cta_secondary}</SecondaryCTA>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
