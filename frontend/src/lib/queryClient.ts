/**
 * Shared TanStack Query client.
 *
 * Centralising defaults here lets us route every unhandled mutation/query
 * error through `showApiError`, which is the only way to consistently render
 * the structured error panel + copy block. Previously many `useMutation`
 * calls had no `onError`, so failures were invisible.
 *
 * Per-call opt-out: pass `meta: { silentError: true }` when you want to handle
 * the error locally without the global toast.
 *
 * Retry policy (#1031):
 *   • 502 / 503 / 504 + plain network errors → one retry with 600 ms backoff.
 *     These are typically transient (load-balancer flapping, cold worker,
 *     brief connection blip) and the page has no way to recover without it.
 *   • 4xx and other errors → no retry. A 400/401/403/404 will not change on
 *     a second attempt and retrying just delays the visible error.
 *   • Individual hooks can still opt out by passing `retry: false`.
 */
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { ApiError } from './apiClient'
import { showApiError } from './showApiError'

interface SilencableMeta {
  silentError?: boolean
}

function shouldSilence(meta: unknown): boolean {
  return Boolean((meta as SilencableMeta | undefined)?.silentError)
}

const TRANSIENT_STATUSES = new Set([502, 503, 504])

function isTransient(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 0 || err.code === 'network_error') return true
    return TRANSIENT_STATUSES.has(err.status)
  }
  return false
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      retry: (failureCount, err) => failureCount < 1 && isTransient(err),
      retryDelay: 600,
      refetchOnWindowFocus: false,
    },
  },
  queryCache: new QueryCache({
    onError: (err, query) => {
      if (shouldSilence(query.meta)) return
      showApiError(err)
    },
  }),
  mutationCache: new MutationCache({
    onError: (err, _vars, _ctx, mutation) => {
      if (shouldSilence(mutation.meta)) return
      showApiError(err)
    },
  }),
})
