/**
 * ProductBento — 2x2 grid of product surface cards (Dashboard, Brand, Topics,
 * Knowledge Graph).
 *
 * Moved verbatim from LandingPage.tsx (lines 1052-1129).
 */
import { BarChart3, Gauge, Network, Search } from 'lucide-react';
import { Eyebrow } from '../components/Eyebrow';
import { Sparkline } from '../components/Sparkline';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function ProductBento({ t }: SectionProps) {
  const icons = [
    <Gauge size={18} strokeWidth={2} key="g" />,
    <BarChart3 size={18} strokeWidth={2} key="b" />,
    <Search size={18} strokeWidth={2} key="s" />,
    <Network size={18} strokeWidth={2} key="n" />,
  ];
  return (
    <section id="product" style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.product.eyebrow}</Eyebrow>
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
            {t.product.title}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" style={{ marginTop: 36 }}>
          {t.product.cards.map((c, i) => (
            <div key={i} className="t-card" style={{ padding: 28 }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 'var(--radius-card)',
                    backgroundColor: 'rgba(96, 91, 255, 0.10)',
                    color: 'var(--color-accent)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {icons[i]}
                </div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: 'var(--color-text-body-soft)',
                    backgroundColor: 'var(--color-bg-page)',
                    padding: '4px 10px',
                    borderRadius: '999px',
                    letterSpacing: '0.04em',
                  }}
                >
                  {c.badge}
                </span>
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 10 }}>
                {c.title}
              </h3>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--color-text-body-soft)' }}>{c.desc}</p>

              <div style={{ marginTop: 18 }}>
                <Sparkline
                  points={[30, 42, 38, 54, 48, 62, 60, 72, 68, 80]}
                  strokeVar={`--color-chart-${(i % 5) + 1}`}
                  width={260}
                  height={34}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
