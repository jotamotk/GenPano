import React from 'react';
import { Card } from '../../../ui';
import { asMetricNumber, getPanoGrade, metricWidth, TFunction } from '../lib/format';
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
    <Card className="p-5">
      <div className="flex flex-col md:flex-row items-start md:items-center gap-5">
        <div className="flex-1 min-w-0">
          <h2
            className="text-2xl font-brand font-bold text-themed-primary truncate cursor-pointer"
            onClick={onScoreClick}
          >
            {formatBrand(primary)}
          </h2>
          <p className="text-sm text-themed-muted mt-0.5">{primary.nameEn}</p>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs text-themed-muted">
              {t('dashboard.hero.industry_label')}: {industry?.name || '—'}
            </span>
            <button
              onClick={onRankClick}
              className="text-xs font-semibold text-themed-accent hover:underline"
            >
              {rank == null ? '#—' : `#${rank}`}
            </button>
            {delta != null && <span className={`text-xs font-medium tabular-nums ${delta >= 0 ? 'text-themed-success' : 'text-themed-danger'}`}>
              {delta >= 0 ? '▲' : '▼'} {delta >= 0 ? '+' : ''}{delta} {t('dashboard.hero.vs_last_period')}
            </span>}
          </div>
        </div>

        <div className="flex items-center gap-5 shrink-0">
          <div
            className="flex flex-col items-center cursor-pointer"
            onClick={onScoreClick}
          >
            <span className="text-4xl font-brand font-bold tabular-nums text-themed-primary leading-none">
              {panoScore == null ? '—' : panoScore}
            </span>
            {grade && <span
              className="text-xs font-semibold mt-1 px-2 py-0.5 rounded-pill"
              style={{ background: grade.color, color: 'var(--color-text-inverse)', opacity: 0.9 }}
            >
              {grade.label}
            </span>}
          </div>

          <div className="flex flex-col gap-2 w-40">
            <div>
              <div className="flex justify-between text-[10px] text-themed-muted mb-0.5">
                <span>{t('dashboard.hero.industry_avg')}</span>
                <span className="tabular-nums">{industryAvgScore == null ? '—' : industryAvgScore}</span>
              </div>
              <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'var(--color-bg-subtle)' }}>
                <div
                  className="h-full rounded-pill transition-all"
                  style={{ width: `${metricWidth(industryAvgScore)}%`, background: 'var(--color-chart-line-grid)' }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-[10px] text-themed-muted mb-0.5">
                <span>{t('dashboard.hero.my_brand')}</span>
                <span className="tabular-nums font-semibold">{panoScore == null ? '—' : panoScore}</span>
              </div>
              <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'var(--color-bg-subtle)' }}>
                <div
                  className="h-full rounded-pill transition-all"
                  style={{ width: `${metricWidth(panoScore)}%`, background: 'var(--color-accent)' }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
