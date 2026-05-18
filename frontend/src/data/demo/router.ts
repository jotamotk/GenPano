/**
 * Demo router — matches API paths to bestcoffer fixtures.
 *
 * Returns a deep-cloned fixture on match; React Query will cache it and
 * subsequent mutations to the cached object won't pollute the fixture.
 * Returns null on no match so the apiClient falls through to live fetch.
 *
 * Only GET requests are routed here; writes go to backend untouched.
 */

import {
  COMPETITOR_METRICS,
  COMPETITOR_TRENDS_GEO,
  DIAGNOSTICS_FULL,
  INDUSTRY_RANKING,
  PRODUCTS,
  REPORTS,
  buildDiagnosticsResponse,
} from './bestcoffer'

function clone<T>(v: T): T {
  // Structured clone keeps Date/null/nested arrays intact; the fixture
  // is pure JSON so a JSON round-trip is also fine but slower.
  return typeof structuredClone === 'function'
    ? structuredClone(v)
    : (JSON.parse(JSON.stringify(v)) as T)
}

function parsePathAndQuery(path: string): { pathname: string; params: URLSearchParams } {
  const qIdx = path.indexOf('?')
  if (qIdx === -1) return { pathname: path, params: new URLSearchParams() }
  return {
    pathname: path.slice(0, qIdx),
    params: new URLSearchParams(path.slice(qIdx + 1)),
  }
}

const PROJECT_SCOPED_RE = /^\/v1\/projects\/[^/]+/
const INDUSTRY_SCOPED_RE = /^\/v1\/industries\/(\d+)/

/**
 * Try to match `path` (with query string) to a demo fixture.
 * Returns the response shape if matched, or null otherwise.
 */
export function tryMockResponse<T>(path: string, method: string): T | null {
  if (method.toUpperCase() !== 'GET') return null

  const { pathname, params } = parsePathAndQuery(path)

  // 行业排名 — /v1/industries/:id/ranking
  if (INDUSTRY_SCOPED_RE.test(pathname) && pathname.endsWith('/ranking')) {
    const match = pathname.match(INDUSTRY_SCOPED_RE)
    const industryId = match ? Number(match[1]) : 0
    const fixture = clone(INDUSTRY_RANKING)
    fixture.industry_id = industryId
    return fixture as unknown as T
  }

  // Project-scoped endpoints
  if (PROJECT_SCOPED_RE.test(pathname)) {
    const tail = pathname.replace(PROJECT_SCOPED_RE, '')

    // 竞品四象限 — /competitors/metrics
    if (tail === '/competitors/metrics') {
      return clone(COMPETITOR_METRICS) as unknown as T
    }

    // PANO 趋势 — /competitors/trends?metric=geo_score (also other metrics use same series shape)
    if (tail === '/competitors/trends') {
      const fixture = clone(COMPETITOR_TRENDS_GEO)
      const metric = params.get('metric')
      if (metric) fixture.metric = metric
      return fixture as unknown as T
    }

    // 产品组合 — /products
    if (tail === '/products') {
      return clone(PRODUCTS) as unknown as T
    }

    // 诊断 + 告警条 — /diagnostics or /diagnostics/ (with optional severity / limit filters)
    if (tail === '/diagnostics' || tail === '/diagnostics/') {
      const severity = params.get('severity')
      const limitRaw = params.get('limit')
      const limit = limitRaw ? Number(limitRaw) : null
      if (severity || (limit && limit > 0)) {
        return clone(buildDiagnosticsResponse(severity, limit)) as unknown as T
      }
      return clone(DIAGNOSTICS_FULL) as unknown as T
    }

    // 报告 — /reports
    if (tail === '/reports') {
      return clone(REPORTS) as unknown as T
    }
  }

  return null
}
