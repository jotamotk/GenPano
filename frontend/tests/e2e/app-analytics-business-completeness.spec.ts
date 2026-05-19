import crypto from 'node:crypto'
import fs from 'node:fs/promises'

import { expect, test, type Locator, type Page } from '@playwright/test'

type ContractPayload = Record<string, any>

type AnalyticsPayloads = {
  overview?: ContractPayload
  metrics?: ContractPayload
  sentiment?: ContractPayload
  sentimentByEngine?: ContractPayload
  sentimentTrend?: ContractPayload
}

type VisibleExpectation = {
  source: string
  metric: string
  expectedText: string
  rawValue: unknown
  labelHints: string[]
  reason: string
}

type RenderedOverviewSummary = {
  route: string
  url: string
  bodyText: string
  kpiCardTexts: string[]
  chartTexts: string[]
  genericEmptyTexts: string[]
}

type VisibilityPanoTrendSummary = {
  route: string
  url: string
  cardText: string
  legendTexts: string[]
  tooltipText?: string
  hoverAttempted: boolean
  hoverMatchedTargetDate: boolean
  screenshotPath?: string
}

type TopicReadabilityExpectation = {
  topicId: unknown
  topicName: string
  brandLabel: string
  metricTexts: string[]
  proofTexts: string[]
  partialMetricKeys: string[]
  reason: string
}

type RenderedTopicsSummary = {
  route: string
  url: string
  bodyText: string
  primaryTableText: string
  primaryRowTexts: string[]
}

type RenderedAnalyzerFactsSummary = {
  route: string
  url: string
  modalText: string
  analyzerFactsText: string
  citationDomainTexts: string[]
  selectionFallbackReason?: string
}

type TopicDrilldownProbe = {
  topicId: unknown
  promptId: unknown
  queryText?: string
  citationCount?: number
  partialProof: boolean
}

type OpenAttemptsSelection = {
  index: number
  fallbackReason?: string
  error?: string
}

const DEFAULT_PROJECT_ID = '95d43022-a5c8-5944-b6d6-34b29faa18b5'
const DEFAULT_BRAND_ID = 12
const DEFAULT_COMPETITOR_ID = 2
const DEFAULT_FROM_DATE = '2026-04-24'
const DEFAULT_TO_DATE = '2026-05-07'
const DEFAULT_OWNER_USER_ID = 'fe25eff1-8462-43eb-a027-bc8eb2c3db81'
const ISSUE_1167_PROJECT_ID = '7380c0e0-8798-4a5f-998f-42010a7d9caa'
const ISSUE_1167_BRAND_ID = 24
const ISSUE_1167_FROM_DATE = '2026-05-01'
const ISSUE_1167_TO_DATE = '2026-05-19'
const ISSUE_1167_TARGET_DATE = '2026-05-17'
const ISSUE_1167_FORBIDDEN_BRAND_LABELS = ['\u96c5\u8bd7\u5170\u9edb', 'Estee', 'Est\u00e9e']
const SCREENSHOT_DIR = 'test-results/live-app-analytics-business-completeness'

if (process.env.APP_ANALYTICS_PANO_LIVE_E2E === '1') {
  test.use({ trace: 'off', video: 'off', screenshot: 'off' })
}

const TOPICS_REASON_WALL_TEXTS = [
  'Analysis coverage missing',
  'Citation attribution unresolved',
  'Citation attribution is not ready for this metric',
  'Sov Empty',
  'Sov Partial',
  'Sentiment Empty',
  'Sentiment Component Empty',
  'Citation Partial',
  'Citation Component Partial',
  'Needs review',
]
const TOPICS_RAW_REASON_CODE_RE =
  /\b(?:missing_analyzer_rows|target_only_sov|sov_component_missing_required_inputs|sentiment_component_empty|citation_component_partial|unresolved_citation_attribution|missing_required_inputs|no_evidence)\b/i

function assertCondition(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message)
}

function lower(value: unknown) {
  return String(value ?? '').toLowerCase()
}

function isOkFormula(status: unknown) {
  const normalized = lower(status)
  if (!normalized) return true
  return ['ok', 'valid', 'ready', 'complete', 'computed', 'formula_ok'].includes(normalized)
}

function effectiveFormulaStatus(payload?: ContractPayload) {
  return payload?.formula_status || payload?.formula_diagnostics?.status || null
}

function effectiveFormulaOk(payload?: ContractPayload) {
  return isOkFormula(effectiveFormulaStatus(payload))
}

function isOkState(payload?: ContractPayload) {
  return lower(payload?.state) === 'ok'
}

function isFullyOk(payload?: ContractPayload) {
  return isOkState(payload) && effectiveFormulaOk(payload)
}

function count(payload: ContractPayload | undefined, key: string) {
  const value = payload?.evidence_counts?.[key]
  return Number.isFinite(Number(value)) ? Number(value) : 0
}

function listIncludes(payload: ContractPayload | undefined, needle: string) {
  const haystack = [
    ...(payload?.missing_inputs || []),
    ...(payload?.missing_sources || []),
    ...(payload?.missing_reasons || []),
    ...(payload?.formula_diagnostics?.pending_sources || []),
    ...(payload?.formula_diagnostics?.details || []),
  ].map(item => lower(typeof item === 'string' ? item : JSON.stringify(item)))
  return haystack.some(item => item.includes(lower(needle)))
}

function normalizeRatio(value: unknown, fields: ContractPayload = {}) {
  if (value === null || value === undefined || value === '') return null
  const raw = Number(value)
  if (!Number.isFinite(raw)) return null
  const scale = lower(fields.value_scale)
  const unit = lower(fields.unit)
  if (scale === 'percent' || unit === 'percent') return raw / 100
  if (scale === 'decimal' || unit === 'ratio') return raw
  return Math.abs(raw) > 1 ? raw / 100 : raw
}

function pointMap(points: ContractPayload[] = []) {
  const out = new Map<string, number>()
  for (const point of points || []) {
    if (point?.date && point?.value !== null && point?.value !== undefined) {
      out.set(point.date, Number(point.value))
    }
  }
  return out
}

function itemCount(payload?: ContractPayload) {
  if (Array.isArray(payload?.items)) return payload.items.length
  if (Array.isArray(payload?.rows)) return payload.rows.length
  if (Array.isArray(payload?.points)) return payload.points.length
  return 0
}

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const next = Number(value)
  return Number.isFinite(next) ? next : null
}

function compactText(value: unknown) {
  return String(value ?? '').replace(/\s+/g, ' ').trim()
}

