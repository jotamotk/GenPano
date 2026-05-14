/* ─────────────────────────────────────────────────────────────
 * Shared types for the reports page split.
 *
 * The original ReportsPage.tsx was JS-style (no type annotations).
 * These types are minimal — they capture only what's needed to
 * satisfy `noImplicitAny` in the extracted modules. They are NOT
 * exhaustive contracts; behavior is unchanged.
 * ─────────────────────────────────────────────────────────── */

export type TFn = (key: string, params?: Record<string, unknown>) => string;
export type FormatBrandFn = (b: unknown) => string;
export type FormatDateRangeFn = (start: string, end: string) => string;

/* Mock REPORTS entry shape (covers all fields read across the page). */
export interface ReportData {
  id: string;
  type: string;
  status: string;
  brand: { id: string; primaryName?: string; nameZh?: string; nameEn?: string };
  periodStart: string;
  periodEnd: string;
  generatedAt: string;
  panoScore: number;
  panoPrev: number;
  subdim: Record<string, { current: number; delta: number }>;
  sovRank: number;
  prevSovRank: number;
  diagnostics: {
    p0: number;
    p1: number;
    p2: number;
    p3: number;
    topTitleZh: string;
    topTitleEn: string;
  };
  engines: {
    top: string;
    topRate: number;
    weak: string;
    weakRate: number;
    negKeywordZh: string;
    negKeywordEn: string;
  };
  topProduct: {
    nameZh: string;
    nameEn: string;
    rank: number;
    topic: string;
    contextZh: string;
    contextEn: string;
  };
  newCompetitor: { nameZh: string; nameEn: string; pct: number };
  wordCount: number;
}

/* Section descriptor built from SECTION_MATRIX[type][sectionType] for each report. */
export interface ReportSection {
  type: string;
  variant: string;
  primaryReader: string;
  insightStackLayers: number[];
}
