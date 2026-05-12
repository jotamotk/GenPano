import { describe, expect, it } from 'vitest'

import {
  ANALYZER_CONTRACT_REQUIRED_COLUMNS,
  APP_ANALYZER_CHART_CONTRACTS,
  analyzerContractPages,
} from './appChartDataContract'

describe('App analyzer chart data contract inventory', () => {
  it('covers every required Brand Mode App route with complete matrix columns', () => {
    expect(analyzerContractPages).toEqual([
      '/brand/overview',
      '/brand/visibility',
      '/brand/topics',
      '/brand/sentiment',
      '/brand/citations',
      '/brand/products',
      '/brand/competitors',
    ])

    const coveredPages = new Set(APP_ANALYZER_CHART_CONTRACTS.map((item) => item.page))
    for (const page of analyzerContractPages) {
      expect(coveredPages.has(page), `${page} is missing from contract matrix`).toBe(true)
    }

    for (const item of APP_ANALYZER_CHART_CONTRACTS) {
      for (const column of ANALYZER_CONTRACT_REQUIRED_COLUMNS) {
        expect(item[column], `${item.page} / ${item.chartKpi} missing ${column}`).toBeTruthy()
      }
      expect(item.visibleBehavior.ok, `${item.metricKey} missing ok behavior`).toBeTruthy()
      expect(item.visibleBehavior.partial, `${item.metricKey} missing partial behavior`).toBeTruthy()
      expect(item.visibleBehavior.empty, `${item.metricKey} missing empty behavior`).toBeTruthy()
    }
  })

  it('locks SoV to response-level competitive extraction instead of target-only or stale aggregates', () => {
    const sovContracts = APP_ANALYZER_CHART_CONTRACTS.filter((item) => item.metricKey.includes('sov'))
    expect(sovContracts.length).toBeGreaterThan(0)

    for (const contract of sovContracts) {
      const required = contract.requiredSourceFacts.join(' | ').toLowerCase()
      const denominator = contract.denominator.toLowerCase()
      const failure = contract.failureState.toLowerCase()
      expect(required).toContain('response-level competitive brand extraction')
      expect(denominator).toContain('competitive-set mentions')
      expect(failure).toContain('target-only')
      expect(failure).toContain('stale aggregate')
    }
  })

  it('requires sentiment score, label, driver, and quote provenance for explanatory ok states', () => {
    const explanatorySentiment = APP_ANALYZER_CHART_CONTRACTS.filter((item) =>
      item.metricKey.includes('sentiment') &&
      (item.metricKey.includes('driver') ||
        item.metricKey.includes('topic') ||
        item.metricKey.includes('sample') ||
        item.metricKey.includes('keyword')),
    )
    expect(explanatorySentiment.length).toBeGreaterThan(0)

    for (const contract of explanatorySentiment) {
      const required = contract.requiredSourceFacts.join(' | ').toLowerCase()
      const partial = contract.visibleBehavior.partial.toLowerCase()
      expect(required).toContain('sentiment_score')
      expect(required).toContain('polarity label')
      expect(required).toContain('driver')
      expect(required).toContain('source quote')
      expect(partial).toContain('score-only')
    }
  })

  it('keeps the explicit acceptance coverage handles visible to downstream workers', () => {
    const requiredHandles = [
      'citation_share',
      'rank',
      'topic_heatmap',
      'product_metrics',
      'competitor_quadrant',
      'pano_geo_trend',
    ]
    const keys = APP_ANALYZER_CHART_CONTRACTS.map((item) => item.metricKey)

    for (const handle of requiredHandles) {
      expect(keys.some((key) => key.includes(handle)), `${handle} missing`).toBe(true)
    }
  })
})