function normalizedVisibleReasonText(value: unknown) {
  return compactText(value)
    .toLowerCase()
    .replace(/[_./-]+/g, ' ')
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function expectedBrandLabels(brandId: number, configuredBrandName?: string) {
  const labels = [configuredBrandName]
  if (brandId === 12) labels.push('Estée Lauder', 'Estee Lauder', '雅诗兰黛')
  if (brandId === 24) labels.push('bestCoffer', 'BestCoffer')
  return Array.from(new Set(labels.map(compactText).filter(Boolean)))
}

function renderedPageHasExpectedBrandContext(text: string, labels: string[]) {
  const normalized = compactText(text).toLowerCase()
  return labels.some(label => normalized.includes(compactText(label).toLowerCase()))
}

function round1(value: number) {
  return Math.round((value + Number.EPSILON) * 10) / 10
}

function normalizeScore0To100(value: unknown, fields: ContractPayload = {}) {
  const raw = numberOrNull(value)
  if (raw === null) return null
  if (lower(fields.value_scale) === 'decimal') return Math.round(raw * 100)
  return Math.round(Math.abs(raw) <= 1 ? raw * 100 : raw)
}

function normalizeSentiment(value: unknown, fields: ContractPayload = {}) {
  const raw = numberOrNull(value)
  if (raw === null) return null
  const scale = lower(fields.value_scale)
  const unit = lower(fields.unit)
  if (scale === 'percent' || unit === 'percent' || scale === 'score_0_100') return raw / 100
  if (!scale && !unit && Math.abs(raw) > 1) return raw / 100
  return raw
}

function percentText(value: unknown, fields: ContractPayload = {}) {
  const ratio = normalizeRatio(value, fields)
  if (ratio === null) return null
  return `${round1(ratio * 100)}%`
}

function sentimentText(value: unknown, fields: ContractPayload = {}) {
  const sentiment = normalizeSentiment(value, fields)
  if (sentiment === null) return null
  return `${Math.round(sentiment * 100)}%`
}

function scoreText(value: unknown, fields: ContractPayload = {}) {
  const score = normalizeScore0To100(value, fields)
  return score === null ? null : String(score)
}

function rankText(value: unknown) {
  const rank = numberOrNull(value)
  return rank === null ? null : `#${Math.max(1, Math.round(rank))}`
}

function labelHintsForMetric(metric: string) {
  const key = lower(metric)
  if (key.includes('mention')) return ['Mention Rate', 'Mention rate', '\u63d0\u53ca\u7387']
  if (key === 'sov' || key.includes('share_of_voice')) return ['SoV', 'Share of Voice']
  if (key.includes('sentiment')) return ['Sentiment', '\u60c5\u611f']
  if (key.includes('rank') || key.includes('position')) return ['Rank', 'Industry rank', '\u884c\u4e1a\u6392\u540d']
  if (key.includes('citation')) return ['Citation', '\u5f15\u7528']
  if (key.includes('pano') || key.includes('geo') || key.includes('score')) return ['PANO', 'GEO', 'Score']
  return [metric]
}

function expectedTextForMetric(metric: string, value: unknown, fields: ContractPayload = {}) {
  const key = lower(metric)
  if (key.includes('mention') || key === 'sov' || key.includes('citation')) return percentText(value, fields)
  if (key.includes('sentiment')) return sentimentText(value, fields)
  if (key.includes('rank') || key.includes('position')) return rankText(value)
  if (key.includes('pano') || key.includes('geo') || key.includes('score')) return scoreText(value, fields)
  const raw = numberOrNull(value)
  return raw === null ? null : String(round1(raw))
}

function cardMetricKey(card: ContractPayload) {
  return lower(card.metric_key || card.key || card.metric || '')
}

function canUseMetricLevelValue(item?: ContractPayload) {
  return item && isOkFormula(item.formula_status) && numberOrNull(item.value) !== null
}

function pushExpectation(
  expectations: VisibleExpectation[],
  source: string,
  metric: string,
  value: unknown,
  fields: ContractPayload,
  reason: string,
) {
  const expectedText = expectedTextForMetric(metric, value, fields)
  if (!expectedText) return
  const duplicate = expectations.some(item => item.metric === metric && item.expectedText === expectedText)
  if (duplicate) return
  expectations.push({
    source,
    metric,
    expectedText,
    rawValue: value,
    labelHints: labelHintsForMetric(metric),
    reason,
  })
}

function latestUsablePoint(series?: ContractPayload) {
  if (!series || !isFullyOk(series) || !Array.isArray(series.points)) return null
  for (const point of [...series.points].reverse()) {
    if (numberOrNull(point?.value) !== null) return point
  }
  return null
}

function deriveVisibleOverviewExpectations(payloads: {
  overview: ContractPayload
  metrics: ContractPayload
  competitors: ContractPayload
}) {
  const expectations: VisibleExpectation[] = []
  for (const card of payloads.overview.kpi_cards || []) {
    const metric = cardMetricKey(card)
    if (!metric || !canUseMetricLevelValue(card)) continue
    pushExpectation(
      expectations,
      'overview.kpi_cards',
      metric,
      card.value,
      card,
      `overview card formula_status=${card.formula_status || '<empty>'}`,
    )
  }

  for (const series of payloads.metrics.series || []) {
    const point = latestUsablePoint(series)
    if (!point) continue
    pushExpectation(
      expectations,
      'metrics.series.latest_point',
      lower(series.metric),
      point.value,
      series,
      `metrics series latest date=${point.date || '<unknown>'}`,
    )
  }

  const primary = payloads.competitors.primary
  if (isOkState(payloads.competitors) && primary?.avg_sov !== null && primary?.avg_sov !== undefined) {
    pushExpectation(
      expectations,
      'competitors.primary.avg_sov',
      'sov',
      primary.avg_sov,
      { value_scale: 'decimal', unit: 'ratio' },
      'primary competitor metrics SoV is available',
    )
  }

  return expectations
}

function usableCompetitorSovRows(competitors: ContractPayload) {
  if (!isOkState(competitors)) return []
  return [competitors.primary, ...(competitors.competitors || [])]
    .filter(Boolean)
    .map((row: ContractPayload) => ({
      brand: row.brand_name || row.brand_key || `Brand #${row.brand_id ?? '?'}`,
      sovText: percentText(row.avg_sov, { value_scale: 'decimal', unit: 'ratio' }),
      rawValue: row.avg_sov,
    }))
    .filter((row: ContractPayload) => row.sovText && numberOrNull(row.rawValue) !== null)
}

function visibleReasonParts(payload: ContractPayload) {
  return [
    payload.state_reason,
    payload.state_detail,
    ...(payload.missing_inputs || []),
    ...(payload.missing_sources || []),
    ...(payload.missing_reasons || []),
    ...(payload.formula_diagnostics?.details || []),
    ...(payload.formula_diagnostics?.pending_sources || []),
  ]
    .map(item => compactText(typeof item === 'string' ? item : JSON.stringify(item)))
    .filter(Boolean)
}

function renderedTextMatchesExpectation(text: string, expectation: VisibleExpectation) {
  const normalized = compactText(text)
  if (!normalized.includes(expectation.expectedText)) return false
  return expectation.labelHints.some(label => normalized.toLowerCase().includes(label.toLowerCase()))
}

function assertVisibleOverviewRendering(
  rendered: RenderedOverviewSummary,
  expectations: VisibleExpectation[],
  competitors: ContractPayload,
) {
  const body = compactText(rendered.bodyText)
  const kpiExpectations = expectations.filter(item =>
    ['overview.kpi_cards', 'competitors.primary.avg_sov'].includes(item.source),
  )
  assertCondition(kpiExpectations.length > 0, 'API returned no metric-level ok KPI values to assert')

  const matched = kpiExpectations.filter(expectation =>
    rendered.kpiCardTexts.some(text => renderedTextMatchesExpectation(text, expectation)) ||
    rendered.chartTexts.some(text => renderedTextMatchesExpectation(text, expectation)) ||
    body.includes(expectation.expectedText),
  )
  const missing = kpiExpectations.filter(expectation => !matched.includes(expectation))

  assertCondition(
    matched.length > 0,
    `${rendered.route} rendered no API-derived KPI values although API has ok numeric values: ${JSON.stringify(kpiExpectations)}`,
  )
  assertCondition(
    missing.length === 0,
    `${rendered.route} is missing API-derived visible KPI values: ${JSON.stringify(missing)}; cards=${JSON.stringify(rendered.kpiCardTexts)}`,
  )

  const dashCards = rendered.kpiCardTexts.filter(text => /(?:^|\s)\u2014(?:\s|$)/.test(text) || text.includes('#\u2014'))
  assertCondition(
    dashCards.length < rendered.kpiCardTexts.length || matched.length > 0,
    `${rendered.route} rendered all KPI cards as dashes while API has ok numeric values`,
  )

  const usableSovRows = usableCompetitorSovRows(competitors)
  if (usableSovRows.length > 0) {
    const sovEmpty = rendered.genericEmptyTexts.find(text => /sov|voice|\u58f0\u91cf|\u4efd\u989d|empty|no data/i.test(text))
    assertCondition(
      !sovEmpty,
      `${rendered.route} showed a generic SoV empty state despite usable competitor rows: ${sovEmpty}`,
    )
    const brandMatches = usableSovRows.filter(row => row.brand && body.includes(row.brand))
    assertCondition(
      brandMatches.length > 0,
      `${rendered.route} did not render any usable competitor SoV brand labels: ${JSON.stringify(usableSovRows)}`,
    )
  } else if (!isOkState(competitors)) {
    const reasons = visibleReasonParts(competitors)
    const normalizedBody = normalizedVisibleReasonText(body)
    assertCondition(reasons.length > 0, 'competitors/metrics is non-ok without explicit reason metadata')
    assertCondition(
      reasons.some(reason => normalizedBody.includes(normalizedVisibleReasonText(reason))),
      `${rendered.route} did not render an explicit competitor partial reason; expected one of ${JSON.stringify(reasons)}`,
    )
  }
}

function readableBrandLabel(labels: string[]) {
  return labels.find(label => !/^brand\s*#?\s*\d+$/i.test(compactText(label))) || ''
}

function compactIncludes(text: string, needle: string) {
  return compactText(text).toLowerCase().includes(compactText(needle).toLowerCase())
}

function joinedCompactText(parts: unknown[]) {
  return compactText(parts.filter(Boolean).join(' '))
}

function visibilityPanoTrendDateList(trends: ContractPayload | null | undefined) {
  const series = Array.isArray(trends?.series) ? trends.series : []
  const primary = series.find((item: ContractPayload) => item?.is_primary)
  const candidate =
    primary ||
    [...series].sort(
      (a: ContractPayload, b: ContractPayload) =>
        (Array.isArray(b?.points) ? b.points.length : 0) - (Array.isArray(a?.points) ? a.points.length : 0),
    )[0]
  return Array.isArray(candidate?.points)
    ? candidate.points.map((point: ContractPayload) => compactText(point?.date)).filter(Boolean)
    : []
}

function assertVisibilityPanoTrendRendering(
  rendered: VisibilityPanoTrendSummary,
  options: { brandLabels: string[]; forbiddenLabels: string[]; targetDate?: string },
) {
  const context = joinedCompactText([rendered.cardText, rendered.tooltipText, ...rendered.legendTexts])
  assertCondition(compactIncludes(rendered.cardText, 'PANO'), `${rendered.route} did not expose the PANO trend card; card=${rendered.cardText}`)

  const legendSource = joinedCompactText(rendered.legendTexts.length > 0 ? rendered.legendTexts : [rendered.cardText])
  assertCondition(
    options.brandLabels.some(label => compactIncludes(legendSource, label)),
    `${rendered.route} PANO trend legend does not contain BestCoffer/bestCoffer labels ${JSON.stringify(options.brandLabels)}; legend=${JSON.stringify(rendered.legendTexts)} card=${rendered.cardText}`,
  )

  for (const forbidden of options.forbiddenLabels) {
    assertCondition(
      !compactIncludes(context, forbidden),
      `${rendered.route} PANO trend chart context contains cross-brand label ${forbidden}; context=${context}`,
    )
  }

  if (options.targetDate && rendered.hoverAttempted) {
    assertCondition(
      rendered.tooltipText,
      `${rendered.route} PANO trend target date ${options.targetDate} tooltip was not captured; hoverMatchedTargetDate=${rendered.hoverMatchedTargetDate}`,
    )
    assertCondition(
      rendered.hoverMatchedTargetDate && compactIncludes(rendered.tooltipText, options.targetDate),
      `${rendered.route} PANO trend tooltip did not stay on target date ${options.targetDate}; tooltip=${rendered.tooltipText}`,
    )
  }

  if (rendered.tooltipText) {
    assertCondition(
      options.brandLabels.some(label => compactIncludes(rendered.tooltipText || '', label)),
      `${rendered.route} PANO trend tooltip does not contain BestCoffer/bestCoffer labels ${JSON.stringify(options.brandLabels)}; tooltip=${rendered.tooltipText}`,
    )
  }
}

async function visibleTooltipTexts(page: Page) {
  return page.locator('.recharts-tooltip-wrapper').evaluateAll(elements => {
    const clean = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()
    return elements
      .map(element => {
        const htmlElement = element as HTMLElement
        const style = window.getComputedStyle(htmlElement)
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return ''
        return clean(htmlElement.innerText || htmlElement.textContent)
      })
      .filter(Boolean)
  })
}

async function hoverVisibilityPanoTrendTargetDate(
  page: Page,
  card: Locator,
  targetDate: string | undefined,
  dateList: string[],
) {
  if (!targetDate || !dateList.includes(targetDate)) {
    return { tooltipText: undefined, hoverAttempted: false, hoverMatchedTargetDate: false }
  }

  const chart = card.locator('.recharts-wrapper').first()
  const box = await chart.boundingBox()
  if (!box || dateList.length === 0) {
    return { tooltipText: undefined, hoverAttempted: true, hoverMatchedTargetDate: false }
  }

  const targetIndex = dateList.indexOf(targetDate)
  const ratio = dateList.length <= 1 ? 0.5 : targetIndex / (dateList.length - 1)
  const xRatios = Array.from(new Set([ratio, (targetIndex + 0.5) / dateList.length]))
    .map(value => Math.max(0.04, Math.min(0.96, value)))
  const yRatios = [0.35, 0.5, 0.65]
  let lastTooltipText: string | undefined

  for (const xRatio of xRatios) {
    for (const yRatio of yRatios) {
      await page.mouse.move(box.x + box.width * xRatio, box.y + box.height * yRatio)
      await page.waitForTimeout(150)
      const tooltips = await visibleTooltipTexts(page)
      const matchingTooltip = tooltips.find(text => compactIncludes(text, targetDate))
      if (matchingTooltip) {
        return { tooltipText: matchingTooltip, hoverAttempted: true, hoverMatchedTargetDate: true }
      }
      lastTooltipText = tooltips.find(Boolean) || lastTooltipText
    }
  }

  return { tooltipText: lastTooltipText, hoverAttempted: true, hoverMatchedTargetDate: false }
}

async function captureVisibilityPanoTrend(
  page: Page,
  route: string,
  options: { targetDate?: string; dateList?: string[]; screenshotPath?: string } = {},
): Promise<VisibilityPanoTrendSummary> {
  const card = page.locator('.t-card').filter({ hasText: /PANO/i }).last()
  await expect(card).toBeVisible({ timeout: 20_000 })
  await card.scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)

  const cardText = compactText(await card.innerText({ timeout: 10_000 }))
  const chartCount = await card.locator('.recharts-wrapper').count()
  assertCondition(chartCount > 0, `${route} PANO trend card rendered no Recharts chart; card=${cardText}`)

  const legendTexts = await card.locator('.recharts-legend-item-text').evaluateAll(elements => {
    const clean = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()
    return Array.from(new Set(elements.map(element => clean((element as HTMLElement).innerText || element.textContent)).filter(Boolean)))
  })

  const hover = await hoverVisibilityPanoTrendTargetDate(page, card, options.targetDate, options.dateList || [])
  if (options.screenshotPath) {
    await card.screenshot({ path: options.screenshotPath })
  }

  return {
    route,
    url: page.url(),
    cardText,
    legendTexts,
    tooltipText: hover.tooltipText,
    hoverAttempted: hover.hoverAttempted,
    hoverMatchedTargetDate: hover.hoverMatchedTargetDate,
    screenshotPath: options.screenshotPath,
  }
}

function fixedPercentText(value: unknown, fields: ContractPayload = {}) {
  const ratio = normalizeRatio(value, fields)
  return ratio === null ? null : `${(ratio * 100).toFixed(1)}%`
}

function countText(value: unknown) {
  const next = numberOrNull(value)
  if (next === null || next <= 0) return null
  return Math.round(next).toLocaleString()
}

function topicsRows(payload: ContractPayload) {
  if (Array.isArray(payload?.topics)) return payload.topics
  if (Array.isArray(payload?.rows)) return payload.rows
  if (Array.isArray(payload?.items)) return payload.items
  return []
}

const TOPICS_METRIC_ALIASES: Record<string, string[]> = {
  visibility: ['visibility', 'mention_rate', 'coverage', 'sov'],
  citation: ['citation', 'citations', 'citation_rate'],
  sentiment: ['sentiment'],
  pano_geo: ['pano_geo', 'geo_score', 'pano_score', 'geo'],
}

function topicMetricEvidence(payload: ContractPayload | null | undefined, metric: string) {
  const evidence = payload?.metric_formula_evidence
  if (!evidence || typeof evidence !== 'object') return null
  const aliases = new Set((TOPICS_METRIC_ALIASES[metric] || [metric]).map(item => item.toLowerCase()))
  for (const [key, item] of Object.entries(evidence)) {
    if (aliases.has(key.toLowerCase())) return item as ContractPayload
  }
  return null
}

function statusImpliesPartialOrMissing(status: unknown) {
  const normalized = lower(status)
  if (!normalized) return false
  return !['ok', 'valid', 'ready', 'complete', 'computed', 'formula_ok', 'data_available'].includes(normalized)
}

function hasPartialOrMissingProof(payload: ContractPayload | null | undefined, metric?: string) {
  if (!payload) return false
  const source = metric ? topicMetricEvidence(payload, metric) : payload
  const reasonValues = [
    source?.state,
    source?.status,
    source?.formula_status,
    source?.state_reason,
    source?.reason,
    ...(source?.reason_codes || []),
    ...(source?.missing_inputs || []),
    ...(source?.missing_sources || []),
    ...(source?.missing_reasons || []),
    ...(source?.formula_diagnostics?.details || []),
    ...(source?.formula_diagnostics?.pending_sources || []),
  ]
  return reasonValues.some(value => {
    const normalized = lower(typeof value === 'string' ? value : JSON.stringify(value))
    return (
      statusImpliesPartialOrMissing(value) ||
      /missing|partial|empty|unresolved|pending|not_ready|no_evidence|incomplete|insufficient/.test(normalized)
    )
  })
}

function metricTextIfDisplayable(
  topic: ContractPayload,
  metric: string,
  value: unknown,
  formatter: (value: unknown) => string | null,
) {
  if (numberOrNull(value) === null || hasPartialOrMissingProof(topic, metric)) return null
  return formatter(value)
}

function sentimentProofTexts(topic: ContractPayload) {
  const distribution = topic.sentiment_distribution || {}
  return ['positive', 'neutral', 'negative']
    .map(key => countText(distribution[key]))
    .filter(Boolean) as string[]
}

function topicPartialMetricKeys(topic: ContractPayload) {
  return Object.keys(TOPICS_METRIC_ALIASES).filter(metric => hasPartialOrMissingProof(topic, metric))
}

function deriveTopicReadabilityExpectations(payload: ContractPayload, brandLabels: string[]) {
  const fallbackBrand = readableBrandLabel(brandLabels)
  return topicsRows(payload)
    .map((topic: ContractPayload): TopicReadabilityExpectation | null => {
      const topicName = compactText(topic.topic_name || topic.name || topic.topic || `Topic ${topic.topic_id ?? ''}`)
      const brandLabel = compactText(topic.associated_brand || topic.brand_name || topic.brand || fallbackBrand)
      const visibility = topic.visibility_rate ?? topic.sov ?? topic.mention_rate
      const visibilityText = metricTextIfDisplayable(topic, 'visibility', visibility, fixedPercentText)
      const citationText = metricTextIfDisplayable(topic, 'citation', topic.citation_rate, fixedPercentText)
      const metricTexts = [visibilityText, citationText].filter(Boolean) as string[]
      const proofTexts = [
        topic.prompt_count,
        topic.query_count,
        topic.response_count,
        topic.analyzed_count,
        topic.target_mention_count,
        topic.citation_count,
      ]
        .map(countText)
        .concat(sentimentProofTexts(topic))
        .filter(Boolean) as string[]
      if (!topicName || (!metricTexts.length && !proofTexts.length)) return null
      return {
        topicId: topic.topic_id,
        topicName,
        brandLabel,
        metricTexts,
        proofTexts: Array.from(new Set(proofTexts)),
        partialMetricKeys: topicPartialMetricKeys(topic),
        reason: `topic_id=${topic.topic_id ?? '<unknown>'}`,
      }
    })
    .filter((item): item is TopicReadabilityExpectation => Boolean(item))
}

function repeatedTopicsReasonWallHits(text: string) {
  const body = compactText(text)
  const labelHits = TOPICS_REASON_WALL_TEXTS.filter(label => compactIncludes(body, label))
  const rawHits = body.match(TOPICS_RAW_REASON_CODE_RE)
  return [...labelHits, ...(rawHits ? [rawHits[0]] : [])]
}

function assertVisibleTopicsReadability(
  rendered: RenderedTopicsSummary,
  expectations: TopicReadabilityExpectation[],
  options: { brandId: number; brandLabels: string[] },
) {
  assertCondition(expectations.length > 0, 'Topics API returned no concrete topic rows to assert')
  const tableText = compactText(rendered.primaryTableText)
  assertCondition(tableText, `${rendered.route} did not expose a primary Topics table`)

  const reasonHits = repeatedTopicsReasonWallHits(tableText)
  assertCondition(
    reasonHits.length === 0,
    `${rendered.route} primary Topics table still renders reason-wall text as primary content: ${JSON.stringify(reasonHits)}`,
  )

  const readableBrand = readableBrandLabel(options.brandLabels)
  if (readableBrand) {
    assertCondition(
      !compactIncludes(tableText, `Brand #${options.brandId}`),
      `${rendered.route} primary Topics table uses Brand #${options.brandId} instead of readable brand label ${readableBrand}`,
    )
  }

  const checkedRows = expectations.slice(0, Math.min(3, expectations.length))
  for (const expectation of checkedRows) {
    const rowText = rendered.primaryRowTexts.find(row =>
      compactIncludes(row, expectation.topicName) ||
        (expectation.topicId !== null && expectation.topicId !== undefined && compactIncludes(row, String(expectation.topicId))),
    )
    assertCondition(
      rowText,
      `${rendered.route} could not find primary row for API topic ${expectation.topicName} (${expectation.reason})`,
    )

    if (expectation.brandLabel && readableBrand) {
      assertCondition(
        compactIncludes(rowText, expectation.brandLabel) || compactIncludes(rowText, readableBrand),
        `${rendered.route} row ${expectation.topicName} does not render a readable brand label; row=${rowText}`,
      )
    }

    const metricMatches = expectation.metricTexts.filter(text => compactIncludes(rowText, text))
    const proofMatches = expectation.proofTexts.filter(text => compactIncludes(rowText, text))
    if (expectation.metricTexts.length > 0) {
      const requiredMetricMatches = Math.min(2, expectation.metricTexts.length)
      assertCondition(
        metricMatches.length >= requiredMetricMatches,
        `${rendered.route} row ${expectation.topicName} hides concrete API topic metric values ${JSON.stringify(expectation.metricTexts)}; row=${rowText}`,
      )
    }
    assertCondition(
      metricMatches.length > 0 || proofMatches.length >= Math.min(2, expectation.proofTexts.length),
      `${rendered.route} row ${expectation.topicName} does not surface enough API-derived topic proof; expected proof=${JSON.stringify(expectation.proofTexts)} row=${rowText}`,
    )
    assertCondition(
      !(expectation.metricTexts.length > 0 && /(?:^|\s)--(?:\s|$)/.test(rowText) && metricMatches.length === 0),
      `${rendered.route} row ${expectation.topicName} renders -- while API has concrete topic metric values ${JSON.stringify(expectation.metricTexts)}`,
    )
    const zeroPlaceholders = rowText.match(/\b0\.0%?\b/g) || []
    assertCondition(
      !(expectation.partialMetricKeys.length > 0 && zeroPlaceholders.length >= 3),
      `${rendered.route} row ${expectation.topicName} renders a 0.0 placeholder wall for partial metrics ${JSON.stringify(expectation.partialMetricKeys)}; row=${rowText}`,
    )
  }
}

function assertAnalyzerFactsReadability(
  rendered: RenderedAnalyzerFactsSummary,
  options: { brandId: number; brandLabels: string[]; partialProof?: boolean },
) {
  const factsText = compactText(rendered.analyzerFactsText)
  assertCondition(factsText, `${rendered.route} did not expose Analyzer facts panel text`)

  const reasonHits = repeatedTopicsReasonWallHits(factsText)
  assertCondition(
    reasonHits.length === 0,
    `${rendered.route} Analyzer facts panel still renders reason-wall text as primary content: ${JSON.stringify(reasonHits)}`,
  )

  const readableBrand = readableBrandLabel(options.brandLabels)
  if (readableBrand) {
    assertCondition(
      !compactIncludes(factsText, `Brand #${options.brandId}`),
      `${rendered.route} Analyzer facts panel uses Brand #${options.brandId} instead of readable brand label ${readableBrand}`,
    )
  }

  const zeroPlaceholders = factsText.match(/\b0\.0\b/g) || []
  if (options.partialProof) {
    assertCondition(
      zeroPlaceholders.length < 3,
      `${rendered.route} Analyzer facts panel shows a misleading 0.0 placeholder wall while proof is partial/missing: ${factsText}`,
    )
  }

  if (rendered.citationDomainTexts.length > 0) {
    assertCondition(
      rendered.citationDomainTexts.some(domain => compactIncludes(factsText, domain)),
      `${rendered.route} Analyzer facts panel has citation links but does not surface readable citation domains`,
    )
    assertCondition(
      !compactIncludes(factsText, 'No citations for this response'),
      `${rendered.route} Analyzer facts panel hides available citation proof behind an empty citation state`,
    )
  }
}

async function captureRenderedTopics(page: Page, route: string): Promise<RenderedTopicsSummary> {
  const captured = await page.evaluate(() => {
    const clean = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()
    const tables = Array.from(document.querySelectorAll('table')).map(table => ({
      text: clean((table as HTMLElement).innerText || table.textContent),
      rows: Array.from(table.querySelectorAll('tbody tr'))
        .map(row => clean((row as HTMLElement).innerText || row.textContent))
        .filter(Boolean),
    }))
    const primary =
      tables.find(table =>
        /Topic/i.test(table.text) &&
          /Visibility/i.test(table.text) &&
          /Prompts/i.test(table.text) &&
          /Queries/i.test(table.text),
      ) || tables[0] || { text: '', rows: [] }
    return {
      bodyText: clean(document.body.innerText),
      primaryTableText: primary.text,
      primaryRowTexts: primary.rows,
    }
  })
  return {
    route,
    url: page.url(),
    ...captured,
  }
}

function resolveOpenAttemptsButtonIndex(rowTexts: string[], queryText?: string): OpenAttemptsSelection {
  const query = compactText(queryText)
  if (!rowTexts.length) {
    return { index: 0, error: 'No visible logical query group cards were available' }
  }
  if (!query) {
    return {
      index: 0,
      fallbackReason: 'No sampled query text was available from the prompt queries API; using first logical-query-group card',
    }
  }
  const index = rowTexts.findIndex(row => compactIncludes(row, query))
  if (index >= 0) return { index }
  return {
    index: 0,
    error: `Sampled query text was not found in visible logical query group cards: ${query}`,
  }
}

function topicDrilldownProbe(
  topic: ContractPayload | null | undefined,
  prompt: ContractPayload | null | undefined,
  queriesPayload: ContractPayload | null | undefined,
  partialProof: boolean,
): TopicDrilldownProbe | null {
  if (!topic?.topic_id || !prompt?.prompt_id) return null
  const queryItems = Array.isArray(queriesPayload?.items) ? queriesPayload.items : []
  const attempts = queryItems.flatMap((query: ContractPayload) =>
    (Array.isArray(query.daily_latest) ? query.daily_latest : []).map((attempt: ContractPayload) => ({
      queryText: attempt.query_text || query.query_text,
      citationCount: numberOrNull(attempt.citation_count) || 0,
    })),
  )
  const citedAttempt = attempts.find((attempt: ContractPayload) => Number(attempt.citationCount || 0) > 0)
  const firstAttempt = citedAttempt || attempts[0]
  return {
    topicId: topic.topic_id,
    promptId: prompt.prompt_id,
    queryText: firstAttempt?.queryText,
    citationCount: firstAttempt?.citationCount,
    partialProof,
  }
}

async function captureTopicsAnalyzerFactsModal(
  page: Page,
  baseUrl: string,
  brandId: number,
  probe: TopicDrilldownProbe,
): Promise<RenderedAnalyzerFactsSummary> {
  const route = `/brand/topics?brandId=${brandId}&range=30d&profileGroup=all&topicId=${probe.topicId}&promptId=${probe.promptId}`
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})
  // Per #985 D2.A: query list now renders one clickable Card per logical query
  // group (no "Open response attempts" button); clicking the card opens the modal.
  const groupCards = page.locator('div').filter({ hasText: /Logical query group/i })
  const cardRowTexts = await groupCards.evaluateAll(cards => {
    const clean = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()
    return cards.map(card => clean((card as HTMLElement).innerText || card.textContent))
  })
  const selection = resolveOpenAttemptsButtonIndex(cardRowTexts, probe.queryText)
  assertCondition(!selection.error, `${route} could not select sampled response attempt: ${selection.error}; rows=${JSON.stringify(cardRowTexts)}`)
  if (selection.fallbackReason) {
    console.log(`TOPICS_MODAL_SELECTION_FALLBACK ${selection.fallbackReason}`)
  }
  const groupCard = groupCards.nth(selection.index)
  await expect(groupCard).toBeVisible({ timeout: 25_000 })
  await groupCard.click()
  const modal = page.getByRole('dialog', { name: /Response attempts/i })
  await expect(modal).toBeVisible({ timeout: 15_000 })
  const analyzerPanel = modal.locator('aside').filter({ hasText: 'Analyzer facts' }).last()
  await expect(analyzerPanel).toBeVisible({ timeout: 15_000 })
  const citationDomainTexts = await analyzerPanel.locator('a').evaluateAll(elements =>
    elements
      .map(element => String((element as HTMLElement).innerText || element.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean),
  )
  return {
    route,
    url: page.url(),
    modalText: await modal.innerText(),
    analyzerFactsText: await analyzerPanel.innerText(),
    citationDomainTexts,
    selectionFallbackReason: selection.fallbackReason,
  }
}

