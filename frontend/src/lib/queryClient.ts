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
 */
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { showApiError } from './showApiError'

interface SilencableMeta {
  silentError?: boolean
}

function shouldSilence(meta: unknown): boolean {
  return Boolean((meta as SilencableMeta | undefined)?.silentError)
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      retry: 1,
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
