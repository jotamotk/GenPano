/**
 * PrimaryCTA — solid gradient CTA.
 *
 * Moved verbatim from LandingPage.tsx (lines 437-450).
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { track } from '../hooks/useLocale';

interface PrimaryCTAProps {
  to: string;
  from: string;
  children: ReactNode;
  icon?: boolean;
  onClick?: () => void;
}

export function PrimaryCTA({ to, from, children, icon = true, onClick }: PrimaryCTAProps) {
  const href = `${to}?from=landing_${from}`;
  return (
    <Link
      to={href}
      onClick={() => { track('landing_cta_click', { cta: 'primary', from }); onClick?.(); }}
      className="t-btn-primary inline-flex items-center justify-center gap-2"
      style={{ paddingLeft: '24px', paddingRight: '24px', height: '48px', fontWeight: 600 }}
    >
      {icon && <Sparkles size={16} strokeWidth={2} />}
      {children}
    </Link>
  );
}
