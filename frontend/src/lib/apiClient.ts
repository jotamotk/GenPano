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
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly problem: ProblemDetails

  constructor(problem: ProblemDetails) {
    super(`${problem.code}: ${problem.title}${problem.detail ? ` (${problem.detail})` : ''}`)
    this.status = problem.status
    this.code = problem.code
    this.problem = problem
  }

  /** Check if this is a specific error code (FE i18n lookup helper). */
  is(code: string): boolean {
    return this.code === code
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
    // Backward-compat: legacy auth router returns {detail: {...}}
    const detail = (data as { detail?: { code?: string; message?: string } })?.detail
    if (detail && typeof detail === 'object' && 'code' in detail) {
      return {
        type: 'about:blank',
        title: detail.message || res.statusText,
        status: res.status,
        code: detail.code || 'unknown_error',
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

function handleUnauthorized(): void {
  clearStoredToken()
  if (typeof window !== 'undefined') {
    const redirect = encodeURIComponent(window.location.pathname + window.location.search)
    // Use replace to avoid adding 401 page to history
    window.location.replace(`/login?redirect=${redirect}`)
  }
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
    throw new ApiError({
      type: 'about:blank',
      title: 'Network error',
      status: 0,
      code: 'network_error',
      detail: err instanceof Error ? err.message : String(err),
    })
  }

  if (res.status === 401 && !options.skipAuth) {
    handleUnauthorized()
    throw new ApiError(await parseProblem(res))
  }
  if (!res.ok) {
    throw new ApiError(await parseProblem(res))
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
