import { PANEL_FALLBACK_BRAND } from './constants';

export type PanelBrand = {
  id: string;
  name: string;
  nameZh: string;
  nameEn: string;
  primaryName: string;
  industryId: string;
  panoScore: number | null;
  mentionRate: number | null;
  sentiment: number | null;
  sov?: number | null;
  ranking: number | null;
  [key: string]: unknown;
};

export function finiteNumber(value: unknown, fallback = 0): number {
  if (value === null || value === undefined || value === '') return fallback;
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

export function finiteMetric(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

export function normalizePanelBrand(
  brand: Record<string, unknown> | null | undefined,
  fallback: Record<string, unknown> | null | undefined = PANEL_FALLBACK_BRAND,
): PanelBrand {
  const brandFields = (brand || {}) as Record<string, unknown>;
  const fallbackFields = (fallback || {}) as Record<string, unknown>;
  const merged = {
    ...PANEL_FALLBACK_BRAND,
    ...fallbackFields,
    ...brandFields,
  } as Record<string, unknown>;
  const displayName =
    (brandFields.nameZh as string | undefined) ||
    (brandFields.primaryName as string | undefined) ||
    (brandFields.name as string | undefined) ||
    (brandFields.nameEn as string | undefined) ||
    (fallbackFields.nameZh as string | undefined) ||
    (fallbackFields.primaryName as string | undefined) ||
    (fallbackFields.name as string | undefined) ||
    (fallbackFields.nameEn as string | undefined) ||
    'Brand';

  const rankingRaw = finiteMetric(merged.ranking);

  return {
    ...merged,
    id: String(merged.id || displayName),
    name: (brandFields.name as string) || displayName,
    nameZh: (brandFields.nameZh as string) || (brandFields.primaryName as string) || (brandFields.name as string) || displayName,
    nameEn: (brandFields.nameEn as string) || (brandFields.name as string) || displayName,
    primaryName: (brandFields.primaryName as string) || (brandFields.nameZh as string) || (brandFields.name as string) || displayName,
    industryId: merged.industryId != null ? String(merged.industryId) : '',
    panoScore: finiteMetric(merged.panoScore),
    mentionRate: finiteMetric(merged.mentionRate),
    sentiment: finiteMetric(merged.sentiment),
    sov: finiteMetric(merged.sov),
    ranking: rankingRaw == null
      ? null
      : Math.max(1, Math.round(rankingRaw)),
  } as PanelBrand;
}
