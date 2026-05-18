import crypto from 'node:crypto'
import fs from 'node:fs/promises'

import { expect, test, type Locator, type Page } from '@playwright/test'

type JsonMap = Record<string, any>

type LiveSlice = {
  projectId: string
  brandId: number
  brandName?: string
  competitorId: number
  fromDate: string
  toDate: string
}

type ModalProbe = LiveSlice & {
  topicId: number
  promptId: number
  queryText: string
  queryId: number
  rawTextLength: number
  analyzerFactCount: number
  candidateSummary?: CandidateScanSummary
  fallbackReason?: string
}

type CandidateScanSummary = {
  scannedSlices: number
  scannedTopics: number
  scannedPrompts: number
  scannedQueries: number
  scannedAttempts: number
  skippedDuplicateAttempts: number
  queryResponseRequests: number
  queryResponseErrors: number
  listEndpointErrors: number
  candidatesWithAnalyzerFacts: number
  categoryCounts: CandidateCategoryCounts
  maxRawTextCandidate: CandidateSummary | null
  selectedCandidate: CandidateSummary | null
  blockers: string[]
}

type CandidateCategoryCounts = {
  healthyResponseCandidates: number
  unhealthyResponseCandidates: number
  unhealthyListEndpoints: number
  rateLimitBlockers: number
  duplicateAttemptsSkipped: number
}

type CandidateSummary = {
  projectId: string
  brandId: number
  brandName?: string
  fromDate: string
  toDate: string
  topicId: number
  promptId: number
  queryId: number
  rawTextLength: number
  analyzerFactCount: number
}

const DEFAULT_OWNER_USER_ID = 'fe25eff1-8462-43eb-a027-bc8eb2c3db81'
const DEFAULT_PROJECT_ID = '95d43022-a5c8-5944-b6d6-34b29faa18b5'
const DEFAULT_BRAND_ID = 12
const DEFAULT_COMPETITOR_ID = 2
const DEFAULT_FROM_DATE = '2026-04-24'
const DEFAULT_TO_DATE = '2026-05-07'
const SCREENSHOT_DIR = 'test-results/live-app-topics-response-modal-scroll'
const MIN_RAW_TEXT_LENGTH = Number(process.env.MIN_RESPONSE_MODAL_RAW_TEXT_LENGTH || 1200)
const MIN_ANALYZER_FACTS_FOR_SCROLL = Number(process.env.MIN_ANALYZER_FACTS_FOR_SCROLL || 12)
const LIVE_API_THROTTLE_MS = Number(process.env.APP_TOPICS_RESPONSE_MODAL_API_THROTTLE_MS || 250)
const LIVE_API_RATE_LIMIT_RETRIES = Number(process.env.APP_TOPICS_RESPONSE_MODAL_RATE_LIMIT_RETRIES || 3)
const LIVE_API_RATE_LIMIT_BUFFER_MS = Number(process.env.APP_TOPICS_RESPONSE_MODAL_RATE_LIMIT_BUFFER_MS || 1500)
const LIVE_API_RATE_LIMIT_MAX_WAIT_MS = Number(process.env.APP_TOPICS_RESPONSE_MODAL_RATE_LIMIT_MAX_WAIT_MS || 60_000)
const HIGH_CONFIDENCE_RAW_TEXT_LENGTH = Number(process.env.APP_TOPICS_RESPONSE_MODAL_HIGH_CONFIDENCE_RAW_TEXT_LENGTH || 4000)

class RateLimitBlockerError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RateLimitBlockerError'
  }
}

function assertCondition(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message)
}