async function captureRenderedOverview(page: Page, route: string): Promise<RenderedOverviewSummary> {
  const captured = await page.evaluate(() => {
    const clean = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()
    const visibleText = (selector: string) =>
      Array.from(document.querySelectorAll(selector))
        .map(element => clean((element as HTMLElement).innerText || element.textContent))
        .filter(Boolean)
    const genericEmptyTexts = visibleText('body *').filter(text =>
      text.length <= 120 &&
      /no data|empty|暂无|暂时没有|没有数据|声量份额数据|竞品共现数据/i.test(text)
    )
    return {
      bodyText: clean(document.body.innerText),
      kpiCardTexts: visibleText('.t-card')
        .filter(text => text.length <= 260 && /%|#|\u2014|Mention|SoV|PANO|GEO|Sentiment|Rank|\u63d0\u53ca|\u60c5\u611f|\u6392\u540d|\u5f15\u7528/.test(text))
        .slice(0, 16),
      chartTexts: visibleText('.recharts-wrapper, svg, [data-testid*="chart"], [class*="chart"]')
        .filter(text => text.length <= 500)
        .slice(0, 16),
      genericEmptyTexts,
    }
  })
  return {
    route,
    url: page.url(),
    ...captured,
  }
}

function summarizeContract(name: string, payload: ContractPayload) {
  const summary = {
    state: payload?.state,
    state_reason: payload?.state_reason,
    formula_status: effectiveFormulaStatus(payload),
    evidence_count: payload?.evidence_count,
    evidence_counts: payload?.evidence_counts,
    missing_inputs: payload?.missing_inputs,
    missing_sources: payload?.missing_sources,
    items: Array.isArray(payload?.items) ? payload.items.length : undefined,
    points: Array.isArray(payload?.points) ? payload.points.length : undefined,
    rows: Array.isArray(payload?.rows) ? payload.rows.length : undefined,
    series: Array.isArray(payload?.series)
      ? payload.series.map((item: ContractPayload) => ({
          metric: item.metric,
          state: item.state,
          formula_status: item.formula_status,
          points: Array.isArray(item.points) ? item.points.length : 0,
          missing_inputs: item.missing_inputs,
        }))
      : undefined,
    kpis: Array.isArray(payload?.kpi_cards)
      ? payload.kpi_cards.map((item: ContractPayload) => ({
          key: item.metric_key,
          value: item.value,
          unit: item.unit,
          value_scale: item.value_scale,
          formula_status: item.formula_status,
        }))
      : undefined,
  }
  console.log(`CONTRACT_SUMMARY ${name} ${JSON.stringify(summary)}`)
}

function requireContract(name: string, payload: ContractPayload) {
  assertCondition(payload && typeof payload === 'object', `${name} returned non-object payload`)
  if ('state' in payload) {
    assertCondition(['ok', 'empty', 'partial', 'error'].includes(lower(payload.state)), `${name} returned invalid state ${payload.state}`)
    if (isOkState(payload)) {
      assertCondition(effectiveFormulaOk(payload), `${name} state=ok but formula_status=${effectiveFormulaStatus(payload)}`)
    } else {
      assertCondition(
        payload.state_reason ||
          (payload.missing_inputs || []).length ||
          (payload.missing_sources || []).length ||
          (payload.formula_diagnostics?.details || []).length,
        `${name} is non-ok without an evidence explanation`,
      )
    }
  }
}

function jsonB64(value: unknown) {
  return Buffer.from(JSON.stringify(value)).toString('base64url')
}

function signJwt(userId: string, secret: string) {
  const now = Math.floor(Date.now() / 1000)
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = {
    sub: userId,
    email: 'app-analytics-e2e@example.invalid',
    iat: now,
    exp: now + 30 * 60,
    iss: 'genpano',
    aud: 'genpano-user-access',
  }
  const body = `${jsonB64(header)}.${jsonB64(payload)}`
  const signature = crypto.createHmac('sha256', secret).update(body).digest('base64url')
  return `${body}.${signature}`
}

export function assertSentimentByEngineCompleteness(_payloads: AnalyticsPayloads) {
  const { overview, metrics, sentiment, sentimentByEngine, sentimentTrend } = _payloads
  const adjacentSignals: string[] = []

  const kpiCards = Array.isArray(overview?.kpi_cards) ? overview.kpi_cards : []
  const sentimentCard = kpiCards.find((card: ContractPayload) =>
    ['sentiment', 'avg_sentiment'].includes(lower(card.metric_key)),
  )
  if (sentimentCard && isOkFormula(sentimentCard.formula_status) && sentimentCard.value !== null && sentimentCard.value !== undefined) {
    adjacentSignals.push(`overview sentiment KPI formula_status=${sentimentCard.formula_status}`)
  }

  const metricSentiment = Array.isArray(metrics?.series)
    ? metrics.series.find((series: ContractPayload) => lower(series.metric) === 'sentiment')
    : null
  if (metricSentiment && isFullyOk(metricSentiment) && itemCount(metricSentiment) > 0) {
    adjacentSignals.push(`metrics sentiment points=${itemCount(metricSentiment)}`)
  }

  const sentimentEvidenceCount = Number(sentiment?.evidence_count || 0)
  const sentimentLabelCount = count(sentiment, 'sentiment_label_count')
  const sentimentDistributionCount =
    Number(sentiment?.distribution?.positive_count || 0) +
    Number(sentiment?.distribution?.neutral_count || 0) +
    Number(sentiment?.distribution?.negative_count || 0)
  if (sentimentEvidenceCount > 0 || sentimentLabelCount > 0 || sentimentDistributionCount > 0) {
    adjacentSignals.push(
      `sentiment evidence_count=${sentimentEvidenceCount} label_count=${sentimentLabelCount} distribution=${sentimentDistributionCount}`,
    )
  }

  if (sentimentTrend && isFullyOk(sentimentTrend) && itemCount(sentimentTrend) > 0) {
    adjacentSignals.push(`sentiment_trend_by_engine items=${itemCount(sentimentTrend)}`)
  }

  if (!adjacentSignals.length) return
  if (itemCount(sentimentByEngine) > 0) return

  const byEngineState = lower(sentimentByEngine?.state)
  const byEngineFormula = lower(effectiveFormulaStatus(sentimentByEngine))
  const isEmptyNoEvidence = byEngineState === 'empty' && byEngineFormula === 'no_evidence'
  if (!isEmptyNoEvidence) return

  const missingDetails = [
    ...(sentimentByEngine?.missing_inputs || []),
    ...(sentimentByEngine?.missing_sources || []),
    ...(sentimentByEngine?.formula_diagnostics?.pending_sources || []),
    ...(sentimentByEngine?.formula_diagnostics?.details || []),
  ].map(item => lower(typeof item === 'string' ? item : JSON.stringify(item)))
  const explainsEngineAttribution = missingDetails.some(item =>
    ['engine', 'target_llm', 'llm_engine', 'response_engine', 'engine_attribution', 'source_engine'].some(keyword =>
      item.includes(keyword),
    ),
  )
  if (explainsEngineAttribution) return

  throw new Error(
    `sentiment_by_engine is ${sentimentByEngine?.state}/${effectiveFormulaStatus(sentimentByEngine)}/items=${itemCount(sentimentByEngine)} despite adjacent sentiment evidence: ${adjacentSignals.join('; ')}. Return engine rows or explicit missing_inputs/missing_sources explaining engine attribution.`,
  )
}

async function api(
  baseUrl: string,
  token: string,
  name: string,
  path: string,
) {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      'Accept-Language': 'zh-CN,zh;q=0.9',
    },
  })
  const text = await response.text()
  if (!response.ok) {
    throw new Error(`${name} ${path} -> HTTP ${response.status}: ${text.slice(0, 800)}`)
  }
  const payload = text ? JSON.parse(text) : null
  summarizeContract(name, payload)
  requireContract(name, payload)
  return payload
}

