import React from 'react';
import { Card } from '../../../ui';
import { asMetricNumber, getPanoGrade, TFunction } from '../lib/format';
import type { PanelBrand } from '../lib/normalize';

type HeroBlockProps = {
  primary: PanelBrand;
  industry: { name?: string } | null | undefined;
  industryAvgScore: number | null;
  t: TFunction;
  formatBrand: (brand: PanelBrand) => string;
  onScoreClick: () => void;
  onRankClick: () => void;
  isLive: boolean | undefined;
};

export default function HeroBlock({
  primary,
  industry,
  industryAvgScore,
  t,
  formatBrand,
  onScoreClick,
  onRankClick,
  isLive,
}: HeroBlockProps) {
  const panoScore = asMetricNumber(primary.panoScore);
  const rank = asMetricNumber(primary.ranking);
  const grade = panoScore == null ? null : getPanoGrade(panoScore, t);
  const delta = isLive ? null : 3.2;

  return (
    <Card className="px-5 py-4">
      <div className="min-w-0">
        <div
          data-testid="brand-hero-primary-line"
          className="flex flex-wrap items-center gap-x-3 gap-y-2 min-w-0"
        >
          <h2
            className="text-2xl font-brand font-bold text-themed-primary truncate max-w-full cursor-pointer"
            onClick={onScoreClick}
          >
            {formatBrand(primary)}
          </h2>

          <span className="text-sm text-themed-muted" aria-hidden="true">·</span>

          <button
            type="button"
            className="flex items-center gap-2 p-0 border-0 bg-transparent text-left cursor-pointer"
            onClick={onScoreClick}
          >
            <span className="text-xs font-semibold text-themed-muted">PANO</span>
            <span className="text-2xl font-brand font-bold tabular-nums text-themed-primary leading-none">
              {panoScore == null ? '-' : panoScore}
            </span>
            {grade && (
              <span
                className="text-xs font-semibold px-2 py-0.5 rounded-pill"
                style={{ background: grade.color, color: 'var(--color-text-inverse)', opacity: 0.9 }}
              >
                {grade.label}
              </span>
            )}
          </button>
        </div>

        <div
          data-testid="brand-hero-meta-line"
          className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-themed-muted"
        >
          <span>
            {t('dashboard.hero.industry_label')}: {industry?.name || '-'}
          </span>
          <button
            type="button"
            onClick={onRankClick}
            className="p-0 border-0 bg-transparent font-semibold text-themed-accent hover:underline cursor-pointer"
          >
            {rank == null ? '#-' : `#${rank}`}
          </button>
          <span aria-hidden="true">·</span>
          <span>
            {t('dashboard.hero.industry_avg')}{' '}
            <span className="tabular-nums font-medium text-themed-secondary">
              {industryAvgScore == null ? '-' : industryAvgScore}
            </span>
          </span>
          {delta != null && (
            <span className={`font-medium tabular-nums ${delta >= 0 ? 'text-themed-success' : 'text-themed-danger'}`}>
              {delta >= 0 ? '+' : ''}{delta} {t('dashboard.hero.vs_last_period')}
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}
