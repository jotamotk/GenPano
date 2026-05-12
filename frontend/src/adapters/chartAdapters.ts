/**
 * Adapters: backend chart DTOs → existing chart-component prop shapes.
 *
 * The frontend chart components in `components/charts/` (and their
 * page-level consumers) were built against the mock data shape. These
 * adapters preserve those prop shapes so the visual layer doesn't change
 * — only the data origin.
 *
 * Each adapter is a pure function: it takes one or more API DTOs and
 * returns the prop shape a specific chart consumes.
 */

import type {
  AuthorityRadarOut,
  AuthorityTrendOut,
  CitationCompositionOut,
  ContentGapOut,
  EngineMetricsOut,
  GroupSharedDomainsOut,
  HeatmapRow as ApiHeatmapRow,
  MentionSamplesOut,
  PositionDistributionOut,
  PrTargetsOut,
  ProductRelationsOut,
  SentimentByEngineOut,
  SentimentTrendByEngineOut,
  SimulatorBaselineOut,
  TopicAttributionOut,
  TopicHeatmapOut,
} from '../api/charts'
import type {
  IndustryDistributionOut,
  IndustryGroupsOut,
  IndustryMoversOut,
  IndustryRankingByEngineOut,
  IndustryRankingOut,
  IndustrySegmentsOut,
  IndustryTopDomainsOut,
  TopicIntentMatrixOut,
} from '../api/industries'
import {
  canUseMetricEvidence,
  type AnalyticsContractMetadata,
} from '../api/analyticsContract'

function canUseChartMetrics(
  out: (AnalyticsContractMetadata & { state?: string }) | null | undefined,
  metricKeys: string[],
): boolean {
  if (!out) return false
  return metricKeys.every((key) => canUseMetricEvidence(out, key))
}

// ── Engine breakdown bar (BrandVisibilityPage) ──────────────────────
export interface EngineBreakdownBar {
  engine: string
  mentionRate: number | null
  sov: number | null
  citationShare: number | null
}

export function adaptEngineMetricsToBreakdown(
  out: EngineMetricsOut | undefined,
): EngineBreakdownBar[] {
  if (!out || !Array.isArray(out.items)) return []
  return out.items.map((row) => ({
    engine: row.engine,
    mentionRate:
      canUseChartMetrics(out, ['mention_rate']) && row.mention_rate != null
        ? +(row.mention_rate * 100).toFixed(1)
        : null,
    sov:
      canUseChartMetrics(out, ['sov']) && row.sov != null
        ? +(row.sov * 100).toFixed(1)
        : null,
    citationShare:
      canUseChartMetrics(out, ['citation']) && row.citation_rate != null
        ? +(row.citation_rate * 100).toFixed(1)
        : null,
  }))
}

// ── Position distribution (HorizontalBar) ───────────────────────────
export interface PositionBarRow {
  name: string
  value: number
}

export function adaptPositionDistribution(
  out: PositionDistributionOut | undefined,
): PositionBarRow[] {
  if (!out || !canUseChartMetrics(out, ['rank']) || !Array.isArray(out.items)) return []
  return out.items.map((it) => ({ name: it.bucket, value: it.pct }))
}

// ── Topic heatmap (BrandTopicHeatmap) ───────────────────────────────
export interface FrontendHeatmapRow {
  brandId: number | string
  brandName: string
  values: {
    topicId: string
    topicLabel: string
    value: number | null
    sample: number
  }[]
}

export function adaptHeatmap(
  out: TopicHeatmapOut | undefined,
  primaryBrandId: number | string | null,
): FrontendHeatmapRow[] {
  if (!out || !canUseChartMetrics(out, [out.metric]) || !Array.isArray(out.rows)) return []
  return out.rows.map((r: ApiHeatmapRow) => ({
    brandId: r.brand_id,
    brandName: r.brand_name ?? `#${r.brand_id}`,
    values: (r.values ?? []).map((c) => ({
      topicId: String(c.topic_id),
      topicLabel: c.topic_label,
      value: c.value,
      sample: c.sample,
    })),
  }))
}

