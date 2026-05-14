/* ─── format helpers ─── */
export type TFunction = (key: string, vars?: Record<string, unknown>) => string;

export function asMetricNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

export function formatMaybePercent(value: number | null | undefined): string {
  return value == null ? '—' : `${value}%`;
}

export function formatMaybeRank(value: number | null | undefined, t: TFunction): string {
  return value == null ? '—' : t('dashboard.ranking_format', { rank: value });
}

export function metricWidth(value: unknown): number {
  const next = asMetricNumber(value);
  return next == null ? 0 : Math.max(0, Math.min(100, next));
}

export function getPanoGrade(score: number, t: TFunction): { label: string; color: string } {
  if (score >= 80) return { label: t('dashboard.hero.grade_excellent'), color: 'var(--color-success)' };
  if (score >= 65) return { label: t('dashboard.hero.grade_good'),      color: 'var(--color-chart-7)' };
  if (score >= 50) return { label: t('dashboard.hero.grade_medium'),    color: 'var(--color-chart-3)' };
  if (score >= 35) return { label: t('dashboard.hero.grade_pass'),      color: 'var(--color-warning)' };
  return { label: t('dashboard.hero.grade_attention'), color: 'var(--color-danger)' };
}