async function seedLiveAuth(
  page: Page,
  token: string,
  projectId: string,
  brandId: number,
  brandName: string,
  competitorId: number,
) {
  await page.addInitScript(
    ({
      token: seededToken,
      projectId: seededProjectId,
      brandId: seededBrandId,
      brandName: seededBrandName,
      competitorId: seededCompetitorId,
    }) => {
      window.localStorage.setItem('genpano_token', seededToken)
      window.sessionStorage.setItem('genpano_onboarding_skipped', '1')
      window.localStorage.setItem('genpano_lang', 'zh')
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: seededProjectId,
          primaryBrandId: Number(seededBrandId),
          industryId: null,
          name: `${seededBrandName || `Brand ${seededBrandId}`} / App Analytics`,
          competitorBrandIds: [Number(seededCompetitorId)],
        }),
      )
    },
    { token, projectId, brandId, brandName, competitorId },
  )
}

const liveFailureShape: AnalyticsPayloads = {
  overview: {
    state: 'partial',
    formula_status: 'missing_required_inputs',
    kpi_cards: [
      { metric_key: 'sentiment', value: 0, value_scale: 'raw_-1_1', formula_status: 'ok' },
    ],
  },
  metrics: {
    state: 'ok',
    formula_status: 'ok',
    series: [
      { metric: 'sentiment', state: 'ok', formula_status: 'ok', points: [{ date: '2026-05-07', value: 0 }] },
    ],
  },
  sentiment: {
    state: 'partial',
    formula_status: 'missing_required_inputs',
    evidence_count: 58,
    evidence_counts: {
      admin_fact_response_count: 70,
      sentiment_label_count: 58,
      sentiment_driver_count: 0,
    },
    missing_inputs: ['sentiment_drivers.source_quote'],
    missing_sources: ['sentiment_drivers.source_quote'],
  },
  sentimentByEngine: {
    state: 'empty',
    state_reason: 'no_sentiment_data',
    formula_status: 'no_evidence',
    evidence_count: 0,
    evidence_counts: { admin_fact_response_count: 0 },
    missing_inputs: [],
    missing_sources: [],
    items: [],
  },
  sentimentTrend: {
    state: 'ok',
    state_reason: 'data_available',
    formula_status: 'ok',
    evidence_count: 2,
    evidence_counts: { geo_score_daily_rows: 2 },
    items: [{ date: '2026-05-07', by_engine: { doubao: 0 } }],
  },
}