// ── Sentiment stacked bar (BrandSentimentPage) ──────────────────────
export interface SentimentStackBarRow {
  engine: string
  positive: number
  neutral: number
  negative: number
}

export function adaptSentimentByEngine(
  out: SentimentByEngineOut | undefined,
): SentimentStackBarRow[] {
  if (!out || !canUseChartMetrics(out, ['sentiment']) || !Array.isArray(out.items)) return []
  return out.items.map((it) => ({
    engine: it.engine,
    positive: it.positive,
    neutral: it.neutral,
    negative: it.negative,
  }))
}

// ── Sentiment trend (TrendChart) ────────────────────────────────────
export interface SentimentTrendRow {
  name: string
  [engine: string]: string | number | null
}

export function adaptSentimentTrend(
  out: SentimentTrendByEngineOut | undefined,
): { rows: SentimentTrendRow[]; engines: string[] } {
  if (
    !out ||
    !canUseChartMetrics(out, ['sentiment']) ||
    !Array.isArray(out.items) ||
    !Array.isArray(out.engines)
  ) {
    return { rows: [], engines: [] }
  }
  return {
    engines: out.engines,
    rows: out.items.map((p) => {
      const r: SentimentTrendRow = { name: p.date.slice(5) }
      for (const eng of out.engines) {
        r[eng] = p.by_engine[eng] != null ? +(p.by_engine[eng]! * 100).toFixed(1) : null
      }
      return r
    }),
  }
}

// ── Topic attribution (sentiment) ───────────────────────────────────
export interface SentimentTopicAttributionRow {
  topicName: string
  negativeCount: number
  negativeRatio: number
  sampleSnippet: string | null
}

export function adaptTopicAttribution(
  out: TopicAttributionOut | undefined,
): SentimentTopicAttributionRow[] {
  if (!out || !canUseChartMetrics(out, ['sentiment']) || !Array.isArray(out.items)) return []
  return out.items.map((r) => ({
    topicName: r.topic_name,
    negativeCount: r.negative_count,
    negativeRatio: r.negative_ratio,
    sampleSnippet: r.sample_snippet,
  }))
}

// ── Mention samples (Response 列表) ─────────────────────────────────
export interface SentimentSampleRow {
  label: string
  topic: string
  engine: string
  time: string
  summary: string
}

export function adaptMentionSamples(
  out: MentionSamplesOut | undefined,
): SentimentSampleRow[] {
  if (!out || !canUseChartMetrics(out, ['sentiment']) || !Array.isArray(out.items)) return []
  return out.items.map((m) => ({
    label: m.label,
    topic: m.topic ?? '—',
    engine: m.engine ?? '—',
    time: m.occurred_at ? m.occurred_at.slice(0, 10) : '',
    summary: m.summary ?? '',
  }))
}

// ── Authority share time series (TrendChart) ────────────────────────
export interface AuthorityShareSeriesRow {
  date: string
  official_domain_pct: number
  co_occurrence_pct: number
  text_match_pct: number
}

export function adaptAuthorityTrend(
  out: AuthorityTrendOut | undefined,
): AuthorityShareSeriesRow[] {
  if (!out || !canUseChartMetrics(out, ['citation']) || !Array.isArray(out.points)) return []
  return out.points.map((p) => ({
    date: p.date,
    // Tier1 = official, Tier2 = authoritative media (co-occurrence proxy),
    // Tier3+4 = text match aggregate.
    official_domain_pct: +(p.tier1_pct ?? 0).toFixed(1),
    co_occurrence_pct: +(p.tier2_pct ?? 0).toFixed(1),
    text_match_pct: +(
      (p.tier3_pct ?? 0) + (p.tier4_pct ?? 0) + (p.untiered_pct ?? 0)
    ).toFixed(1),
  }))
}

// ── Citation composition donut ──────────────────────────────────────
export interface DonutSegment {
  name: string
  value: number
  color: string
}

