/**
 * Problem — "classic SEO is dead in AI" two-card section.
 *
 * Moved verbatim from LandingPage.tsx (lines 848-893).
 */
import { Check, X } from 'lucide-react';
import { ComparisonCard } from '../components/ComparisonCard';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function Problem({ t }: SectionProps) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <h2
            style={{
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.problem.title}
          </h2>
          <p
            style={{
              marginTop: 16,
              fontSize: 17,
              lineHeight: 1.6,
              color: 'var(--color-text-body-soft)',
            }}
          >
            {t.problem.subtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" style={{ marginTop: 40 }}>
          <ComparisonCard
            tone="muted"
            icon={<X size={18} strokeWidth={2} />}
            title={t.problem.left_title}
            items={t.problem.left_items}
          />
          <ComparisonCard
            tone="accent"
            icon={<Check size={18} strokeWidth={2} />}
            title={t.problem.right_title}
            items={t.problem.right_items}
          />
        </div>
      </div>
    </section>
  );
}
