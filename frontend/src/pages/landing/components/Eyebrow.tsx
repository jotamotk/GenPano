/**
 * Eyebrow — small accent label above section titles.
 *
 * Moved verbatim from LandingPage.tsx (lines 421-435).
 */
import type { ReactNode } from 'react';

interface EyebrowProps {
  children: ReactNode;
}

export function Eyebrow({ children }: EyebrowProps) {
  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1 text-xs font-semibold uppercase tracking-wider"
      style={{
        color: 'var(--color-accent)',
        backgroundColor: 'rgba(96, 91, 255, 0.08)',
        borderRadius: '999px',
        letterSpacing: '0.08em',
      }}
    >
      {children}
    </div>
  );
}