test.describe('App analytics business completeness assertion', () => {
  test('flags sentiment_by_engine empty/no_evidence when adjacent sentiment evidence exists', () => {
    expect(() => assertSentimentByEngineCompleteness(liveFailureShape)).toThrow(
      /sentiment_by_engine.*adjacent sentiment evidence/,
    )
  })

  test('accepts explicit missing engine attribution metadata', () => {
    expect(() =>
      assertSentimentByEngineCompleteness({
        ...liveFailureShape,
        sentimentByEngine: {
          ...liveFailureShape.sentimentByEngine,
          missing_inputs: ['queries.target_llm'],
          missing_sources: ['queries.target_llm'],
        },
      }),
    ).not.toThrow()
  })

  test('flags all-dash visible overview cards when API has metric-level ok values', () => {
    const competitors = {
      state: 'ok',
      primary: { brand_name: 'Est\u00e9e Lauder', avg_sov: 0.31 },
      competitors: [{ brand_name: 'Lanc\u00f4me', avg_sov: 0.22 }],
    }
    const expectations = deriveVisibleOverviewExpectations({
      overview: {
        state: 'partial',
        kpi_cards: [
          { metric_key: 'mention_rate', value: 0.42, value_scale: 'decimal', formula_status: 'ok' },
          { metric_key: 'sentiment', value: 0, value_scale: 'raw_-1_1', formula_status: 'ok' },
        ],
      },
      metrics: {
        state: 'ok',
        series: [
          {
            metric: 'mention_rate',
            state: 'ok',
            formula_status: 'ok',
            value_scale: 'decimal',
            points: [{ date: '2026-05-07', value: 0.42 }],
          },
        ],
      },
      competitors,
    })

    expect(() =>
      assertVisibleOverviewRendering(
        {
          route: '/brand/overview',
          url: 'http://example.test/brand/overview',
          bodyText: 'Mention Rate \u2014 SoV \u2014 Sentiment \u2014',
          kpiCardTexts: ['Mention Rate \u2014', 'SoV \u2014', 'Sentiment \u2014'],
          chartTexts: ['\u6682\u65e0\u58f0\u91cf\u4efd\u989d\u6570\u636e'],
          genericEmptyTexts: ['\u6682\u65e0\u58f0\u91cf\u4efd\u989d\u6570\u636e'],
        },
        expectations,
        competitors,
      ),
    ).toThrow(/rendered no API-derived KPI values|missing API-derived visible KPI values/)
  })

  test('accepts visible overview cards that render API-derived values', () => {
    const competitors = {
      state: 'ok',
      primary: { brand_name: 'Est\u00e9e Lauder', avg_sov: 0.31 },
      competitors: [{ brand_name: 'Lanc\u00f4me', avg_sov: 0.22 }],
    }
    const expectations = deriveVisibleOverviewExpectations({
      overview: {
        state: 'partial',
        kpi_cards: [
          { metric_key: 'mention_rate', value: 0.42, value_scale: 'decimal', formula_status: 'ok' },
          { metric_key: 'sentiment', value: 0, value_scale: 'raw_-1_1', formula_status: 'ok' },
        ],
      },
      metrics: {
        state: 'ok',
        series: [
          {
            metric: 'mention_rate',
            state: 'ok',
            formula_status: 'ok',
            value_scale: 'decimal',
            points: [{ date: '2026-05-07', value: 0.42 }],
          },
        ],
      },
      competitors,
    })

    expect(() =>
      assertVisibleOverviewRendering(
        {
          route: '/brand/overview',
          url: 'http://example.test/brand/overview',
          bodyText: 'Est\u00e9e Lauder Mention Rate 42% SoV 31% Sentiment 0% Lanc\u00f4me',
          kpiCardTexts: ['Mention Rate 42%', 'SoV 31%', 'Sentiment 0%'],
          chartTexts: ['Est\u00e9e Lauder Lanc\u00f4me'],
          genericEmptyTexts: [],
        },
        expectations,
        competitors,
      ),
    ).not.toThrow()
  })

  test('accepts humanized competitor partial reason labels from raw API reason codes', () => {
    const competitors = {
      state: 'partial',
      state_reason: 'partial_analyzer_data',
      missing_reasons: ['eligible_response_denominator', 'missing_optional_collection'],
    }
    const expectations = deriveVisibleOverviewExpectations({
      overview: {
        state: 'partial',
        kpi_cards: [
          { metric_key: 'mention_rate', value: 0.42, value_scale: 'decimal', formula_status: 'ok' },
        ],
      },
      metrics: {
        state: 'ok',
        series: [],
      },
      competitors,
    })

    expect(() =>
      assertVisibleOverviewRendering(
        {
          route: '/brand/overview?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/overview?brandId=24&range=30d&profileGroup=all',
          bodyText:
            'bestCoffer Mention Rate 42% Competitor coverage Partial Analyzer Data Eligible Response Denominator Missing Optional Collection',
          kpiCardTexts: ['Mention Rate 42%'],
          chartTexts: [],
          genericEmptyTexts: [],
        },
        expectations,
        competitors,
      ),
    ).not.toThrow()
  })

  test('flags missing visible competitor partial reason evidence', () => {
    const competitors = {
      state: 'partial',
      state_reason: 'partial_analyzer_data',
      missing_reasons: ['eligible_response_denominator', 'missing_optional_collection'],
    }
    const expectations = deriveVisibleOverviewExpectations({
      overview: {
        state: 'partial',
        kpi_cards: [
          { metric_key: 'mention_rate', value: 0.42, value_scale: 'decimal', formula_status: 'ok' },
        ],
      },
      metrics: {
        state: 'ok',
        series: [],
      },
      competitors,
    })

    expect(() =>
      assertVisibleOverviewRendering(
        {
          route: '/brand/overview?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/overview?brandId=24&range=30d&profileGroup=all',
          bodyText: 'bestCoffer Mention Rate 42% Competitor coverage Limited data',
          kpiCardTexts: ['Mention Rate 42%'],
          chartTexts: [],
          genericEmptyTexts: [],
        },
        expectations,
        competitors,
      ),
    ).toThrow(/did not render an explicit competitor partial reason/)
  })

  test('accepts configured BestCoffer brand context for live rendered routes', () => {
    expect(
      renderedPageHasExpectedBrandContext(
        'bestCoffer Analyzer facts Topics Visibility',
        ['bestCoffer'],
      ),
    ).toBe(true)
    expect(
      renderedPageHasExpectedBrandContext(
        'bestCoffer Analyzer facts Topics Visibility',
        ['Estée Lauder', '雅诗兰黛'],
      ),
    ).toBe(false)
  })

  test('flags Visibility PANO trend when brandId=24 renders Estee labels', () => {
    expect(() =>
      assertVisibilityPanoTrendRendering(
        {
          route: '/brand/visibility?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/visibility?brandId=24&range=30d&profileGroup=all',
          cardText: 'PANO 综合趋势 雅诗兰黛 2026-05-17',
          legendTexts: ['雅诗兰黛'],
          tooltipText: '2026-05-17 雅诗兰黛 72',
          hoverAttempted: true,
          hoverMatchedTargetDate: true,
        },
        {
          brandLabels: ['BestCoffer', 'bestCoffer'],
          forbiddenLabels: ['雅诗兰黛', 'Estee', 'Estée'],
          targetDate: '2026-05-17',
        },
      ),
    ).toThrow(/BestCoffer|cross-brand label/)
  })

  test('accepts Visibility PANO trend when legend and tooltip stay on BestCoffer', () => {
    expect(() =>
      assertVisibilityPanoTrendRendering(
        {
          route: '/brand/visibility?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/visibility?brandId=24&range=30d&profileGroup=all',
          cardText: 'PANO 综合趋势 BestCoffer 2026-05-17',
          legendTexts: ['BestCoffer'],
          tooltipText: '2026-05-17 BestCoffer 72',
          hoverAttempted: true,
          hoverMatchedTargetDate: true,
        },
        {
          brandLabels: ['BestCoffer', 'bestCoffer'],
          forbiddenLabels: ['雅诗兰黛', 'Estee', 'Estée'],
          targetDate: '2026-05-17',
        },
      ),
    ).not.toThrow()
  })

  test('flags Visibility PANO trend when target-date tooltip is missing', () => {
    expect(() =>
      assertVisibilityPanoTrendRendering(
        {
          route: '/brand/visibility?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/visibility?brandId=24&range=30d&profileGroup=all',
          cardText: 'PANO \u7efc\u5408\u8d8b\u52bf BestCoffer 2026-05-17',
          legendTexts: ['BestCoffer'],
          hoverAttempted: true,
          hoverMatchedTargetDate: false,
        },
        {
          brandLabels: ['BestCoffer', 'bestCoffer'],
          forbiddenLabels: ['\u96c5\u8bd7\u5170\u9edb', 'Estee', 'Est\u00e9e'],
          targetDate: '2026-05-17',
        },
      ),
    ).toThrow(/target date 2026-05-17 tooltip was not captured/)
  })

  test('flags Visibility PANO trend when tooltip stays on wrong date', () => {
    expect(() =>
      assertVisibilityPanoTrendRendering(
        {
          route: '/brand/visibility?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/visibility?brandId=24&range=30d&profileGroup=all',
          cardText: 'PANO \u7efc\u5408\u8d8b\u52bf BestCoffer 2026-05-17',
          legendTexts: ['BestCoffer'],
          tooltipText: '2026-05-16 BestCoffer 72',
          hoverAttempted: true,
          hoverMatchedTargetDate: false,
        },
        {
          brandLabels: ['BestCoffer', 'bestCoffer'],
          forbiddenLabels: ['\u96c5\u8bd7\u5170\u9edb', 'Estee', 'Est\u00e9e'],
          targetDate: '2026-05-17',
        },
      ),
    ).toThrow(/PANO trend tooltip did not stay on target date 2026-05-17/)
  })

  test('flags Topics primary table reason-wall rendering when API has concrete topic values', () => {
    const topicMonitoring = {
      topics: [
        {
          topic_id: 153,
          topic_name: 'Unstructured data AI masking',
          associated_brand: 'bestCoffer',
          sov: 0.4607,
          citation_rate: 0.25,
          prompt_count: 4,
          query_count: 36,
          response_count: 36,
          citation_count: 12,
          sentiment_distribution: { positive: 3, neutral: 1, negative: 0 },
        },
      ],
    }
    const expectations = deriveTopicReadabilityExpectations(topicMonitoring, ['bestCoffer'])

    expect(() =>
      assertVisibleTopicsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all',
          bodyText: '',
          primaryTableText:
            'Topic Visibility Sentiment Citation Coverage Citations Prompts Queries Unstructured data AI masking Brand #24 -- Analysis coverage missing Citation attribution unresolved Sov Empty Citation Partial 12 4 36',
          primaryRowTexts: [
            'Unstructured data AI masking Brand #24 -- Analysis coverage missing Citation attribution unresolved Sov Empty Citation Partial 12 4 36',
          ],
        },
        expectations,
        { brandId: 24, brandLabels: ['bestCoffer'] },
      ),
    ).toThrow(/reason-wall text/)
  })

  test('accepts Topics primary table when it surfaces API-derived values and proof counts', () => {
    const topicMonitoring = {
      topics: [
        {
          topic_id: 153,
          topic_name: 'Unstructured data AI masking',
          associated_brand: 'bestCoffer',
          sov: 0.4607,
          citation_rate: 0.25,
          prompt_count: 4,
          query_count: 36,
          response_count: 36,
          citation_count: 12,
          sentiment_distribution: { positive: 3, neutral: 1, negative: 0 },
        },
      ],
    }
    const expectations = deriveTopicReadabilityExpectations(topicMonitoring, ['bestCoffer'])

    expect(() =>
      assertVisibleTopicsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all',
          bodyText: '',
          primaryTableText:
            'Topic Visibility Sentiment Citation Coverage Citations Prompts Queries Unstructured data AI masking bestCoffer 46.1% Positive 3 Neutral 1 Negative 0 Citation Coverage 25.0% Limited data 12 4 36',
          primaryRowTexts: [
            'Unstructured data AI masking bestCoffer 46.1% Positive 3 Neutral 1 Negative 0 Citation Coverage 25.0% Limited data 12 4 36',
          ],
        },
        expectations,
        { brandId: 24, brandLabels: ['bestCoffer'] },
      ),
    ).not.toThrow()
  })

  test('flags Topics primary table 0.0 placeholder walls only for partial metrics', () => {
    const topicMonitoring = {
      topics: [
        {
          topic_id: 153,
          topic_name: 'Unstructured data AI masking',
          associated_brand: 'bestCoffer',
          sov: 0.4607,
          citation_rate: 0,
          prompt_count: 4,
          query_count: 36,
          response_count: 36,
          citation_count: 12,
          metric_formula_evidence: {
            citation: {
              formula_status: 'partial',
              reason_codes: ['unresolved_citation_attribution'],
            },
          },
        },
      ],
    }
    const expectations = deriveTopicReadabilityExpectations(topicMonitoring, ['bestCoffer'])

    expect(() =>
      assertVisibleTopicsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all',
          bodyText: '',
          primaryTableText:
            'Topic Visibility Sentiment Citation Coverage Citations Prompts Queries Unstructured data AI masking bestCoffer 46.1% Citation 0.0 Sentiment 0.0 GEO 0.0 12 4 36',
          primaryRowTexts: [
            'Unstructured data AI masking bestCoffer 46.1% Citation 0.0 Sentiment 0.0 GEO 0.0 12 4 36',
          ],
        },
        expectations,
        { brandId: 24, brandLabels: ['bestCoffer'] },
      ),
    ).toThrow(/0\.0 placeholder wall/)
  })

  test('selects the sampled query card before opening Response attempts', () => {
    const selection = resolveOpenAttemptsButtonIndex(
      [
        'Logical query group How does BestCoffer compare on uptime? Days covered 1 Mentioned 0/1 Citations 0',
        'Logical query group 测试非结构化数据AI脱敏的准确率，有哪些可用的参考依据? Days covered 1 Mentioned 1/1 Citations 3',
      ],
      '测试非结构化数据AI脱敏的准确率，有哪些可用的参考依据?',
    )

    expect(selection).toEqual({ index: 1 })
  })

  test('allows first-card modal fallback only when sampled query text is unavailable', () => {
    const selection = resolveOpenAttemptsButtonIndex(
      ['Logical query group Fallback row Days covered 1 Mentioned 1/1 Citations 2'],
      '',
    )

    expect(selection.index).toBe(0)
    expect(selection.fallbackReason).toMatch(/No sampled query text/)
    expect(
      resolveOpenAttemptsButtonIndex(
        ['Logical query group Fallback row Days covered 1 Mentioned 1/1 Citations 2'],
        'Missing sampled query',
      ).error,
    ).toMatch(/not found/)
  })

  test('flags Analyzer facts modal reason-wall and Brand-number primary label', () => {
    expect(() =>
      assertAnalyzerFactsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          modalText: '',
          analyzerFactsText:
            'Analyzer facts Brand #24 Needs review Citation attribution is not ready for this metric Citation attribution unresolved Sentiment Component Empty Citation Component Partial Citations (6) pmc.ncbi.nlm.nih.gov',
          citationDomainTexts: ['pmc.ncbi.nlm.nih.gov'],
        },
        { brandId: 24, brandLabels: ['bestCoffer'] },
      ),
    ).toThrow(/reason-wall text|Brand #24/)
  })

  test('flags Analyzer facts modal misleading 0.0 placeholder wall', () => {
    expect(() =>
      assertAnalyzerFactsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          modalText: '',
          analyzerFactsText:
            'Analyzer facts bestCoffer Target brand Not mentioned Visibility score 0.0 Sentiment score 0.0 Share of voice 0.0 Citation score 80.0 GEO score 0.0 Citations (6) pmc.ncbi.nlm.nih.gov',
          citationDomainTexts: ['pmc.ncbi.nlm.nih.gov'],
        },
        { brandId: 24, brandLabels: ['bestCoffer'], partialProof: true },
      ),
    ).toThrow(/0\.0 placeholder wall/)
  })

  test('accepts Analyzer facts modal concrete zero values when proof context is ok', () => {
    expect(() =>
      assertAnalyzerFactsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          modalText: '',
          analyzerFactsText:
            'Analyzer facts bestCoffer Formula ok Target brand Not mentioned Visibility score 0.0 Sentiment score 0.0 Share of voice 0.0 Citation score 0.0 GEO score 0.0 Citations (1) official.example',
          citationDomainTexts: ['official.example'],
        },
        { brandId: 24, brandLabels: ['bestCoffer'], partialProof: false },
      ),
    ).not.toThrow()
  })

  test('accepts Analyzer facts modal with readable partial state and citation domains', () => {
    expect(() =>
      assertAnalyzerFactsReadability(
        {
          route: '/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          url: 'http://example.test/brand/topics?brandId=24&range=30d&profileGroup=all&topicId=153&promptId=201',
          modalText: '',
          analyzerFactsText:
            'Analyzer facts bestCoffer Limited data 72 of 75 analyzed Citation domains available while attribution is pending Citations (6) pmc.ncbi.nlm.nih.gov arxiv.org',
          citationDomainTexts: ['pmc.ncbi.nlm.nih.gov', 'arxiv.org'],
        },
        { brandId: 24, brandLabels: ['bestCoffer'] },
      ),
    ).not.toThrow()
  })
})

