/**
 * Hero — top fold with headline, sub-copy, primary/secondary/tertiary CTAs.
 *
 * Moved verbatim from LandingPage.tsx (lines 614-719).
 */
import { Link } from 'react-router-dom';
import { Eyebrow } from '../components/Eyebrow';
import { PrimaryCTA } from '../components/PrimaryCTA';
import { SecondaryCTA } from '../components/SecondaryCTA';
import { track } from '../hooks/useLocale';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';
import { HeroVisual } from './HeroVisual';

export function Hero({ t }: SectionProps) {
  return (
    <section
      style={{
        backgroundColor: 'var(--color-bg-page)',
        paddingTop: 88,
        paddingBottom: 96,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Subtle radial glow */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: -220,
          right: -180,
          width: 620,
          height: 620,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(96, 91, 255, 0.12) 0%, transparent 60%)',
          pointerEvents: 'none',
        }}
      />

      <div className={MAX_W} style={{ position: 'relative' }}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <Eyebrow>{t.hero.eyebrow}</Eyebrow>
            <h1
              style={{
                marginTop: 20,
                fontSize: 'clamp(40px, 6vw, 68px)',
                lineHeight: 1.05,
                fontWeight: 800,
                letterSpacing: '-0.03em',
                color: 'var(--color-text-primary)',
              }}
            >
              {t.hero.h1_a}
              <br />
              <span
                style={{
                  background: 'linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                {t.hero.h1_highlight}
              </span>
              {t.hero.h1_b}
            </h1>

            <p
              style={{
                marginTop: 24,
                maxWidth: 640,
                fontSize: 18,
                lineHeight: 1.6,
                color: 'var(--color-text-body-soft)',
              }}
            >
              {t.hero.sub}
            </p>

            <div style={{ marginTop: 36 }} className="flex flex-wrap items-center gap-3">
              <PrimaryCTA to="/register" from="hero_primary">{t.hero.cta_primary}</PrimaryCTA>
              <SecondaryCTA to="/industry" from="hero_secondary">{t.hero.cta_secondary}</SecondaryCTA>
              <Link
                to="/login?from=landing_hero_tertiary"
                onClick={() => track('landing_cta_click', { cta: 'tertiary', from: 'hero' })}
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: 'var(--color-text-body-soft)',
                  textDecoration: 'none',
                  marginLeft: 4,
                }}
              >
                {t.hero.cta_tertiary} →
              </Link>
            </div>

            <p
              style={{
                marginTop: 28,
                fontSize: 13,
                fontWeight: 500,
                color: 'var(--color-text-body-soft)',
                letterSpacing: '0.01em',
              }}
            >
              {t.hero.meta}
            </p>
          </div>

          <div className="lg:col-span-5">
            <HeroVisual />
          </div>
        </div>
      </div>
    </section>
  );
}
