/**
 * ComparisonCard — used by the Problem section to contrast "classic SEO" vs
 * "AI search reality" lists.
 *
 * Moved verbatim from LandingPage.tsx (lines 895-960).
 */
import type { ReactNode } from 'react';

interface ComparisonCardProps {
  tone: 'muted' | 'accent';
  icon: ReactNode;
  title: string;
  items: readonly string[];
}

export function ComparisonCard({ tone, icon, title, items }: ComparisonCardProps) {
  const accent = tone === 'accent';
  return (
    <div
      className="t-card"
      style={{
        padding: 28,
        borderColor: accent ? 'rgba(96, 91, 255, 0.3)' : 'var(--color-border-card)',
        boxShadow: accent ? '0 8px 24px rgba(96, 91, 255, 0.08)' : 'var(--shadow-card)',
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 'var(--radius-card)',
          backgroundColor: accent ? 'rgba(96, 91, 255, 0.12)' : 'var(--color-bg-page)',
          color: accent ? 'var(--color-accent)' : 'var(--color-text-body-soft)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
        }}
      >
        {icon}
      </div>
      <h3
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: 'var(--color-text-primary)',
          marginBottom: 12,
        }}
      >
        {title}
      </h3>
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((i, idx) => (
          <li
            key={idx}
            style={{
              fontSize: 15,
              lineHeight: 1.55,
              color: accent ? 'var(--color-text-primary)' : 'var(--color-text-body-soft)',
              paddingLeft: 20,
              position: 'relative',
            }}
          >
            <span
              style={{
                position: 'absolute',
                left: 0,
                top: 9,
                width: 6,
                height: 6,
                borderRadius: 3,
                backgroundColor: accent ? 'var(--color-accent)' : 'var(--color-border-card)',
              }}
            />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}