test.describe('Live #1167 BestCoffer PANO trend gate', () => {
  test.describe.configure({ retries: 0 })

  test.skip(
    process.env.APP_ANALYTICS_PANO_LIVE_E2E !== '1',
    'Set APP_ANALYTICS_PANO_LIVE_E2E=1 to run the isolated #1167 production PANO trend check.',
  )

  test('#1167 captures /brand/visibility PANO trend card without running Topics checks', async ({ page }) => {
    test.setTimeout(90_000)
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || 'http://116.62.36.173'
    const projectId = process.env.PROJECT_ID || ISSUE_1167_PROJECT_ID
    const brandId = Number(process.env.BRAND_ID || ISSUE_1167_BRAND_ID)
    const fromDate = process.env.FROM_DATE || ISSUE_1167_FROM_DATE
    const toDate = process.env.TO_DATE || ISSUE_1167_TO_DATE
    const targetDate = process.env.TARGET_DATE || ISSUE_1167_TARGET_DATE
    const userId = process.env.OWNER_USER_ID || DEFAULT_OWNER_USER_ID
    const secret = process.env.USER_JWT_SECRET || process.env.JWT_SECRET || ''
    const brandLabels = expectedBrandLabels(brandId, process.env.BRAND_NAME || process.env.BRAND_QUERY || 'BestCoffer')
    const primaryBrandName = brandLabels[0] || `Brand ${brandId}`

    assertCondition(Buffer.byteLength(secret, 'utf8') >= 32, 'USER_JWT_SECRET/JWT_SECRET is missing or too short')
    assertCondition(brandId === ISSUE_1167_BRAND_ID, `#1167 PANO trend check must run against brandId=24, got ${brandId}`)
    assertCondition(brandLabels.length > 0, '#1167 PANO trend check has no configured brand labels to assert')
    const token = signJwt(userId, secret)

    const dateParams = `from=${encodeURIComponent(fromDate)}&to=${encodeURIComponent(toDate)}`
    const brandDateParams = `${dateParams}&brand_id=${brandId}`
    const me = await api(baseUrl, token, 'auth_me', '/api/auth/me')
    assertCondition(me.id === userId, `auth/me returned unexpected user ${me.id}`)

    const projects = await api(baseUrl, token, 'projects', '/api/v1/projects/')
    const projectItems = Array.isArray(projects?.items) ? projects.items : []
    assertCondition(
      projectItems.some((project: ContractPayload) => project.id === projectId && Number(project.primary_brand_id) === brandId),
      '#1167 approved BestCoffer analytics project is not visible to owner user',
    )

    const competitorTrends = await api(
      baseUrl,
      token,
      'competitors_trends_geo',
      `/api/v1/projects/${projectId}/competitors/trends?metric=geo_score&${brandDateParams}`,
    )
    const trendDates = visibilityPanoTrendDateList(competitorTrends)
    assertCondition(
      trendDates.includes(targetDate),
      `#1167 competitors/trends did not expose target date ${targetDate}; dates=${JSON.stringify(trendDates)}`,
    )

    await fs.mkdir(SCREENSHOT_DIR, { recursive: true })
    const failedResponses: string[] = []
    const runtimeErrors: string[] = []
    page.on('response', response => {
      const url = response.url()
      const status = response.status()
      if (url.includes('/api/') && (status === 401 || status >= 500)) {
        failedResponses.push(`${status} ${url}`)
      }
    })
    page.on('pageerror', error => runtimeErrors.push(`pageerror: ${error.message}`))
    page.on('console', message => {
      if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`)
    })

    await seedLiveAuth(page, token, projectId, brandId, primaryBrandName, DEFAULT_COMPETITOR_ID)
    const route = `/brand/visibility?brandId=${brandId}&range=30d&profileGroup=all`
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
    await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})
    const path = new URL(page.url()).pathname
    assertCondition(!['/register', '/login', '/onboarding'].includes(path), `${route} redirected to ${page.url()}`)
    const pageText = await page.locator('body').innerText({ timeout: 15_000 })
    assertCondition(
      renderedPageHasExpectedBrandContext(pageText, brandLabels),
      `${route} did not render expected BestCoffer brand context from ${JSON.stringify(brandLabels)}`,
    )

    const cardScreenshotPath = `${SCREENSHOT_DIR}/issue_1167_visibility_pano_trend_brand_${brandId}.png`
    const renderedPanoTrend = await captureVisibilityPanoTrend(page, route, {
      targetDate,
      dateList: trendDates,
      screenshotPath: cardScreenshotPath,
    })
    assertVisibilityPanoTrendRendering(renderedPanoTrend, {
      brandLabels,
      forbiddenLabels: ISSUE_1167_FORBIDDEN_BRAND_LABELS,
      targetDate,
    })

    const deployedSha = await page
      .locator('meta[name="genpano-deploy-sha"]')
      .evaluate(element => element.getAttribute('content'))
      .catch(() => null)
    await fs.writeFile(
      `${SCREENSHOT_DIR}/issue-1167-visibility-pano-trend-summary.json`,
      JSON.stringify(
        {
          projectId,
          brandId,
          window: { from: fromDate, to: toDate },
          targetDate,
          route,
          url: renderedPanoTrend.url,
          deployedSha,
          screenshotPath: cardScreenshotPath,
          legendTexts: renderedPanoTrend.legendTexts,
          tooltipText: renderedPanoTrend.tooltipText,
          hoverAttempted: renderedPanoTrend.hoverAttempted,
          hoverMatchedTargetDate: renderedPanoTrend.hoverMatchedTargetDate,
          forbiddenLabels: ISSUE_1167_FORBIDDEN_BRAND_LABELS,
        },
        null,
        2,
      ),
    )

    const fatalRuntimeErrors = runtimeErrors.filter(
      item =>
        !item.includes('favicon') &&
        !item.includes('ResizeObserver loop') &&
        !item.includes('A request was aborted') &&
        !item.includes('Failed to load resource'),
    )
    if (failedResponses.length) {
      throw new Error(`#1167 live PANO trend check had failing API responses:\n${failedResponses.join('\n')}`)
    }
    if (fatalRuntimeErrors.length) {
      throw new Error(`#1167 live PANO trend check had runtime errors:\n${fatalRuntimeErrors.join('\n')}`)
    }

    console.log('ISSUE_1167_PANO_TREND_E2E_SUMMARY ' + JSON.stringify({
      projectId,
      brandId,
      targetDate,
      route,
      screenshotPath: cardScreenshotPath,
      legendTexts: renderedPanoTrend.legendTexts,
      tooltipText: renderedPanoTrend.tooltipText,
      hoverMatchedTargetDate: renderedPanoTrend.hoverMatchedTargetDate,
      deployedSha,
    }))
  })
})

test.describe('Live App analytics business completeness gate', () => {
  test.skip(process.env.APP_ANALYTICS_LIVE_E2E !== '1', 'Set APP_ANALYTICS_LIVE_E2E=1 to run against production.')

  test('validates live API contracts and rendered chart pages', async ({ page }) => {
    test.setTimeout(120_000)
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || 'http://116.62.36.173'
    const projectId = process.env.PROJECT_ID || DEFAULT_PROJECT_ID
    const brandId = Number(process.env.BRAND_ID || DEFAULT_BRAND_ID)
    const competitorId = Number(process.env.COMPETITOR_ID || DEFAULT_COMPETITOR_ID)
    const fromDate = process.env.FROM_DATE || DEFAULT_FROM_DATE
    const toDate = process.env.TO_DATE || DEFAULT_TO_DATE
    const userId = process.env.OWNER_USER_ID || DEFAULT_OWNER_USER_ID
    const secret = process.env.USER_JWT_SECRET || process.env.JWT_SECRET || ''
    const brandLabels = expectedBrandLabels(brandId, process.env.BRAND_NAME || process.env.BRAND_QUERY)
    const primaryBrandName = brandLabels[0] || `Brand ${brandId}`

    assertCondition(Buffer.byteLength(secret, 'utf8') >= 32, 'USER_JWT_SECRET/JWT_SECRET is missing or too short')
    assertCondition(brandLabels.length > 0, 'live App E2E has no configured brand labels to assert')
    const token = signJwt(userId, secret)
    console.log('::add-mask::' + token)

    const dateParams = `from=${encodeURIComponent(fromDate)}&to=${encodeURIComponent(toDate)}`
    const brandDateParams = `${dateParams}&brand_id=${brandId}`

    const me = await api(baseUrl, token, 'auth_me', '/api/auth/me')
    assertCondition(me.id === userId, `auth/me returned unexpected user ${me.id}`)
    assertCondition(me.needs_onboarding !== true && me.needsOnboarding !== true, 'owner user still needs onboarding')

    const projects = await api(baseUrl, token, 'projects', '/api/v1/projects/')
    const projectItems = Array.isArray(projects?.items) ? projects.items : []
    assertCondition(
      projectItems.some((project: ContractPayload) => project.id === projectId && Number(project.primary_brand_id) === brandId),
      'approved live analytics project is not visible to owner user',
    )

    const overview = await api(baseUrl, token, 'overview', `/api/v1/projects/${projectId}/overview?brand_id=${brandId}`)
    const metrics = await api(
      baseUrl,
      token,
      'metrics',
      `/api/v1/projects/${projectId}/metrics?series=mention_rate,sov,rank,sentiment,citation&${brandDateParams}`,
    )
    const byEngine = await api(baseUrl, token, 'metrics_by_engine', `/api/v1/projects/${projectId}/metrics/by-engine?${dateParams}`)
    const position = await api(baseUrl, token, 'position_distribution', `/api/v1/projects/${projectId}/position-distribution?${dateParams}`)
    const competitors = await api(baseUrl, token, 'competitors_metrics', `/api/v1/projects/${projectId}/competitors/metrics?${brandDateParams}`)
    const competitorTrends = await api(
      baseUrl,
      token,
      'competitors_trends_geo',
      `/api/v1/projects/${projectId}/competitors/trends?metric=geo_score&${brandDateParams}`,
    )
    const topicMonitoring = await api(baseUrl, token, 'topics_monitoring', `/api/v1/projects/${projectId}/topics/monitoring?${brandDateParams}`)
    const queryActivity = await api(baseUrl, token, 'query_activity', `/api/v1/projects/${projectId}/query-activity?${brandDateParams}`)
    const heatmapMention = await api(
      baseUrl,
      token,
      'topic_heatmap_mention',
      `/api/v1/projects/${projectId}/topic-heatmap?metric=mention_rate&compare_with=${competitorId}&top_n=10&${dateParams}`,
    )
    const heatmapSentiment = await api(
      baseUrl,
      token,
      'topic_heatmap_sentiment',
      `/api/v1/projects/${projectId}/topic-heatmap?metric=sentiment&compare_with=${competitorId}&top_n=10&${dateParams}`,
    )
    const sentiment = await api(baseUrl, token, 'sentiment', `/api/v1/projects/${projectId}/sentiment?${dateParams}`)
    const sentimentByEngine = await api(baseUrl, token, 'sentiment_by_engine', `/api/v1/projects/${projectId}/sentiment/by-engine?${dateParams}`)
    const sentimentTrend = await api(baseUrl, token, 'sentiment_trend_by_engine', `/api/v1/projects/${projectId}/sentiment/trend-by-engine?${dateParams}`)
    const sentimentAttribution = await api(
      baseUrl,
      token,
      'sentiment_topic_attribution',
      `/api/v1/projects/${projectId}/sentiment/topic-attribution?limit=10&${dateParams}`,
    )
    const mentionSamples = await api(baseUrl, token, 'mention_samples', `/api/v1/projects/${projectId}/mention-samples?limit=20&${dateParams}`)
    const citations = await api(baseUrl, token, 'citations', `/api/v1/projects/${projectId}/citations?page_size=20&${dateParams}`)
    const citationComposition = await api(baseUrl, token, 'citations_composition', `/api/v1/projects/${projectId}/citations/composition?${dateParams}`)
    const citationAuthorityTrend = await api(
      baseUrl,
      token,
      'citations_authority_trend',
      `/api/v1/projects/${projectId}/citations/authority-trend?${dateParams}`,
    )
    const citationContentGap = await api(baseUrl, token, 'citations_content_gap', `/api/v1/projects/${projectId}/citations/content-gap?limit=12&${dateParams}`)

    assertCondition(overview.project_scope?.primary_brand_id === brandId, 'overview project_scope primary_brand_id mismatch')
    assertCondition((overview.project_scope?.competitor_brand_ids || []).includes(competitorId), 'overview project_scope is missing configured competitor brand 2')
    const overviewMentionResponses =
      count(overview, 'brand_mentioned_response_count') ||
      Number(overview.identity_diagnostics?.brand_mentioned_response_count || 0)
    assertCondition(overviewMentionResponses > 0, 'overview has no target brand mentioned response evidence')

    const overviewCompetitiveMentions = count(overview, 'competitive_mention_count')
    if (overviewCompetitiveMentions <= 0) {
      assertCondition(!isFullyOk(overview), 'overview is fully ok without competitive mention evidence for SoV')
    }

    const kpiCards = Array.isArray(overview.kpi_cards) ? overview.kpi_cards : []
    const cardByKey = new Map(kpiCards.map((card: ContractPayload) => [card.metric_key, card]))
    const mentionCard = cardByKey.get('mention_rate')
    const sovCard = cardByKey.get('sov')
    const sentimentCard = cardByKey.get('sentiment') || cardByKey.get('avg_sentiment')
    assertCondition(mentionCard, 'overview is missing mention_rate KPI contract')
    assertCondition(sovCard, 'overview is missing SoV KPI contract')
    assertCondition(sentimentCard, 'overview is missing sentiment KPI contract')
    if (isFullyOk(overview) && isOkFormula(sovCard.formula_status)) {
      const sovValue = normalizeRatio(sovCard.value, sovCard)
      assertCondition(sovValue !== null && sovValue < 0.999, `overview SoV KPI is still effectively 100%: ${sovCard.value}`)
    }

    const seriesByMetric = new Map((metrics.series || []).map((series: ContractPayload) => [series.metric, series]))
    for (const required of ['mention_rate', 'sov', 'rank', 'sentiment', 'citation']) {
      assertCondition(seriesByMetric.has(required), `metrics endpoint missing series ${required}`)
    }
    const mentionSeries = seriesByMetric.get('mention_rate')
    const sovSeries = seriesByMetric.get('sov')
    const citationSeries = seriesByMetric.get('citation')
    for (const point of mentionSeries.points || []) {
      const value = normalizeRatio(point.value, mentionSeries)
      assertCondition(value === null || value <= 1, `mention_rate point exceeds 1 after normalization: ${point.value}`)
    }
    if (isFullyOk(sovSeries) && (sovSeries.points || []).length) {
      const normalized = sovSeries.points.map((point: ContractPayload) => normalizeRatio(point.value, sovSeries)).filter((value: number | null) => value !== null)
      assertCondition(!normalized.every((value: number) => value >= 0.999), `SoV series is still effectively 100%: ${JSON.stringify(normalized)}`)
    } else {
      assertCondition(
        listIncludes(sovSeries, 'competitive') || listIncludes(metrics, 'competitive'),
        'SoV is not ok but does not explain missing competitive-set evidence',
      )
    }

    const citationEvidence = Math.max(
      count(overview, 'citation_source_count'),
      count(metrics, 'citation_source_count'),
      Number(citations.total || 0),
      Number(citations.evidence_count || 0),
      Number(citationComposition.total || 0),
      Number(citationComposition.evidence_count || 0),
    )
    if (citationEvidence <= 0) {
      assertCondition(!isFullyOk(citations), 'citations endpoint is fully ok despite zero citation_sources evidence')
      assertCondition(listIncludes(citations, 'citation'), 'citations endpoint does not identify citation_sources as missing')
      assertCondition(
        !isFullyOk(citationSeries) || !(citationSeries.points || []).length,
        `citation metric series is ok/populated despite zero citation source evidence: ${JSON.stringify(citationSeries)}`,
      )
    }

    assertCondition(byEngine.items?.length > 0 || !isFullyOk(byEngine), 'by-engine chart has no rows while fully ok')
    for (const row of byEngine.items || []) {
      for (const key of ['mention_rate', 'sov', 'citation_rate']) {
        const value = normalizeRatio(row[key])
        assertCondition(value === null || value <= 1, `${key} exceeds 1 for engine ${row.engine}: ${row[key]}`)
      }
    }

    assertCondition(position.total_mentions > 0 || !isFullyOk(position), 'position distribution has no mentions while fully ok')
    assertCondition(competitors.primary || !isFullyOk(competitors), 'competitors/metrics has no primary row while fully ok')
    assertCondition((competitors.competitors || []).length >= 1 || !isFullyOk(competitors), 'competitors/metrics has no competitor rows while fully ok')

    const trendHasPoints = (competitorTrends.series || []).some((series: ContractPayload) =>
      (series.points || []).some((point: ContractPayload) => point.value !== null && point.value !== undefined),
    )
    assertCondition(trendHasPoints || !isFullyOk(competitorTrends), 'PANO/GEO trend is fully ok but has no points')

    const metricsSovMap = pointMap(sovSeries?.points || [])
    const overviewSovMap = pointMap(overview.sov_30d || [])
    if (isFullyOk(overview) && isFullyOk(sovSeries) && metricsSovMap.size && overviewSovMap.size) {
      for (const [day, metricValue] of metricsSovMap) {
        if (!overviewSovMap.has(day)) continue
        const overviewValue = Number(overviewSovMap.get(day))
        const normalizedMetric = normalizeRatio(metricValue, sovSeries)
        const normalizedOverview = normalizeRatio(overviewValue)
        assertCondition(
          Math.abs(Number(normalizedMetric) - Number(normalizedOverview)) <= 0.015,
          `overview vs visibility SoV mismatch on ${day}: overview=${overviewValue}, metrics=${metricValue}`,
        )
      }
    }

    const topicSummary = topicMonitoring.summary || {}
    if (isFullyOk(topicMonitoring)) {
      assertCondition(Number(topicSummary.topic_count || 0) > 0, 'topics monitoring ok but topic_count=0')
      assertCondition(Number(topicSummary.prompt_count || 0) > 0, 'topics monitoring ok but prompt_count=0')
      assertCondition(Number(topicSummary.query_count || 0) > 0, 'topics monitoring ok but query_count=0')
      assertCondition(Number(topicSummary.response_count || 0) > 0, 'topics monitoring ok but response_count=0')
    }
    assertCondition((queryActivity.totals?.queries || 0) > 0 || !isFullyOk(queryActivity), 'query activity ok but no queries')
    assertCondition((queryActivity.totals?.responses || 0) > 0 || !isFullyOk(queryActivity), 'query activity ok but no responses')

    let topicModalProbe: TopicDrilldownProbe | null = null
    const topicWithPrompts = (topicMonitoring.topics || []).find((topic: ContractPayload) => Number(topic.prompt_count || 0) > 0)
    if (topicWithPrompts) {
      const promptPayload = await api(
        baseUrl,
        token,
        'topic_prompts_sample',
        `/api/v1/projects/${projectId}/topics/${topicWithPrompts.topic_id}/prompts?${brandDateParams}`,
      )
      assertCondition(promptPayload.total > 0, `topic ${topicWithPrompts.topic_id} has prompt_count but prompts endpoint returned none`)
      const promptWithQueries = (promptPayload.items || []).find((prompt: ContractPayload) => Number(prompt.query_count || 0) > 0)
      assertCondition(promptWithQueries, `topic ${topicWithPrompts.topic_id} prompts endpoint has no prompt with query_count`)
      const queriesPayload = await api(
        baseUrl,
        token,
        'prompt_queries_sample',
        `/api/v1/projects/${projectId}/prompts/${promptWithQueries.prompt_id}/queries?${brandDateParams}`,
      )
      assertCondition(queriesPayload.total > 0, `prompt ${promptWithQueries.prompt_id} has query_count but queries endpoint returned none`)
      const modalPartialProof =
        hasPartialOrMissingProof(topicMonitoring) ||
        hasPartialOrMissingProof(topicWithPrompts) ||
        hasPartialOrMissingProof(promptPayload) ||
        hasPartialOrMissingProof(queriesPayload)
      topicModalProbe = topicDrilldownProbe(topicWithPrompts, promptWithQueries, queriesPayload, modalPartialProof)
    } else if (isFullyOk(topicMonitoring)) {
      throw new Error('topics monitoring is fully ok but no topic exposes prompt/query evidence')
    }

    for (const [name, heatmap] of [
      ['mention heatmap', heatmapMention],
      ['sentiment heatmap', heatmapSentiment],
    ] as const) {
      const uniqueBrands = new Set((heatmap.rows || []).map((row: ContractPayload) => row.brand_id))
      const uniqueTopics = new Set(
        (heatmap.rows || []).flatMap((row: ContractPayload) => (row.values || []).map((cell: ContractPayload) => cell.topic_id)),
      )
      if (isFullyOk(heatmap)) {
        assertCondition(uniqueBrands.size >= 2, `${name} is ok but collapsed to ${uniqueBrands.size} brand row(s)`)
        assertCondition(uniqueTopics.size >= 2, `${name} is ok but collapsed to ${uniqueTopics.size} topic(s)`)
      } else {
        assertCondition(
          (heatmap.missing_inputs || []).length ||
            (heatmap.missing_sources || []).length ||
            heatmap.state_reason,
          `${name} is non-ok without missing evidence metadata`,
        )
      }
    }

    const sentimentTotal =
      Number(sentiment.distribution?.positive_count || 0) +
      Number(sentiment.distribution?.neutral_count || 0) +
      Number(sentiment.distribution?.negative_count || 0)
    assertCondition(sentimentTotal > 0 || !isFullyOk(sentiment), 'sentiment endpoint fully ok but distribution has zero evidence')
    assertCondition((sentimentTrend.items || []).length > 0 || !isFullyOk(sentimentTrend), 'sentiment trend fully ok but empty')
    assertCondition((mentionSamples.items || []).length > 0 || !isFullyOk(mentionSamples), 'mention samples fully ok but empty')
    if ((sentiment.top_drivers || []).length === 0) {
      assertCondition(
        !isFullyOk(sentiment) || listIncludes(sentiment, 'sentiment_drivers'),
        'sentiment endpoint is fully ok while sentiment driver evidence is absent',
      )
    }
    if (isFullyOk(sentimentAttribution)) {
      assertCondition((sentimentAttribution.items || []).length > 0, 'sentiment topic attribution fully ok but empty')
    }
    assertSentimentByEngineCompleteness({ overview, metrics, sentiment, sentimentByEngine, sentimentTrend })

    if (citationEvidence <= 0) {
      for (const [name, payload] of [
        ['citation composition', citationComposition],
        ['citation authority trend', citationAuthorityTrend],
      ] as const) {
        assertCondition(!isFullyOk(payload), `${name} is fully ok despite zero citation_sources evidence`)
      }
    }
    if (isFullyOk(citationContentGap)) {
      assertCondition((citationContentGap.topics || []).length > 0, 'citation content gap fully ok but no topics')
    }

    await fs.mkdir(SCREENSHOT_DIR, { recursive: true })
    const failedResponses: string[] = []
    const runtimeErrors: string[] = []
    let capturedMentionSamplesPayload: ContractPayload | null = null
    page.on('response', response => {
      const url = response.url()
      const status = response.status()
      if (url.includes('/api/') && (status === 401 || status >= 500)) {
        failedResponses.push(`${status} ${url}`)
      }
      // #1175: capture the mention-samples payload the BrandSentimentPage actually consumes so the
      // DOM-rendered response_text can be compared against the live API value below.
      if (
        status === 200 &&
        url.includes(`/api/v1/projects/${projectId}/mention-samples`) &&
        capturedMentionSamplesPayload === null
      ) {
        response
          .json()
          .then(json => {
            capturedMentionSamplesPayload = json as ContractPayload
          })
          .catch(() => {})
      }
    })
    page.on('pageerror', error => runtimeErrors.push(`pageerror: ${error.message}`))
    page.on('console', message => {
      if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`)
    })
    await seedLiveAuth(page, token, projectId, brandId, primaryBrandName, competitorId)
    const visibleExpectations = deriveVisibleOverviewExpectations({ overview, metrics, competitors })
    const visibleOverviewSummaries: Array<RenderedOverviewSummary & {
      expected: VisibleExpectation[]
      competitorSovRows: ReturnType<typeof usableCompetitorSovRows>
    }> = []
    const topicReadabilityExpectations = deriveTopicReadabilityExpectations(topicMonitoring, brandLabels)
    const visibleTopicsSummaries: Array<RenderedTopicsSummary & {
      expected: TopicReadabilityExpectation[]
      modal?: RenderedAnalyzerFactsSummary
    }> = []
    // #1175: traceability record proving the BrandSentimentPage rendered the live API response_text.
    let sentimentResponseExpansionEvidence: {
      route: string
      apiItemCount: number
      apiResponseTextPreview: string
      apiResponseTextLength: number
      renderedMatchesApi: boolean
    } | null = null

    const routes = [
      `/brand/overview?brandId=${brandId}&range=30d&profileGroup=all`,
      '/brand/overview',
      `/brand/visibility?brandId=${brandId}&range=30d&profileGroup=all`,
      `/brand/topics?brandId=${brandId}&range=30d&profileGroup=all`,
      `/brand/sentiment?brandId=${brandId}&range=30d&profileGroup=all`,
      `/brand/citations?brandId=${brandId}&range=30d&profileGroup=all`,
      `/brand/competitors?brandId=${brandId}&range=30d&profileGroup=all`,
    ]
    const pageSummaries = []
    for (const route of routes) {
      await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
      await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})
      const path = new URL(page.url()).pathname
      assertCondition(!['/register', '/login', '/onboarding'].includes(path), `${route} redirected to ${page.url()}`)
      const text = await page.locator('body').innerText({ timeout: 15_000 })
      assertCondition(
        renderedPageHasExpectedBrandContext(text, brandLabels),
        `${route} did not render expected brand context from ${JSON.stringify(brandLabels)}`,
      )
      const surfaceCount = await page.locator('.recharts-wrapper, svg, table, [role="table"], [data-testid*="chart"], [class*="chart"]').count()
      assertCondition(surfaceCount > 0, `${route} rendered no chart/table/svg surface`)
      const screenshotName = route.replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'route'
      await page.screenshot({ path: `${SCREENSHOT_DIR}/${screenshotName}.png`, fullPage: true })
      if (route === '/brand/overview' || route.startsWith('/brand/overview?')) {
        const renderedOverview = await captureRenderedOverview(page, route)
        assertVisibleOverviewRendering(renderedOverview, visibleExpectations, competitors)
        visibleOverviewSummaries.push({
          ...renderedOverview,
          expected: visibleExpectations,
          competitorSovRows: usableCompetitorSovRows(competitors),
        })
      } else if (route.startsWith('/brand/topics?')) {
        const renderedTopics = await captureRenderedTopics(page, route)
        assertVisibleTopicsReadability(renderedTopics, topicReadabilityExpectations, { brandId, brandLabels })
        let modalSummary: RenderedAnalyzerFactsSummary | undefined
        if (topicModalProbe) {
          modalSummary = await captureTopicsAnalyzerFactsModal(page, baseUrl, brandId, topicModalProbe)
          assertAnalyzerFactsReadability(modalSummary, { brandId, brandLabels, partialProof: topicModalProbe.partialProof })
        }
        visibleTopicsSummaries.push({
          ...renderedTopics,
          expected: topicReadabilityExpectations,
          modal: modalSummary,
        })
      } else if (route.startsWith('/brand/sentiment?')) {
        // #1175 acceptance evidence: prove the response row expansion renders the live API response_text.
        // Wait briefly for the captured mention-samples payload (the page already finished networkidle above,
        // but the JSON .then() resolves on the next microtask). No flake-retry per AGENTS.md — single attempt.
        const waitDeadline = Date.now() + 10_000
        while (capturedMentionSamplesPayload === null && Date.now() < waitDeadline) {
          await page.waitForTimeout(250)
        }
        assertCondition(
          capturedMentionSamplesPayload !== null,
          '#1175 expected /api/v1/projects/{id}/mention-samples response to be captured on /brand/sentiment',
        )
        const samplesPayload = capturedMentionSamplesPayload as ContractPayload
        const samplesItems = Array.isArray(samplesPayload.items) ? samplesPayload.items : []
        assertCondition(
          samplesItems.length >= 1,
          '#1175 expected at least one sentiment response item on /brand/sentiment',
        )
        const firstItem = samplesItems[0] as ContractPayload
        const firstResponseText = firstItem?.response_text
        assertCondition(
          typeof firstResponseText === 'string' && firstResponseText.length > 0,
          '#1175 first response item must have non-empty response_text',
        )
        // Click the first row's Inspect control. The page uses a plain <button> labelled "Inspect" with
        // aria-label="Inspect full response for ...". Using the visible name keeps test scope to this file
        // (no product code testid needed). See BrandSentimentPage.tsx:570-591.
        const inspectButton = page.getByRole('button', { name: /^Inspect full response for / }).first()
        await inspectButton.waitFor({ state: 'visible', timeout: 10_000 })
        await inspectButton.click()
        // Wait for the expanded panel header to appear, then assert the rendered text contains the exact API value.
        const expandedPanel = page.getByText('Full response inspection').first()
        await expandedPanel.waitFor({ state: 'visible', timeout: 10_000 })
        const expandedContainer = expandedPanel.locator('..')
        const expandedText = await expandedContainer.innerText({ timeout: 10_000 })
        assertCondition(
          expandedText.includes(firstResponseText),
          '#1175 expanded row must render exact API response_text on /brand/sentiment',
        )
        sentimentResponseExpansionEvidence = {
          route,
          apiItemCount: samplesItems.length,
          apiResponseTextPreview: firstResponseText.slice(0, 200),
          apiResponseTextLength: firstResponseText.length,
          renderedMatchesApi: true,
        }
      }
      pageSummaries.push({ route, path, surfaceCount })
    }

    await fs.writeFile(
      `${SCREENSHOT_DIR}/visible-overview-summary.json`,
      JSON.stringify(
        {
          projectId,
          brandId,
          window: { from: fromDate, to: toDate },
          expectedValues: visibleExpectations,
          competitorSovRows: usableCompetitorSovRows(competitors),
          renderedRoutes: visibleOverviewSummaries.map(summary => ({
            route: summary.route,
            url: summary.url,
            expected: summary.expected.map(item => ({
              metric: item.metric,
              source: item.source,
              expectedText: item.expectedText,
              rawValue: item.rawValue,
              reason: item.reason,
            })),
            kpiCardTexts: summary.kpiCardTexts,
            chartTexts: summary.chartTexts,
            genericEmptyTexts: summary.genericEmptyTexts,
          })),
        },
        null,
        2,
      ),
    )
    await fs.writeFile(
      `${SCREENSHOT_DIR}/visible-topics-readability-summary.json`,
      JSON.stringify(
        {
          projectId,
          brandId,
          window: { from: fromDate, to: toDate },
          apiExpectations: topicReadabilityExpectations,
          renderedRoutes: visibleTopicsSummaries.map(summary => ({
            route: summary.route,
            url: summary.url,
            primaryTableText: summary.primaryTableText,
            primaryRowTexts: summary.primaryRowTexts,
            modal: summary.modal
              ? {
                  route: summary.modal.route,
                  url: summary.modal.url,
                  analyzerFactsText: summary.modal.analyzerFactsText,
                  citationDomainTexts: summary.modal.citationDomainTexts,
                  selectionFallbackReason: summary.modal.selectionFallbackReason,
                }
              : null,
          })),
        },
        null,
        2,
      ),
    )
    // #1175: persist the captured response_text preview so the acceptance evidence is traceable from the artifact.
    await fs.writeFile(
      `${SCREENSHOT_DIR}/sentiment-response-expansion-summary.json`,
      JSON.stringify(
        {
          projectId,
          brandId,
          window: { from: fromDate, to: toDate },
          issue: '#1175',
          evidence: sentimentResponseExpansionEvidence,
        },
        null,
        2,
      ),
    )

    const fatalRuntimeErrors = runtimeErrors.filter(
      item =>
        !item.includes('favicon') &&
        !item.includes('ResizeObserver loop') &&
        !item.includes('A request was aborted') &&
        !item.includes('Failed to load resource'),
    )
    if (failedResponses.length) {
      throw new Error(`live App had failing API responses:\n${failedResponses.join('\n')}`)
    }
    if (fatalRuntimeErrors.length) {
      throw new Error(`live App had runtime errors:\n${fatalRuntimeErrors.join('\n')}`)
    }

    console.log('FINAL_BUSINESS_COMPLETENESS_E2E_SUMMARY ' + JSON.stringify({
      projectId,
      brandId,
      window: { from: fromDate, to: toDate },
      overview: {
        state: overview.state,
        formula_status: overview.formula_status,
        evidence_counts: overview.evidence_counts,
        kpis: kpiCards.map((card: ContractPayload) => ({
          key: card.metric_key,
          value: card.value,
          formula_status: card.formula_status,
          value_scale: card.value_scale,
        })),
      },
      metrics: (metrics.series || []).map((series: ContractPayload) => ({
        metric: series.metric,
        state: series.state,
        formula_status: series.formula_status,
        points: (series.points || []).length,
        missing_inputs: series.missing_inputs,
      })),
      topics: topicSummary,
      topicsReadability: visibleTopicsSummaries.map(summary => ({
        route: summary.route,
        rowsChecked: summary.expected.length,
        modalChecked: Boolean(summary.modal),
      })),
      heatmapMention: {
        state: heatmapMention.state,
        rows: (heatmapMention.rows || []).length,
      },
      sentiment: {
        state: sentiment.state,
        formula_status: sentiment.formula_status,
        evidence_count: sentiment.evidence_count,
        top_drivers: (sentiment.top_drivers || []).length,
      },
      sentimentByEngine: {
        state: sentimentByEngine.state,
        formula_status: sentimentByEngine.formula_status,
        evidence_count: sentimentByEngine.evidence_count,
        items: itemCount(sentimentByEngine),
        missing_inputs: sentimentByEngine.missing_inputs,
        missing_sources: sentimentByEngine.missing_sources,
      },
      citations: {
        state: citations.state,
        formula_status: citations.formula_status,
        total: citations.total,
        evidence_count: citations.evidence_count,
      },
      pageSummaries,
    }))
  })

  test('#1175 sentiment-only acceptance: /brand/sentiment response row expansion', async ({ page }) => {
    // Self-contained replay for the #1175 user symptom ("情感分析中看不到具体的response").
    // The sibling iterated test above can short-circuit on an earlier /brand/overview assertion
    // before reaching /brand/sentiment (see Epic #1175 evidence-gap notes). This test boots a
    // fresh page, navigates ONLY to /brand/sentiment, and proves response_text reaches the DOM.
    // No flake-retry: single attempt per AGENTS.md `### Acceptance And Verification Evidence`.
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || 'http://116.62.36.173'
    const projectId = process.env.PROJECT_ID || DEFAULT_PROJECT_ID
    const brandId = Number(process.env.BRAND_ID || DEFAULT_BRAND_ID)
    const competitorId = Number(process.env.COMPETITOR_ID || DEFAULT_COMPETITOR_ID)
    const userId = process.env.OWNER_USER_ID || DEFAULT_OWNER_USER_ID
    const secret = process.env.USER_JWT_SECRET || process.env.JWT_SECRET || ''
    const brandLabels = expectedBrandLabels(brandId, process.env.BRAND_NAME || process.env.BRAND_QUERY)
    const primaryBrandName = brandLabels[0] || `Brand ${brandId}`

    assertCondition(Buffer.byteLength(secret, 'utf8') >= 32, 'USER_JWT_SECRET/JWT_SECRET is missing or too short')
    const token = signJwt(userId, secret)
    console.log('::add-mask::' + token)

    let capturedMentionSamplesPayload: ContractPayload | null = null
    page.on('response', response => {
      const url = response.url()
      if (
        response.status() === 200 &&
        url.includes(`/api/v1/projects/${projectId}/mention-samples`) &&
        capturedMentionSamplesPayload === null
      ) {
        response
          .json()
          .then(json => {
            capturedMentionSamplesPayload = json as ContractPayload
          })
          .catch(() => {})
      }
    })

    await seedLiveAuth(page, token, projectId, brandId, primaryBrandName, competitorId)

    const route = `/brand/sentiment?brandId=${brandId}&range=30d&profileGroup=all`
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
    await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})

    const waitDeadline = Date.now() + 10_000
    while (capturedMentionSamplesPayload === null && Date.now() < waitDeadline) {
      await page.waitForTimeout(250)
    }
    assertCondition(
      capturedMentionSamplesPayload !== null,
      '#1175 expected /api/v1/projects/{id}/mention-samples response to be captured on /brand/sentiment',
    )
    const samplesPayload = capturedMentionSamplesPayload as ContractPayload
    const samplesItems = Array.isArray(samplesPayload.items) ? samplesPayload.items : []
    assertCondition(
      samplesItems.length >= 1,
      '#1175 expected at least one sentiment response item on /brand/sentiment',
    )
    const firstItem = samplesItems[0] as ContractPayload
    const firstResponseText = firstItem?.response_text
    assertCondition(
      typeof firstResponseText === 'string' && firstResponseText.length > 0,
      '#1175 first response item must have non-empty response_text',
    )

    const inspectButton = page.getByRole('button', { name: /^Inspect full response for / }).first()
    await inspectButton.waitFor({ state: 'visible', timeout: 10_000 })
    await inspectButton.click()

    const expandedPanel = page.getByText('Full response inspection').first()
    await expandedPanel.waitFor({ state: 'visible', timeout: 10_000 })
    const expandedContainer = expandedPanel.locator('..')
    const expandedText = await expandedContainer.innerText({ timeout: 10_000 })
    assertCondition(
      expandedText.includes(firstResponseText),
      '#1175 expanded row must render exact API response_text on /brand/sentiment',
    )

    const deployedSha = await page
      .evaluate(() => document.querySelector('meta[name="genpano-deploy-sha"]')?.getAttribute('content') ?? null)
      .catch(() => null)

    await fs.mkdir(SCREENSHOT_DIR, { recursive: true })
    await fs.writeFile(
      `${SCREENSHOT_DIR}/issue-1175-sentiment-only-acceptance.json`,
      JSON.stringify(
        {
          issue: '#1175',
          route,
          response_text_length: firstResponseText.length,
          response_text_preview: firstResponseText.slice(0, 200),
          rendered_matches_api: true,
          deployed_sha: deployedSha,
          api_item_count: samplesItems.length,
        },
        null,
        2,
      ),
    )
  })
})
