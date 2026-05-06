/**
 * Centralised error → toast pipeline.
 *
 * Why this exists:
 *   • Many callers (TanStack Query global handlers, plain async helpers) live
 *     outside the React tree, so they cannot pull `pushToast` from
 *     `ProjectContext` directly.
 *   • Errors should always render with code + request_id + a copy-to-clipboard
 *     block so support can correlate with backend logs.
 *
 * The flow:
 *   1. `ProjectProvider` calls `registerToastPusher(pushToast)` once on mount.
 *   2. Anywhere in the app, callers do `showApiError(err)`.
 *   3. We format the error (resolving the i18n code map, building copy text)
 *      and forward it to the registered pusher with `duration: Infinity` so
 *      the user can read and copy it before dismissing.
 *
 * If no pusher is registered yet (e.g. during early bootstrap), errors fall
 * back to `console.error` so they are not silently swallowed.
 */
import { ApiError } from './apiClient'

export interface ErrorToastPayload {
  kind: 'error'
  /** Stable RFC 7807 code, displayed verbatim so support can search for it. */
  code: string
  /** Localised, user-facing one-liner. */
  title: string
  /** Optional secondary line (validation field/reason, etc.). */
  detail?: string
  /** Set when the response carried `X-Request-ID`. */
  requestId?: string
  /** Multi-line block ready to paste into a bug report. */
  copyText: string
  /** Compatibility with the existing toast shape. */
  message: string
  duration: number
}

type ToastPusher = (toast: ErrorToastPayload | Record<string, unknown>) => void

let pusher: ToastPusher | null = null

export function registerToastPusher(fn: ToastPusher | null): void {
  pusher = fn
}

/** Read access for legacy callers that need to push non-error toasts. */
export function getToastPusher(): ToastPusher | null {
  return pusher
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

function resolveTitle(err: ApiError, fallback?: string): string {
  // i18n lookup is done by the toast renderer (ToastViewport) which has
  // access to the live language. We fall back to whatever the backend sent,
  // then to the optional fallback string supplied by the caller.
  if (err.problem.title) return err.problem.title
  if (err.problem.detail) return err.problem.detail
  return fallback || err.message || 'Error'
}

export interface FormattedError {
  code: string
  title: string
  detail?: string
  requestId?: string
  status: number
  path: string
  timestamp: string
  copyText: string
}

export function formatApiError(err: unknown, fallback?: string): FormattedError {
  if (isApiError(err)) {
    return {
      code: err.code,
      title: resolveTitle(err, fallback),
      detail: typeof err.problem.detail === 'string' ? err.problem.detail : undefined,
      requestId: err.requestId || undefined,
      status: err.status,
      path: err.path,
      timestamp: err.timestamp,
      copyText: err.toCopyText(),
    }
  }
  // Non-ApiError throwable — still produce a copyable block.
  const timestamp = new Date().toISOString()
  const message = err instanceof Error ? err.message : String(err)
  const title = fallback || 'Unexpected error'
  const copyText = [
    `[unknown_error] ${title}`,
    `time: ${timestamp}`,
    `detail: ${message || '-'}`,
  ].join('\n')
  return {
    code: 'unknown_error',
    title,
    detail: message || undefined,
    status: 0,
    path: '',
    timestamp,
    copyText,
  }
}

export interface ShowApiErrorOptions {
  /** Substituted when no `errors.codes[code]` translation exists. */
  fallback?: string
  /**
   * Suppress the toast for `unauthorized` (the API client already redirects
   * to /login, so a flash of red is just noise).
   */
  silent401?: boolean
}

export function showApiError(err: unknown, opts: ShowApiErrorOptions = {}): void {
  if (opts.silent401 !== false && isApiError(err) && err.is('unauthorized')) {
    return
  }
  const formatted = formatApiError(err, opts.fallback)
  const payload: ErrorToastPayload = {
    kind: 'error',
    code: formatted.code,
    title: formatted.title,
    detail: formatted.detail,
    requestId: formatted.requestId,
    copyText: formatted.copyText,
    message: formatted.title,
    duration: Infinity,
  }
  if (pusher) {
    pusher(payload)
  } else {
    // Pre-mount errors (e.g. very early bootstrap) — at minimum surface in
    // the console so they are not invisible.
    console.error('[showApiError] toast pusher not yet registered:', formatted)
  }
}
