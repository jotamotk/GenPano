/**
 * API key hooks — wrap /v1/users/me/api-keys (Phase M).
 *
 * The `secret` field on the create response is only returned *once* at
 * creation time. The mutation hook surfaces it via mutation.data so the
 * page can display it in a one-time copy modal before invalidating the
 * list query (which refetches without the secret).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  apiKeysApi,
  type ApiKeyCreated,
  type ApiKeyIn,
  type ApiKeyListOut,
} from '../api/apiKeys'

export const API_KEYS_QUERY_KEY = ['api-keys'] as const

export function useApiKeys() {
  return useQuery<ApiKeyListOut>({
    queryKey: API_KEYS_QUERY_KEY,
    queryFn: () => apiKeysApi.list(),
    staleTime: 30 * 1000,
    retry: false,
  })
}

export function useCreateApiKey() {
  const qc = useQueryClient()
  return useMutation<ApiKeyCreated, Error, ApiKeyIn>({
    mutationFn: (payload) => apiKeysApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_QUERY_KEY })
    },
  })
}

export function useRevokeApiKey() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiKeysApi.revoke(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: API_KEYS_QUERY_KEY })
    },
  })
}
