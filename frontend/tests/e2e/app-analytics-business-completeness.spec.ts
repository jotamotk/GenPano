import crypto from 'node:crypto'
import fs from 'node:fs/promises'

import { expect, test, type Page } from '@playwright/test'

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

const DEFAULT_PROJECT_ID = '95d43022-a5c8-5944-b6d6-34b29faa18b5'
const DEFAULT_BRAND_ID = 12
const DEFAULT_COMPETITOR_ID = 2
const DEFAULT_FROM_DATE = '2026-04-24'
const DEFAULT_TO_DATE = '2026-05-07'
const DEFAULT_OWNER_USER_ID = 'fe25eff1-8462-43eb-a027-bc8eb2c3db81'
const SCREENSHOT_DIR = 'test-results/live-app-analytics-business-completeness'

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
    assertCondition(reasons.length > 0, 'competitors/metrics is non-ok without explicit reason metadata')
    assertCondition(
      reasons.some(reason => body.toLowerCase().includes(reason.toLowerCase())),
      `${rendered.route} did not render an explicit competitor partial reason; expected one of ${JSON.stringify(reasons)}`,
    )
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

async function seedLiveAuth(page: Page, token: string, projectId: string, brandId: number) {
  await page.addInitScript(
    ({ token: seededToken, projectId: seededProjectId, brandId: seededBrandId }) => {
      window.localStorage.setItem('genpano_token', seededToken)
      window.sessionStorage.setItem('genpano_onboarding_skipped', '1')
      window.localStorage.setItem('genpano_lang', 'zh')
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: seededProjectId,
          primaryBrandId: Number(seededBrandId),
          industryId: null,
          name: 'Estee Lauder / App Analytics',
          competitorBrandIds: [2],
        }),
      )
    },
    { token, projectId, brandId },
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
})

test.describe('Live App analytics business completeness gate', () => {
  test.skip(process.env.APP_ANALYTICS_LIVE_E2E !== '1', 'Set APP_ANALYTICS_LIVE_E2E=1 to run against production.')

  test('validates live API contracts and rendered chart pages', async ({ page }) => {
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || 'http://116.62.36.173'
    const projectId = process.env.PROJECT_ID || DEFAULT_PROJECT_ID
    const brandId = Number(process.env.BRAND_ID || DEFAULT_BRAND_ID)
    const competitorId = Number(process.env.COMPETITOR_ID || DEFAULT_COMPETITOR_ID)
    const fromDate = process.env.FROM_DATE || DEFAULT_FROM_DATE
    const toDate = process.env.TO_DATE || DEFAULT_TO_DATE
    const userId = process.env.OWNER_USER_ID || DEFAULT_OWNER_USER_ID
    const secret = process.env.USER_JWT_SECRET || process.env.JWT_SECRET || ''

    assertCondition(Buffer.byteLength(secret, 'utf8') >= 32, 'USER_JWT_SECRET/JWT_SECRET is missing or too short')
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
      'approved Estee Lauder project is not visible to owner user',
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
    await seedLiveAuth(page, token, projectId, brandId)
    const visibleExpectations = deriveVisibleOverviewExpectations({ overview, metrics, competitors })
    const visibleOverviewSummaries: Array<RenderedOverviewSummary & {
      expected: VisibleExpectation[]
      competitorSovRows: ReturnType<typeof usableCompetitorSovRows>
    }> = []

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
      const body = text.toLowerCase()
      const hasBrandContext = body.includes('estee') || body.includes('est\u00e9e') || text.includes('\u96c5\u8bd7\u5170\u9edb')
      assertCondition(hasBrandContext, `${route} did not render Estee/Est\u00e9e/\u96c5\u8bd7\u5170\u9edb context`)
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
})