const TIER_COLORS = [
  'var(--color-accent)',
  'var(--color-chart-3)',
  'var(--color-chart-2)',
  'var(--color-chart-4)',
  'var(--color-chart-line-grid)',
]

export function adaptCitationComposition(
  out: CitationCompositionOut | undefined,
): DonutSegment[] {
  if (!out || !canUseChartMetrics(out, ['citation']) || !Array.isArray(out.segments)) return []
  return out.segments.map((s, i) => ({
    name: s.label,
    value: +s.pct.toFixed(1),
    color: TIER_COLORS[i] ?? 'var(--color-chart-line-grid)',
  }))
}

// ── Content gap topics ──────────────────────────────────────────────
export interface ContentGapTopicMockShape {
  topicName: string
  mentionRate: number
  citationRate: number
  gap: number
  suggestion: string | null
}

export function adaptContentGap(out: ContentGapOut | undefined): {
  topics: ContentGapTopicMockShape[]
  pageTypeDistribution: { type: string; count: number; pct: number }[]
} {
  if (!out || !canUseChartMetrics(out, ['citation', 'topic']) || !Array.isArray(out.topics))
    return { topics: [], pageTypeDistribution: [] }
  return {
    topics: out.topics.map((t) => ({
      topicName: t.topic_name,
      mentionRate: t.mention_rate,
      citationRate: t.citation_rate,
      gap: t.gap_score,
      suggestion: t.suggestion,
    })),
    pageTypeDistribution: (out.page_type_distribution ?? []).map((d) => ({
      type: d.page_type,
      count: d.count,
      pct: d.pct,
    })),
  }
}

// ── PR targets / Tier2 matrix ───────────────────────────────────────
//
// The live `/citations/pr-targets` endpoint returns a slimmer shape than the
// existing `PrTargetsPanel` mock. Keep unavailable formula fields null so the
// UI can render them as missing instead of inventing production scores.
export function adaptPrTargets(out: PrTargetsOut | undefined) {
  if (!out || !canUseChartMetrics(out, ['citation']) || !Array.isArray(out.targets))
    return {
      targets: [],
      kolScorecards: [],
      tier2Matrix: {
        domains: [] as string[],
        brands: [] as { brandId: number; label: string; counts: number[] }[],
      },
    }
  return {
    targets: out.targets.map((t, i) => {
      return {
        rank: i + 1,
        domain: t.domain,
        tier: t.tier,
        authorityTier: t.tier,
        authorityConfidence: null,
        citations30d: t.we_count + t.competitors_count,
        trending30dPct: null,
        prScore: null,
        attributedToMeCount: t.we_count,
        weCount: t.we_count,
        competitorsCount: t.competitors_count,
        gap: t.gap,
        suggestion: t.suggestion,
      }
    }),
    kolScorecards: (out.kol_scorecards ?? []).map((k, i) => ({
      id: `kol-${i}`,
      domain: k.name,
      name: k.name,
      platform: k.platform,
      audienceScore: k.audience_score,
      qualityScore: k.quality_score,
      risk: k.risk,
      authorityConfidence: k.audience_score == null ? null : k.audience_score / 100,
      avgCitationsPerWeek: null,
      diversity: null,
      brandDiversity90d: [],
    })),
    tier2Matrix: {
      domains: out.tier2_matrix?.domains ?? [],
      brands: (out.tier2_matrix?.brands ?? []).map((b) => ({
        brandId: b.brand_id,
        label: b.label,
        counts: b.counts,
      })),
    },
  }
}

