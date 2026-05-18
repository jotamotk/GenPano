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
  candidatesWithAnalyzerFacts: number
  maxRawTextCandidate: CandidateSummary | null
  selectedCandidate: CandidateSummary | null
  blockers: string[]
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

function assertCondition(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message)
}

function compactText(value: unknown) {
  return String(value ?? '').replace(/\s+/g, ' ').trim()
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
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

async function api(baseUrl: string, token: string, name: string, path: string) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9',
      },
    })
    const text = await response.text()
    if (response.status === 429 && attempt < 2) {
      let retryAfter = Number(response.headers.get('retry-after') || 0)
      try {
        const payload = text ? JSON.parse(text) : null
        retryAfter = Number(payload?.detail?.retry_after_seconds || payload?.detail?.retry_after || retryAfter)
      } catch {
        // Keep header-derived retryAfter if the payload is not JSON.
      }
      const waitMs = Math.max(1000, Math.min(35_000, retryAfter * 1000 || 2000))
      console.log(`LIVE_API_RATE_LIMIT_RETRY name=${name} attempt=${attempt + 1} wait_ms=${waitMs}`)
      await sleep(waitMs)
      continue
    }
    if (!response.ok) {
      throw new Error(`${name} ${path} -> HTTP ${response.status}: ${text.slice(0, 800)}`)
    }
    return text ? JSON.parse(text) : null
  }
  throw new Error(`${name} ${path} -> HTTP 429 after retries`)
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

function selectStrongestModalProbe(candidates: ModalProbe[]) {
  const candidatesWithFacts = candidates.filter(candidate => candidate.analyzerFactCount > 0)
  const pool = candidatesWithFacts.length ? candidatesWithFacts : candidates
  return [...pool].sort((left, right) => {
    if (right.rawTextLength !== left.rawTextLength) return right.rawTextLength - left.rawTextLength
    return right.analyzerFactCount - left.analyzerFactCount
  })[0] || null
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
  }

  for (const slice of candidateSlices()) {
    scan.scannedSlices += 1
    const params = dateParams(slice)
    const monitoring = await api(
      baseUrl,
      token,
      'topics_monitoring',
      `/api/v1/projects/${slice.projectId}/topics/monitoring?${params}`,
    )
    const topics = (Array.isArray(monitoring?.topics) ? monitoring.topics : [])
      .filter((topic: JsonMap) => Number(topic.response_count || 0) > 0)
    scan.scannedTopics += topics.length
    if (!topics.length) {
      blockers.push(`${slice.projectId}/${slice.brandId}: no topic rows with response_count > 0`)
      continue
    }

    for (const topic of topics) {
      const topicId = Number(topic.topic_id)
      const promptsPayload = await api(
        baseUrl,
        token,
        'topic_prompts',
        `/api/v1/projects/${slice.projectId}/topics/${topicId}/prompts?${params}`,
      )
      const prompts = (Array.isArray(promptsPayload?.items) ? promptsPayload.items : [])
        .filter((prompt: JsonMap) => Number(prompt.response_count || 0) > 0)
      scan.scannedPrompts += prompts.length
      for (const prompt of prompts) {
        const promptId = Number(prompt.prompt_id)
        const queriesPayload = await api(
          baseUrl,
          token,
          'prompt_queries',
          `/api/v1/projects/${slice.projectId}/prompts/${promptId}/queries?${params}`,
        )
        const queries = Array.isArray(queriesPayload?.items) ? queriesPayload.items : []
        scan.scannedQueries += queries.length
        for (const query of queries) {
          for (const attempt of queryAttempts(query)) {
            scan.scannedAttempts += 1
            const queryId = Number(attempt.query_id || query.query_id)
            if (!Number.isFinite(queryId)) continue
            const detail = await api(
              baseUrl,
              token,
              'query_response',
              `/api/v1/projects/${slice.projectId}/queries/${queryId}/response?brand_id=${slice.brandId}`,
            )
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
          }
        }
      }
    }

    const sliceCandidates = candidates.filter(candidate => candidate.projectId === slice.projectId && candidate.brandId === slice.brandId)
    const maxRawText = Math.max(0, ...sliceCandidates.map(candidate => candidate.rawTextLength))
    const withFacts = sliceCandidates.filter(candidate => candidate.analyzerFactCount > 0).length
    blockers.push(`${slice.projectId}/${slice.brandId}: scanned ${sliceCandidates.length} attempts; max_raw_text=${maxRawText}; with_analyzer_facts=${withFacts}`)
  }

  const selected = selectStrongestModalProbe(candidates)
  const maxRawTextCandidate = selectStrongestModalProbe([...candidates].sort((left, right) => right.rawTextLength - left.rawTextLength).slice(0, 1))
  const candidateSummary: CandidateScanSummary = {
    ...scan,
    candidatesWithAnalyzerFacts: candidates.filter(candidate => candidate.analyzerFactCount > 0).length,
    maxRawTextCandidate: maxRawTextCandidate ? summarizeCandidate(maxRawTextCandidate) : null,
    selectedCandidate: selected ? summarizeCandidate(selected) : null,
    blockers,
  }

  if (selected) {
    selected.candidateSummary = candidateSummary
    selected.fallbackReason =
      `Candidate scan complete: scanned_attempts=${scan.scannedAttempts}; ` +
      `selected_query_id=${selected.queryId}; selected_raw_text_length=${selected.rawTextLength}; ` +
      `selected_analyzer_fact_count=${selected.analyzerFactCount}; ` +
      `max_raw_text_query_id=${candidateSummary.maxRawTextCandidate?.queryId ?? '<none>'}; ` +
      `max_raw_text_length=${candidateSummary.maxRawTextCandidate?.rawTextLength ?? 0}; ` +
      `candidates_with_analyzer_facts=${candidateSummary.candidatesWithAnalyzerFacts}`
    return selected
  }
  throw new Error(`DATA_BLOCKER: no real response attempt could be selected for Response attempts modal. ${JSON.stringify(candidateSummary)}`)
}

async function openResponseAttemptsModal(page: Page, baseUrl: string, probe: ModalProbe) {
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
  await card.click()

  const modal = page.getByRole('dialog', { name: /Response attempts/i })
  await expect(modal).toBeVisible({ timeout: 15_000 })
  await expect(modal.getByRole('button', { name: /Close response attempts/i })).toBeVisible()
  return modal
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

    const modal = await openResponseAttemptsModal(page, baseUrl, probe)
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
      mainScroll: { before: mainBefore },
      analyzerScroll: { before: analyzerBefore },
    }
    await fs.writeFile(`${SCREENSHOT_DIR}/summary.json`, JSON.stringify(summaryPayload, null, 2))
    assertCondition(
      mainBefore.canScroll,
      `DATA_BLOCKER: strongest scanned response did not make the main response pane scrollable. candidate_summary=${JSON.stringify(probe.candidateSummary)} main=${JSON.stringify(mainBefore)}`,
    )

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
          mainScrollable: mainBefore.canScroll,
          analyzerScrollable: analyzerBefore.canScroll,
        }),
    )
  })
})
