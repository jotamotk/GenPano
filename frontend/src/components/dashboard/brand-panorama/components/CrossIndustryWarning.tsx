import React from 'react';
import type { TFunction } from '../lib/format';

type CrossIndustryWarningProps = {
  visible: boolean;
  t: TFunction;
};

export default function CrossIndustryWarning({ visible, t }: CrossIndustryWarningProps) {
  if (!visible) return null;
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] text-themed-muted ml-2"
      title={t('brand_watch.crossindustry.card_warning_short')}
      aria-label={t('brand_watch.crossindustry.card_warning_short')}
    >
      <svg
        width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        style={{ opacity: 0.7 }}
      >
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9"  x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </span>
  );
}