// ── Simulator baseline ──────────────────────────────────────────────
export function adaptSimulatorBaseline(out: SimulatorBaselineOut | undefined) {
  if (!out || !canUseChartMetrics(out, ['citation', 'pano_score'])) return null
  const currentByTier: Record<number, number> = {}
  const tierWeights: Record<number, number> = {}
  const defaultConfidence: Record<number, number> = {}
  for (const t of out.tiers ?? []) {
    currentByTier[t.tier] = t.current_count
    tierWeights[t.tier] = t.weight
    defaultConfidence[t.tier] = t.confidence
  }
  return {
    currentPanoA: out.current_pano,
    industryMedian: out.industry_median ?? null,
    industryTop3Avg: out.industry_top3_avg ?? null,
    currentByTier,
    tierWeights,
    defaultConfidence,
    presets: (out.presets ?? []).map((p) => ({
      id: String(p.id),
      label: String(p.label),
      deltaByTier: Object.fromEntries(
        Object.entries(p.delta_by_tier ?? {}).map(([k, v]) => [Number(k), Number(v)]),
      ) as Record<number, number>,
    })),
  }
}

// ── Authority radar ─────────────────────────────────────────────────
export interface AuthorityRadarMockRow {
  tier: string
  me: number
  industryMedian: number
  topCompetitor: number
}

export function adaptAuthorityRadar(
  out: AuthorityRadarOut | undefined,
): AuthorityRadarMockRow[] {
  if (!out || !canUseChartMetrics(out, ['citation']) || !Array.isArray(out.rows)) return []
  return out.rows.map((r) => ({
    tier: r.tier,
    me: r.me,
    industryMedian: r.industry_median,
    topCompetitor: r.top_competitor,
  }))
}

// ── Group shared domains ────────────────────────────────────────────
export function adaptGroupSharedDomains(out: GroupSharedDomainsOut | undefined) {
  if (!out || !canUseChartMetrics(out, ['citation']))
    return {
      group: null as string | null,
      sharedRatio: null as number | null,
      sharedDomains: [] as {
        domain: string
        tier: number | null
        sharedWith: string[]
      }[],
    }
  return {
    group: out.group_name,
    sharedRatio: out.shared_ratio,
    sharedDomains: (out.items ?? []).map((i) => ({
      domain: i.domain,
      tier: i.tier,
      sharedWith: i.sister_brand_names,
    })),
  }
}

// ── Product relations ───────────────────────────────────────────────
export function adaptProductRelations(out: ProductRelationsOut | undefined) {
  if (!out || !canUseChartMetrics(out, ['product']) || !Array.isArray(out.items)) return [] as { productA: number; productB: number; type: string; confidence: number }[]
  return out.items.map((r) => ({
    productA: r.product_a_id,
    productAName: r.product_a_name,
    productB: r.product_b_id,
    productBName: r.product_b_name,
    type: r.type,
    confidence: r.confidence ?? 0.5,
  }))
}

// ── Industry distribution → IQR card props ──────────────────────────
export interface IqrStats {
  p25: number | null
  p50: number | null
  p75: number | null
  min: number | null
  max: number | null
  n: number
  outliers?: number[]
  tooSmall?: boolean
}

export function adaptIndustryDistribution(
  out: IndustryDistributionOut | undefined,
): Record<string, IqrStats> {
  const empty: Record<string, IqrStats> = {}
  if (!out) return empty
  const result: Record<string, IqrStats> = {}
  for (const s of out.stats) {
    result[s.metric] = {
      p25: s.p25,
      p50: s.p50,
      p75: s.p75,
      min: s.min,
      max: s.max,
      n: s.n,
      tooSmall: s.n < 3,
    }
  }
  return result
}

// ── Industry ranking → leaderboard rows ─────────────────────────────
export interface LeaderboardRow {
  id: string | number
  name: string
  rank: number
  panoScore: number
  mentionRate: number
  sov: number
  sentiment: number
  citationShare: number
  industryId: string | number | null
  sparkPano: number[]
}

export function adaptIndustryRanking(
  out: IndustryRankingOut | undefined,
  industryId: string | number,
): LeaderboardRow[] {
  if (!out) return []
  return out.items.map((row) => ({
    id: row.brand_id,
    name: row.brand_name ?? `#${row.brand_id}`,
    rank: row.rank,
    panoScore: row.avg_geo_score ?? 0,
    mentionRate: row.avg_mention_rate ?? 0,
    sov:
      row.avg_sov != null && row.avg_sov <= 1
        ? +(row.avg_sov * 100).toFixed(1)
        : row.avg_sov ?? 0,
    sentiment: row.avg_sentiment ?? 0,
    citationShare:
      row.avg_citation_rate != null
        ? +(row.avg_citation_rate * 100).toFixed(1)
        : 0,
    industryId,
    sparkPano: row.sparkline ?? [],
  }))
}

