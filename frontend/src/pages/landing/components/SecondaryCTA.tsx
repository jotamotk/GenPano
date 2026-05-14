/**
 * SecondaryCTA — outlined CTA with arrow.
 *
 * Moved verbatim from LandingPage.tsx (lines 452-465).
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { track } from '../hooks/useLocale';

interface SecondaryCTAProps {
  to: string;
  from: string;
  children: ReactNode;
}

export function SecondaryCTA({ to, from, children }: SecondaryCTAProps) {
  const href = `${to}?from=landing_${from}`;
  return (
    <Link
      to={href}
      onClick={() => track('landing_cta_click', { cta: 'secondary', from })}
      className="t-btn-secondary inline-flex items-center justify-center gap-2"
      style={{ paddingLeft: '24px', paddingRight: '24px', height: '48px', fontWeight: 600 }}
    >
      {children}
      <ArrowRight size={16} strokeWidth={2} />
    </Link>
  );
}
