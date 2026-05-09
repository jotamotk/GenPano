/**
 * Unified API client (Phase 0 / ADR-014 — RFC 7807 errors)
 *
 * Wraps `fetch` with:
 *   • Bearer JWT injection from `localStorage('genpano_token')`
 *   • 401 → clear token + navigate to /login?redirect=...
 *   • RFC 7807 `application/problem+json` parsing
 *   • Accept-Language header from LocaleContext (browser nav.lang fallback)
 *
 * Usage:
 *   const project = await apiClient.get<Project>('/v1/projects/abc')
 *   await apiClient.post('/v1/leads', { source: 'cta_modal', context: {...} })
 *
 * For React data fetching, prefer the hook layer (`useProjects`, `useBrand…`)
 * which wraps this in TanStack Query.
 */

const TOKEN_KEY = 'genpano_token'
const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')

const appBase = trimTrailingSlash(import.meta.env.BASE_URL || '')
const configuredApiBase = (import.meta.env as Record<string, string | undefined>).VITE_API_BASE
const API_BASE = trimTrailingSlash(configuredApiBase || `${appBase}/api` || '/api')

export interface ProblemDetails {
  type: string
  title: string
  status: number
  detail?: string
  code: string
  request_id?: string
  instance?: string
  [key: string]: unknown
}

/**
 * Errors thrown by the API client. Carries the full RFC 7807 body plus the
 * request metadata users need to copy when reporting an issue: request_id
 * (from `X-Request-ID` header), the call path, and the time the error fired.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly problem: ProblemDetails
  readonly requestId: string
  readonly path: string
  readonly timestamp: string

  constructor(
    problem: ProblemDetails,
    meta: { requestId?: string; path?: string } = {},
  ) {
    super(`${problem.code}: ${problem.title}${problem.detail ? ` (${problem.detail})` : ''}`)
    this.status = problem.status
    this.code = problem.code
    this.problem = problem
    this.requestId = meta.requestId || (typeof problem.request_id === 'string' ? problem.request_id : '') || ''
    this.path = meta.path || (typeof problem.instance === 'string' ? problem.instance : '') || ''
    this.timestamp = new Date().toISOString()
  }

  /** Check if this is a specific error code (FE i18n lookup helper). */
  is(code: string): boolean {
    return this.code === code
  }

  /**
   * Build a multi-line block users can paste into a bug report. Includes the
   * code, title, status, request_id, time, path, and any structured detail —
   * everything support needs to correlate with backend logs.
   */
  toCopyText(): string {
    const lines = [
      `[${this.code}] ${this.problem.title}`,
      `status: ${this.status}`,
      `request_id: ${this.requestId || '-'}`,
      `time: ${this.timestamp}`,
      `path: ${this.path || '-'}`,
    ]
    if (this.problem.detail) lines.push(`detail: ${this.problem.detail}`)
    if (typeof this.problem.field === 'string') lines.push(`field: ${this.problem.field}`)
    if (typeof this.problem.reason === 'string') lines.push(`reason: ${this.problem.reason}`)
    return lines.join('\n')
  }
}

function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function clearStoredToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // localStorage unavailable (SSR, sandbox) — silent
  }
}

function getAcceptLanguage(): string {
  try {
    const stored = localStorage.getItem('genpano_lang')
    if (stored === 'en') return 'en-US,en;q=0.9'
    if (stored === 'zh') return 'zh-CN,zh;q=0.9'
  } catch { /* fall through */ }
  return navigator.language || 'zh-CN'
}

interface RequestOptions extends RequestInit {
  /** If true, skip auth handling (for public landing endpoints). */
  skipAuth?: boolean
  /** Override token (for tests / OAuth callback hydration). */
  token?: string | null
}

async function parseProblem(res: Response): Promise<ProblemDetails> {
  try {
    const data = await res.json()
    if (data && typeof data === 'object' && 'code' in data) {
      return data as ProblemDetails
    }
    // Backward-compat: FastAPI default + legacy auth router return {detail: {...}}.
    // Preserve every field so callers can surface request_id, instance, retry_after, etc.
    const detail = (data as { detail?: Record<string, unknown> })?.detail
    if (detail && typeof detail === 'object' && 'code' in detail) {
      return {
        type: typeof detail.type === 'string' ? detail.type : 'about:blank',
        title: typeof detail.title === 'string'
          ? detail.title
          : (typeof detail.message === 'string' ? detail.message : res.statusText) || 'Error',
        status: typeof detail.status === 'number' ? detail.status : res.status,
        code: typeof detail.code === 'string' ? detail.code : 'unknown_error',
        ...detail,
      }
    }
    return {
      type: 'about:blank',
      title: res.statusText || 'Unknown error',
      status: res.status,
      code: 'unknown_error',
      detail: typeof data === 'string' ? data : JSON.stringify(data),
    }
  } catch {
    return {
      type: 'about:blank',
      title: res.statusText || 'Unknown error',
      status: res.status,
      code: 'unknown_error',
    }
  }
}

function buildApiError(res: Response, problem: ProblemDetails, url: string): ApiError {
  const requestId = res.headers.get('X-Request-ID') || ''
  return new ApiError(problem, { requestId, path: url })
}

// Public/auth surfaces where we must NOT redirect on 401 — those routes
// already render their own auth UI, and redirecting would loop forever
// (the redirect target itself triggers another 401 → redirect, with the
// `redirect` query string URL-encoded each iteration until the URL grows
// past server limits and the rate limiter trips → 429).
const PUBLIC_AUTH_PATHS = new Set([
  '/',
  '/login',
  '/auth',
  '/register',
  '/forgot',
  '/forgot-password',
  '/email-sent',
  '/setup',
  '/reset-password',
  '/reset-password-success',
  '/auth/callback',
])

function handleUnauthorized(): void {
  clearStoredToken()
  if (typeof window === 'undefined') return
  const path = window.location.pathname
  if (PUBLIC_AUTH_PATHS.has(path)) {
    // Already on a public/auth page — clearing the stale token is enough.
    return
  }
  const redirect = encodeURIComponent(path + window.location.search)
  // Use replace to avoid adding 401 page to history
  window.location.replace(`/login?redirect=${redirect}`)
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  headers.set('Accept-Language', getAcceptLanguage())

  const token = options.token !== undefined ? options.token : getStoredToken()
  if (!options.skipAuth && token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`

  let res: Response
  try {
    res = await fetch(url, { ...options, headers })
  } catch (err) {
    throw new ApiError(
      {
        type: 'about:blank',
        title: 'Network error',
        status: 0,
        code: 'network_error',
        detail: err instanceof Error ? err.message : String(err),
      },
      { path: url },
    )
  }

  if (res.status === 401 && !options.skipAuth) {
    handleUnauthorized()
    throw buildApiError(res, await parseProblem(res), url)
  }
  if (!res.ok) {
    throw buildApiError(res, await parseProblem(res), url)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

export const apiClient = {
  get<T>(path: string, opts?: RequestOptions): Promise<T> {
    return request<T>(path, { ...opts, method: 'GET' })
  },
  post<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...opts,
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  },
  patch<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...opts,
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  },
  put<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...opts,
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  },
  delete<T>(path: string, opts?: RequestOptions): Promise<T> {
    return request<T>(path, { ...opts, method: 'DELETE' })
  },
}

export { API_BASE }