export function adaptIndustryMovers(out: IndustryMoversOut | undefined) {
  if (!out) return { gainers: [], losers: [] }
  const map = (rows: IndustryMoversOut['gainers']) =>
    rows.map((r) => ({
      brandId: r.brand_id,
      name: r.brand_name ?? `#${r.brand_id}`,
      delta: r.delta_pct,
      currentPano: r.current_pano,
      sparkline: r.sparkline,
      driver: r.driver,
    }))
  return { gainers: map(out.gainers), losers: map(out.losers) }
}

export function adaptIndustryGroups(out: IndustryGroupsOut | undefined) {
  if (!out) return []
  return out.items.map((g) => ({
    groupId: g.group_id,
    groupName: g.group_name,
    parentCompany: g.parent_company,
    memberBrandIds: g.member_brand_ids,
    memberBrandNames: g.member_brand_names,
    aggregateGeoScore: g.aggregate_geo_score,
    aggregateSov: g.aggregate_sov,
  }))
}

export function adaptIndustryTopDomains(out: IndustryTopDomainsOut | undefined) {
  if (!out) return []
  const total = out.items.reduce((s, r) => s + (r.total_citations || 0), 0) || 1
  return out.items.map((r) => ({
    domain: r.domain,
    citations: r.total_citations,
    share: +((r.total_citations / total) * 100).toFixed(1),
    authorityTier: r.tier ?? 0,
    authorityConfidence: r.tier != null ? 1 - (r.tier - 1) * 0.15 : 0,
    brandsAttributed: r.top_brand_id != null ? [String(r.top_brand_id)] : [],
  }))
}

export function adaptIndustrySegments(out: IndustrySegmentsOut | undefined) {
  if (!out) return []
  return out.items.map((seg) => ({
    segment: seg.segment,
    label: seg.label_zh,
    items: seg.items.map((i) => ({
      brandId: i.brand_id,
      name: i.brand_name ?? `#${i.brand_id}`,
      panoScore: i.avg_geo_score ?? 0,
      sov:
        i.avg_sov != null && i.avg_sov <= 1
          ? +(i.avg_sov * 100).toFixed(1)
          : i.avg_sov ?? 0,
    })),
  }))
}

export function adaptIndustryRankingByEngine(
  out: IndustryRankingByEngineOut | undefined,
) {
  if (!out)
    return {
      engines: [],
      brands: [] as {
        brandId: number
        name: string
        rank: number
        scores: number[]
        ranks: (number | null)[]
        deltaMax: number | null
      }[],
    }
  return {
    engines: out.engines,
    brands: out.items.map((r) => ({
      brandId: r.brand_id,
      name: r.brand_name ?? `#${r.brand_id}`,
      rank: r.overall_rank,
      scores: out.engines.map(
        (e) => r.cells.find((c) => c.engine === e)?.avg_geo_score ?? 0,
      ),
      ranks: out.engines.map(
        (e) => r.cells.find((c) => c.engine === e)?.rank ?? null,
      ),
      deltaMax: r.delta_max,
    })),
  }
}

export function adaptTopicIntentMatrix(out: TopicIntentMatrixOut | undefined) {
  if (!out) return { intents: [], topics: [] }
  return {
    intents: out.intents,
    topics: out.rows.map((r) => ({
      topicId: r.topic_id,
      topicName: r.topic_name,
      total: r.total_count,
      cells: out.intents.map((intent) => {
        const c = r.cells.find((x) => x.intent === intent)
        return { intent, count: c?.count ?? 0, pct: c?.pct ?? 0 }
      }),
    })),
  }
}