function compactText(value: unknown) {
  return String(value ?? '').replace(/\s+/g, ' ').trim()
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function isRateLimitBlocker(error: unknown) {
  return error instanceof RateLimitBlockerError || (error instanceof Error && error.message.includes('RATE_LIMIT_BLOCKER'))
}

function jsonB64(value: unknown) {
  return Buffer.from(JSON.stringify(value)).toString('base64url')
}

function signJwt(userId: string, secret: string) {
  const now = Math.floor(Date.now() / 1000)
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = {
    sub: userId,
    email: 'app-topics-response-modal-e2e@example.invalid',
    iat: now,
    exp: now + 30 * 60,
    iss: 'genpano',
    aud: 'genpano-user-access',
  }
  const body = `${jsonB64(header)}.${jsonB64(payload)}`
  const signature = crypto.createHmac('sha256', secret).update(body).digest('base64url')
  return `${body}.${signature}`
}

function parseRetryAfterSeconds(response: Response, text: string) {
  let retryAfter = Number(response.headers.get('retry-after') || 0)
  try {
    const payload = text ? JSON.parse(text) : null
    const detail = payload?.detail || payload
    retryAfter = Number(detail?.retry_after_seconds || detail?.retry_after || retryAfter)
  } catch {
    // Keep header-derived retryAfter if the payload is not JSON.
  }
  return Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 0
}

async function api(baseUrl: string, token: string, name: string, path: string) {
  const maxAttempts = Math.max(1, LIVE_API_RATE_LIMIT_RETRIES + 1)
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let response: Response
    try {
      response = await fetch(`${baseUrl}${path}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const waitMs = Math.min(LIVE_API_RATE_LIMIT_MAX_WAIT_MS, 1000 + attempt * 1000)
      if (attempt < maxAttempts - 1) {
        console.log(
          'LIVE_API_NETWORK_RETRY ' +
            JSON.stringify({
              name,
              path,
              attempt: attempt + 1,
              maxRetries: LIVE_API_RATE_LIMIT_RETRIES,
              waitMs,
              error: message.slice(0, 240),
            }),
        )
        await sleep(waitMs)
        continue
      }
      throw new Error(`${name} ${path} -> NETWORK_ERROR after ${LIVE_API_RATE_LIMIT_RETRIES} retries: ${message.slice(0, 800)}`)
    }
    const text = await response.text()
    if (response.status === 429) {
      const retryAfterSeconds = parseRetryAfterSeconds(response, text)
      const waitMs = Math.max(
        1000,
        Math.min(
          LIVE_API_RATE_LIMIT_MAX_WAIT_MS,
          (retryAfterSeconds > 0 ? retryAfterSeconds * 1000 : 2000) + LIVE_API_RATE_LIMIT_BUFFER_MS,
        ),
      )
      if (attempt < maxAttempts - 1) {
        console.log(
          'LIVE_API_RATE_LIMIT_RETRY ' +
            JSON.stringify({
              name,
              path,
              attempt: attempt + 1,
              maxRetries: LIVE_API_RATE_LIMIT_RETRIES,
              retryAfterSeconds,
              waitMs,
            }),
        )
        await sleep(waitMs)
        continue
      }
      throw new RateLimitBlockerError(
        `RATE_LIMIT_BLOCKER: ${name} ${path} -> HTTP 429 after ${LIVE_API_RATE_LIMIT_RETRIES} retry-after retries: ${text.slice(0, 800)}`,
      )
    }
    if (!response.ok) {
      throw new Error(`${name} ${path} -> HTTP ${response.status}: ${text.slice(0, 800)}`)
    }
    return text ? JSON.parse(text) : null
  }
  throw new RateLimitBlockerError(`RATE_LIMIT_BLOCKER: ${name} ${path} -> HTTP 429 after retry loop exited`)
}

async function seedLiveAuth(page: Page, token: string, slice: LiveSlice) {
  await page.addInitScript(
    ({ token: seededToken, slice: seededSlice }) => {
      window.localStorage.setItem('genpano_token', seededToken)
      window.sessionStorage.setItem('genpano_onboarding_skipped', '1')
      window.localStorage.setItem('genpano_lang', 'zh')
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: seededSlice.projectId,
          primaryBrandId: Number(seededSlice.brandId),
          industryId: null,
          name: `${seededSlice.brandName || `Brand ${seededSlice.brandId}`} / App Analytics`,
          competitorBrandIds: [Number(seededSlice.competitorId)],
        }),
      )
    },
    { token, slice },
  )
}

function candidateSlices(): LiveSlice[] {
  const configured: LiveSlice = {
    projectId: process.env.PROJECT_ID || DEFAULT_PROJECT_ID,
    brandId: Number(process.env.BRAND_ID || DEFAULT_BRAND_ID),
    brandName: process.env.BRAND_NAME || process.env.BRAND_QUERY,
    competitorId: Number(process.env.COMPETITOR_ID || DEFAULT_COMPETITOR_ID),
    fromDate: process.env.FROM_DATE || DEFAULT_FROM_DATE,
    toDate: process.env.TO_DATE || DEFAULT_TO_DATE,
  }
  const fallback: LiveSlice = {
    projectId: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
    brandId: 24,
    brandName: 'bestCoffer',
    competitorId: 2,
    fromDate: '2026-05-06',
    toDate: '2026-05-13',
  }
  const seen = new Set<string>()
  return [configured, fallback].filter(slice => {
    const key = `${slice.projectId}:${slice.brandId}:${slice.fromDate}:${slice.toDate}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function dateParams(slice: LiveSlice) {
  return `from=${encodeURIComponent(slice.fromDate)}&to=${encodeURIComponent(slice.toDate)}&brand_id=${slice.brandId}`
}

function queryAttempts(query: JsonMap) {
  const daily = Array.isArray(query?.daily_latest) ? query.daily_latest : []
  return daily.length ? daily : query?.response_id ? [query] : []
}

function countAnalyzerFacts(detail: JsonMap) {
  const facts = detail?.analyzer_facts || {}
  return [
    facts.citations,
    facts.brands_mentioned,
    facts.products_features_attributes,
    facts.relations,
    facts.sentiment_drivers,
  ].reduce((total, value) => total + (Array.isArray(value) ? value.length : 0), 0)
}

function summarizeCandidate(probe: ModalProbe): CandidateSummary {
  return {
    projectId: probe.projectId,
    brandId: probe.brandId,
    brandName: probe.brandName,
    fromDate: probe.fromDate,
    toDate: probe.toDate,
    topicId: probe.topicId,
    promptId: probe.promptId,
    queryId: probe.queryId,
    rawTextLength: probe.rawTextLength,
    analyzerFactCount: probe.analyzerFactCount,
  }
}

function candidateScanSummary(
  scan: Omit<CandidateScanSummary, 'candidatesWithAnalyzerFacts' | 'categoryCounts' | 'maxRawTextCandidate' | 'selectedCandidate' | 'blockers'>,
  candidates: ModalProbe[],
  blockers: string[],
  overrides: Partial<CandidateCategoryCounts> = {},
): CandidateScanSummary {
  const selected = selectStrongestModalProbe(candidates)
  const maxRawTextCandidate = [...candidates].sort((left, right) => {
    if (right.rawTextLength !== left.rawTextLength) return right.rawTextLength - left.rawTextLength
    return right.analyzerFactCount - left.analyzerFactCount
  })[0]
  return {
    ...scan,
    candidatesWithAnalyzerFacts: candidates.filter(candidate => candidate.analyzerFactCount > 0).length,
    categoryCounts: {
      healthyResponseCandidates: candidates.length,
      unhealthyResponseCandidates: scan.queryResponseErrors,
      unhealthyListEndpoints: scan.listEndpointErrors,
      rateLimitBlockers: 0,
      duplicateAttemptsSkipped: scan.skippedDuplicateAttempts,
      ...overrides,
    },
    maxRawTextCandidate: maxRawTextCandidate ? summarizeCandidate(maxRawTextCandidate) : null,
    selectedCandidate: selected ? summarizeCandidate(selected) : null,
    blockers,
  }
}

function rateLimitWithPartialSummary(error: unknown, scan: Parameters<typeof candidateScanSummary>[0], candidates: ModalProbe[], blockers: string[]) {
  const message = error instanceof Error ? error.message : String(error)
  return new RateLimitBlockerError(
    `${message}; partial_candidate_summary=${JSON.stringify(candidateScanSummary(scan, candidates, blockers, { rateLimitBlockers: 1 }))}`,
  )
}

function selectStrongestModalProbe(candidates: ModalProbe[]) {
  const candidatesWithFacts = candidates.filter(candidate => candidate.analyzerFactCount > 0)
  const pool = candidatesWithFacts.length ? candidatesWithFacts : candidates
  return [...pool].sort((left, right) => {
    if (right.rawTextLength !== left.rawTextLength) return right.rawTextLength - left.rawTextLength
    return right.analyzerFactCount - left.analyzerFactCount
  })[0] || null
}

function isHighConfidenceCandidate(candidate: ModalProbe | null) {
  return Boolean(candidate && candidate.rawTextLength >= HIGH_CONFIDENCE_RAW_TEXT_LENGTH && candidate.analyzerFactCount > 0)
}

function attachCandidateSummary(selected: ModalProbe, candidateSummary: CandidateScanSummary, reason: string) {
  selected.candidateSummary = candidateSummary
  selected.fallbackReason =
    `${reason}: scanned_attempts=${candidateSummary.scannedAttempts}; ` +
    `selected_query_id=${selected.queryId}; selected_raw_text_length=${selected.rawTextLength}; ` +
    `selected_analyzer_fact_count=${selected.analyzerFactCount}; ` +
    `max_raw_text_query_id=${candidateSummary.maxRawTextCandidate?.queryId ?? '<none>'}; ` +
    `max_raw_text_length=${candidateSummary.maxRawTextCandidate?.rawTextLength ?? 0}; ` +
    `candidates_with_analyzer_facts=${candidateSummary.candidatesWithAnalyzerFacts}`
  return selected
}

async function findModalProbe(baseUrl: string, token: string): Promise<ModalProbe> {
  const blockers: string[] = []
  const candidates: ModalProbe[] = []
  const scan = {
    scannedSlices: 0,
    scannedTopics: 0,
    scannedPrompts: 0,
    scannedQueries: 0,
    scannedAttempts: 0,
    skippedDuplicateAttempts: 0,
    queryResponseRequests: 0,
    queryResponseErrors: 0,
    listEndpointErrors: 0,
  }
  const seenQueryResponses = new Set<string>()

  for (const slice of candidateSlices()) {
    scan.scannedSlices += 1
    const params = dateParams(slice)
    let monitoring: JsonMap
    try {
      monitoring = await api(
        baseUrl,
        token,
        'topics_monitoring',
        `/api/v1/projects/${slice.projectId}/topics/monitoring?${params}`,
      )
    } catch (error) {
      if (isRateLimitBlocker(error)) throw rateLimitWithPartialSummary(error, scan, candidates, blockers)
      scan.listEndpointErrors += 1
      const message = error instanceof Error ? error.message : String(error)
      blockers.push(`${slice.projectId}/${slice.brandId}: skipped slice monitoring endpoint error: ${message.slice(0, 240)}`)
      console.log(
        `TOPICS_MODAL_LIST_ENDPOINT_SKIP ${JSON.stringify({ projectId: slice.projectId, brandId: slice.brandId, endpoint: 'topics_monitoring', error: message.slice(0, 300) })}`,
      )
      continue
    }
    const topics = (Array.isArray(monitoring?.topics) ? monitoring.topics : [])
      .filter((topic: JsonMap) => Number(topic.response_count || 0) > 0)
    scan.scannedTopics += topics.length
    if (!topics.length) {
      blockers.push(`${slice.projectId}/${slice.brandId}: no topic rows with response_count > 0`)
      continue
    }

    for (const topic of topics) {
      const topicId = Number(topic.topic_id)
      let promptsPayload: JsonMap
      try {
        promptsPayload = await api(
          baseUrl,
          token,
          'topic_prompts',
          `/api/v1/projects/${slice.projectId}/topics/${topicId}/prompts?${params}`,
        )
      } catch (error) {
        if (isRateLimitBlocker(error)) throw rateLimitWithPartialSummary(error, scan, candidates, blockers)
        scan.listEndpointErrors += 1
        const message = error instanceof Error ? error.message : String(error)
        blockers.push(`${slice.projectId}/${slice.brandId}: skipped topic_id=${topicId} prompts endpoint error: ${message.slice(0, 240)}`)
        console.log(
          `TOPICS_MODAL_LIST_ENDPOINT_SKIP ${JSON.stringify({ projectId: slice.projectId, brandId: slice.brandId, topicId, endpoint: 'topic_prompts', error: message.slice(0, 300) })}`,
        )
        continue
      }
      const prompts = (Array.isArray(promptsPayload?.items) ? promptsPayload.items : [])
        .filter((prompt: JsonMap) => Number(prompt.response_count || 0) > 0)
      scan.scannedPrompts += prompts.length
      for (const prompt of prompts) {
        const promptId = Number(prompt.prompt_id)
        let queriesPayload: JsonMap
        try {
          queriesPayload = await api(
            baseUrl,
            token,
            'prompt_queries',
            `/api/v1/projects/${slice.projectId}/prompts/${promptId}/queries?${params}`,
          )
        } catch (error) {
          if (isRateLimitBlocker(error)) throw rateLimitWithPartialSummary(error, scan, candidates, blockers)
          scan.listEndpointErrors += 1
          const message = error instanceof Error ? error.message : String(error)
          blockers.push(`${slice.projectId}/${slice.brandId}: skipped prompt_id=${promptId} queries endpoint error: ${message.slice(0, 240)}`)
          console.log(
            `TOPICS_MODAL_LIST_ENDPOINT_SKIP ${JSON.stringify({ projectId: slice.projectId, brandId: slice.brandId, topicId, promptId, endpoint: 'prompt_queries', error: message.slice(0, 300) })}`,
          )
          continue
        }
        const queries = Array.isArray(queriesPayload?.items) ? queriesPayload.items : []
        scan.scannedQueries += queries.length
        for (const query of queries) {
          for (const attempt of queryAttempts(query)) {
            scan.scannedAttempts += 1
            const queryId = Number(attempt.query_id || query.query_id)
            if (!Number.isFinite(queryId)) continue
            const responseKey = `${slice.projectId}:${slice.brandId}:${queryId}`
            if (seenQueryResponses.has(responseKey)) {
              scan.skippedDuplicateAttempts += 1
              continue
            }
            seenQueryResponses.add(responseKey)
            const detailPath = `/api/v1/projects/${slice.projectId}/queries/${queryId}/response?brand_id=${slice.brandId}`
            let detail: JsonMap
            try {
              scan.queryResponseRequests += 1
              detail = await api(baseUrl, token, 'query_response', detailPath)
            } catch (error) {
              if (isRateLimitBlocker(error)) throw rateLimitWithPartialSummary(error, scan, candidates, blockers)
              scan.queryResponseErrors += 1
              const message = error instanceof Error ? error.message : String(error)
              const skipSummary = {
                projectId: slice.projectId,
                brandId: slice.brandId,
                topicId,
                promptId,
                queryId,
                error: message.slice(0, 300),
              }
              blockers.push(`${slice.projectId}/${slice.brandId}: skipped query_id=${queryId} detail error: ${message.slice(0, 240)}`)
              console.log(`TOPICS_MODAL_RESPONSE_DETAIL_SKIP ${JSON.stringify(skipSummary)}`)
              if (LIVE_API_THROTTLE_MS > 0) await sleep(LIVE_API_THROTTLE_MS)
              continue
            }
            if (LIVE_API_THROTTLE_MS > 0) await sleep(LIVE_API_THROTTLE_MS)
            const rawTextLength = compactText(detail?.response?.raw_text).length
            const analyzerFactCount = countAnalyzerFacts(detail)
            const probe: ModalProbe = {
              ...slice,
              topicId,
              promptId,
              queryText: compactText(attempt.query_text || query.query_text),
              queryId,
              rawTextLength,
              analyzerFactCount,
            }
            candidates.push(probe)
            const strongest = selectStrongestModalProbe(candidates)
            if (strongest?.queryId === probe.queryId) {
              console.log(`TOPICS_MODAL_STRONGEST_CANDIDATE ${JSON.stringify(summarizeCandidate(probe))}`)
            }
          }
        }
      }
    }

    const sliceCandidates = candidates.filter(candidate => candidate.projectId === slice.projectId && candidate.brandId === slice.brandId)
    const maxRawText = Math.max(0, ...sliceCandidates.map(candidate => candidate.rawTextLength))
    const withFacts = sliceCandidates.filter(candidate => candidate.analyzerFactCount > 0).length
    blockers.push(`${slice.projectId}/${slice.brandId}: scanned ${sliceCandidates.length} attempts; max_raw_text=${maxRawText}; with_analyzer_facts=${withFacts}`)
    console.log(
      'TOPICS_MODAL_CANDIDATE_SLICE_SUMMARY ' +
        JSON.stringify({
          projectId: slice.projectId,
          brandId: slice.brandId,
          fromDate: slice.fromDate,
          toDate: slice.toDate,
          sliceCandidates: sliceCandidates.length,
          maxRawText,
          withAnalyzerFacts: withFacts,
          scannedAttempts: scan.scannedAttempts,
          skippedDuplicateAttempts: scan.skippedDuplicateAttempts,
          queryResponseRequests: scan.queryResponseRequests,
          queryResponseErrors: scan.queryResponseErrors,
          listEndpointErrors: scan.listEndpointErrors,
        }),
    )
    const strongestSoFar = selectStrongestModalProbe(candidates)
    if (isHighConfidenceCandidate(strongestSoFar)) {
      const candidateSummary = candidateScanSummary(scan, candidates, blockers)
      console.log(`TOPICS_MODAL_HIGH_CONFIDENCE_CANDIDATE_STOP ${JSON.stringify(candidateSummary)}`)
      return attachCandidateSummary(strongestSoFar, candidateSummary, 'High-confidence candidate selected before exhausting fallback slices')
    }
  }

  const selected = selectStrongestModalProbe(candidates)
  const candidateSummary = candidateScanSummary(scan, candidates, blockers)
  console.log(`TOPICS_MODAL_CANDIDATE_SCAN_SUMMARY ${JSON.stringify(candidateSummary)}`)

  if (selected) {
    return attachCandidateSummary(selected, candidateSummary, 'Candidate scan complete')
  }
  throw new Error(`DATA_BLOCKER: no real response attempt could be selected for Response attempts modal. ${JSON.stringify(candidateSummary)}`)
}

type OpenedResponseModal = {
  modal: Locator
  responsePromise: Promise<any>
}

async function openResponseAttemptsModal(page: Page, baseUrl: string, probe: ModalProbe): Promise<OpenedResponseModal> {
  const route =
    `/brand/topics?brandId=${probe.brandId}&from=${encodeURIComponent(probe.fromDate)}` +
    `&to=${encodeURIComponent(probe.toDate)}&profileGroup=all` +
    `&topicId=${probe.topicId}&promptId=${probe.promptId}`
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.waitForLoadState('networkidle', { timeout: 25_000 }).catch(() => {})

  const groupCards = page.locator('div.cursor-pointer').filter({ hasText: /Logical query group/i })
  await expect(groupCards.first()).toBeVisible({ timeout: 25_000 })
  const cardTexts = await groupCards.evaluateAll(cards =>
    cards.map(card => String((card as HTMLElement).innerText || card.textContent || '').replace(/\s+/g, ' ').trim()),
  )
  const queryNeedle = probe.queryText.slice(0, 80)
  const selectedIndex = queryNeedle
    ? cardTexts.findIndex(text => text.includes(queryNeedle))
    : -1
  const card = groupCards.nth(selectedIndex >= 0 ? selectedIndex : 0)
  const responsePath = `/api/v1/projects/${probe.projectId}/queries/${probe.queryId}/response`
  const responsePromise = page
    .waitForResponse(
      response => {
        const url = response.url()
        return url.includes(responsePath) && url.includes(`brand_id=${probe.brandId}`)
      },
      { timeout: 45_000 },
    )
    .catch(error => error)
  await card.click()

  const modal = page.getByRole('dialog', { name: /Response attempts/i })
  await expect(modal).toBeVisible({ timeout: 15_000 })
  await expect(modal.getByRole('button', { name: /Close response attempts/i })).toBeVisible()
  return { modal, responsePromise }
}

async function waitForResponseModalLoaded(modal: Locator, responsePromise: Promise<any>, probe: ModalProbe) {
  const response = await responsePromise
  const apiEvidence = response && typeof response.status === 'function'
    ? {
        status: response.status(),
        ok: response.ok(),
        url: response.url(),
      }
    : {
        status: null,
        ok: false,
        error: response instanceof Error ? response.message : String(response),
      }

  if (apiEvidence.status && apiEvidence.status >= 500) {
    return {
      loaded: false,
      status: 'RESPONSE_ENDPOINT_BLOCKER',
      reason: 'selected_query_response_api_failed',
      apiEvidence,
    }
  }

  const loading = modal.getByText(/Loading response/i)
  const fullAnswer = modal.getByText(/Full LLM answer/i)
  const loadingHidden = await expect(loading).toBeHidden({ timeout: 45_000 }).then(() => true).catch(() => false)
  const fullAnswerVisible = await expect(fullAnswer).toBeVisible({ timeout: 45_000 }).then(() => true).catch(() => false)

  if (loadingHidden && fullAnswerVisible) {
    return {
      loaded: true,
      status: 'LOADED',
      reason: 'selected_response_content_loaded',
      apiEvidence,
      loadingHidden,
      fullAnswerVisible,
      queryId: probe.queryId,
    }
  }

  if (!apiEvidence.ok || !loadingHidden || !fullAnswerVisible) {
    return {
      loaded: false,
      status: 'RESPONSE_LOAD_BLOCKER',
      reason: 'selected_response_content_did_not_finish_loading',
      apiEvidence,
      loadingHidden,
      fullAnswerVisible,
    }
  }
}

async function scrollMetrics(locator: Locator) {
  return locator.evaluate(element => {
    const target = element as HTMLElement
    return {
      scrollTop: target.scrollTop,
      scrollHeight: target.scrollHeight,
      clientHeight: target.clientHeight,
      canScroll: target.scrollHeight > target.clientHeight + 8,
    }
  })
}

async function scrollToBottom(locator: Locator) {
  return locator.evaluate(element => {
    const target = element as HTMLElement
    target.scrollTop = target.scrollHeight
    return {
      scrollTop: target.scrollTop,
      scrollHeight: target.scrollHeight,
      clientHeight: target.clientHeight,
    }
  })
}

test.describe('Response modal candidate ranking', () => {
  test('selects the longest candidate with analyzer facts after scanning all candidates', () => {
    const base: LiveSlice = {
      projectId: 'project-a',
      brandId: 24,
      brandName: 'bestCoffer',
      competitorId: 2,
      fromDate: '2026-05-06',
      toDate: '2026-05-13',
    }
    const candidates: ModalProbe[] = [
      { ...base, topicId: 1, promptId: 10, queryId: 100, queryText: 'first threshold hit', rawTextLength: 1300, analyzerFactCount: 2 },
      { ...base, topicId: 2, promptId: 20, queryId: 200, queryText: 'strongest for scroll', rawTextLength: 4200, analyzerFactCount: 1 },
      { ...base, topicId: 3, promptId: 30, queryId: 300, queryText: 'long but no facts', rawTextLength: 9000, analyzerFactCount: 0 },
    ]

    expect(selectStrongestModalProbe(candidates)?.queryId).toBe(200)
  })
})

test.describe('Live App Topics response modal scroll gate', () => {
  test.describe.configure({ timeout: 300_000, retries: 0 })
  test.skip(process.env.APP_TOPICS_RESPONSE_MODAL_LIVE_E2E !== '1', 'Set APP_TOPICS_RESPONSE_MODAL_LIVE_E2E=1 to run against production.')

  test('opens a real Response attempts modal and keeps scroll panes bounded', async ({ page }) => {
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || 'http://116.62.36.173'
    const userId = process.env.OWNER_USER_ID || DEFAULT_OWNER_USER_ID
    const secret = process.env.USER_JWT_SECRET || process.env.JWT_SECRET || ''
    assertCondition(Buffer.byteLength(secret, 'utf8') >= 32, 'USER_JWT_SECRET/JWT_SECRET is missing or too short')
    const token = signJwt(userId, secret)
    console.log('::add-mask::' + token)

    const me = await api(baseUrl, token, 'auth_me', '/api/auth/me')
    assertCondition(me.id === userId, `auth/me returned unexpected user ${me.id}`)
    assertCondition(me.needs_onboarding !== true && me.needsOnboarding !== true, 'owner user still needs onboarding')

    const probe = await findModalProbe(baseUrl, token)
    if (probe.fallbackReason) console.log(`DATA_BLOCKER_FALLBACK ${probe.fallbackReason}`)

    await fs.mkdir(SCREENSHOT_DIR, { recursive: true })
    await seedLiveAuth(page, token, probe)

    const failedResponses: string[] = []
    page.on('response', response => {
      const url = response.url()
      const status = response.status()
      if (url.includes('/api/') && (status === 401 || status >= 500)) {
        failedResponses.push(`${status} ${url}`)
      }
    })

    const { modal, responsePromise } = await openResponseAttemptsModal(page, baseUrl, probe)
    const loadEvidence = await waitForResponseModalLoaded(modal, responsePromise, probe)
    if (!loadEvidence.loaded) {
      await modal.screenshot({ path: `${SCREENSHOT_DIR}/response-modal-load-blocked.png` })
      const loadBlocker = {
        status: loadEvidence.status,
        reason: loadEvidence.reason,
        selectedCandidate: probe.candidateSummary?.selectedCandidate,
        maxRawTextCandidate: probe.candidateSummary?.maxRawTextCandidate,
        projectId: probe.projectId,
        brandId: probe.brandId,
        topicId: probe.topicId,
        promptId: probe.promptId,
        queryId: probe.queryId,
        rawTextLength: probe.rawTextLength,
        analyzerFactCount: probe.analyzerFactCount,
        candidateSummary: probe.candidateSummary,
        loadEvidence,
        failedResponses,
      }
      await fs.writeFile(`${SCREENSHOT_DIR}/final-blocker.json`, JSON.stringify(loadBlocker, null, 2))
      console.log(`FINAL_TOPICS_RESPONSE_MODAL_LOAD_BLOCKER ${JSON.stringify(loadBlocker)}`)
      throw new Error(`${loadEvidence.status}: selected response did not load before scroll measurement. final_blocker=${JSON.stringify(loadBlocker)}`)
    }
    await modal.screenshot({ path: `${SCREENSHOT_DIR}/response-modal-open.png` })

    const modalBox = await modal.boundingBox()
    assertCondition(modalBox, 'Response attempts modal has no bounding box')
    const viewport = page.viewportSize()
    assertCondition(viewport, 'Playwright viewport is unavailable')
    expect(modalBox.x, 'modal left edge should stay in viewport').toBeGreaterThanOrEqual(0)
    expect(modalBox.y, 'modal top edge should stay in viewport').toBeGreaterThanOrEqual(0)
    expect(modalBox.x + modalBox.width, 'modal right edge should stay in viewport').toBeLessThanOrEqual(viewport.width + 1)
    expect(modalBox.y + modalBox.height, 'modal bottom edge should stay in viewport').toBeLessThanOrEqual(viewport.height + 1)

    const header = modal.locator('h3', { hasText: 'Response attempts' })
    const close = modal.getByRole('button', { name: /Close response attempts/i })
    const mainPane = modal.locator('main').first()
    const analyzerPane = modal.locator('aside').filter({ hasText: 'Analyzer facts' }).last()
    await expect(header).toBeVisible()
    await expect(close).toBeVisible()
    await expect(mainPane).toBeVisible()
    await expect(analyzerPane).toBeVisible()

    const mainBefore = await scrollMetrics(mainPane)
    const analyzerBefore = await scrollMetrics(analyzerPane)
    const summaryPayload = {
      baseUrl,
      projectId: probe.projectId,
      brandId: probe.brandId,
      topicId: probe.topicId,
      promptId: probe.promptId,
      queryId: probe.queryId,
      window: { from: probe.fromDate, to: probe.toDate },
      rawTextLength: probe.rawTextLength,
      analyzerFactCount: probe.analyzerFactCount,
      candidateSummary: probe.candidateSummary,
      loadEvidence,
      mainScroll: { before: mainBefore },
      analyzerScroll: { before: analyzerBefore },
    }
    await fs.writeFile(`${SCREENSHOT_DIR}/summary.json`, JSON.stringify(summaryPayload, null, 2))
    if (!mainBefore.canScroll) {
      const finalBlocker = {
        status: 'DATA_BLOCKER',
        reason: 'strongest_scanned_healthy_response_did_not_overflow_main_pane',
        categoryCounts: {
          healthyResponseCandidates: probe.candidateSummary?.categoryCounts.healthyResponseCandidates ?? 0,
          unhealthyResponseCandidates: probe.candidateSummary?.categoryCounts.unhealthyResponseCandidates ?? 0,
          unhealthyListEndpoints: probe.candidateSummary?.categoryCounts.unhealthyListEndpoints ?? 0,
          rateLimitBlockers: probe.candidateSummary?.categoryCounts.rateLimitBlockers ?? 0,
          duplicateAttemptsSkipped: probe.candidateSummary?.categoryCounts.duplicateAttemptsSkipped ?? 0,
          openedNonOverflowingCandidates: 1,
        },
        selectedCandidate: probe.candidateSummary?.selectedCandidate,
        maxRawTextCandidate: probe.candidateSummary?.maxRawTextCandidate,
        candidateSummary: probe.candidateSummary,
        loadEvidence,
        modalMetrics: {
          main: mainBefore,
          analyzer: analyzerBefore,
        },
      }
      await fs.writeFile(`${SCREENSHOT_DIR}/final-blocker.json`, JSON.stringify(finalBlocker, null, 2))
      console.log(`FINAL_TOPICS_RESPONSE_MODAL_SCROLL_BLOCKER ${JSON.stringify(finalBlocker)}`)
      throw new Error(`DATA_BLOCKER: strongest scanned response did not make the main response pane scrollable. final_blocker=${JSON.stringify(finalBlocker)}`)
    }

    const mainAfter = await scrollToBottom(mainPane)
    const analyzerAfter = analyzerBefore.canScroll ? await scrollToBottom(analyzerPane) : analyzerBefore
    expect(mainAfter.scrollTop, 'main response pane should move when scrolled').toBeGreaterThan(mainBefore.scrollTop)
    if (analyzerBefore.canScroll) {
      expect(analyzerAfter.scrollTop, 'Analyzer facts pane should move when scrolled').toBeGreaterThan(analyzerBefore.scrollTop)
    } else {
      expect(
        probe.analyzerFactCount,
        `Analyzer facts pane should only be required to overflow when enough facts exist. analyzer=${JSON.stringify(analyzerBefore)}`,
      ).toBeLessThan(MIN_ANALYZER_FACTS_FOR_SCROLL)
    }
    await expect(header).toBeVisible()
    await expect(close).toBeVisible()
    await modal.screenshot({ path: `${SCREENSHOT_DIR}/response-modal-scrolled.png` })

    assertCondition(!failedResponses.length, `live App had failing API responses:\n${failedResponses.join('\n')}`)
    await fs.writeFile(
      `${SCREENSHOT_DIR}/summary.json`,
      JSON.stringify(
        {
          baseUrl,
          projectId: probe.projectId,
          brandId: probe.brandId,
          topicId: probe.topicId,
          promptId: probe.promptId,
          queryId: probe.queryId,
          window: { from: probe.fromDate, to: probe.toDate },
          rawTextLength: probe.rawTextLength,
          analyzerFactCount: probe.analyzerFactCount,
          candidateSummary: probe.candidateSummary,
          loadEvidence,
          mainScroll: { before: mainBefore, after: mainAfter },
          analyzerScroll: { before: analyzerBefore, after: analyzerAfter },
        },
        null,
        2,
      ),
    )
    console.log(
      'FINAL_TOPICS_RESPONSE_MODAL_SCROLL_E2E_SUMMARY ' +
        JSON.stringify({
          projectId: probe.projectId,
          brandId: probe.brandId,
          topicId: probe.topicId,
          promptId: probe.promptId,
          queryId: probe.queryId,
          rawTextLength: probe.rawTextLength,
          analyzerFactCount: probe.analyzerFactCount,
          candidateSummary: probe.candidateSummary,
          loadEvidence,
          mainScrollable: mainBefore.canScroll,
          analyzerScrollable: analyzerBefore.canScroll,
        }),
    )
  })
})
