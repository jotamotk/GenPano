/**
 * User API keys (Phase M).
 *
 *   GET    /v1/users/me/api-keys
 *   POST   /v1/users/me/api-keys        — secret returned ONCE at creation
 *   DELETE /v1/users/me/api-keys/:id
 *   GET    /v1/users/me/api-keys/:id/usage
 */
import { apiClient } from '../lib/apiClient'

export interface ApiKeyOut {
  id: string
  user_id: string
  name: string | null
  prefix: string
  scope: Record<string, unknown> | null
  rate_limit_per_minute: number
  usage_count: number
  last_used_at: string | null
  expires_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface ApiKeyListOut {
  items: ApiKeyOut[]
  total: number
}

export interface ApiKeyCreated {
  id: string
  prefix: string
  secret: string
  name: string | null
  rate_limit_per_minute: number
  created_at: string
  expires_at: string | null
}

export interface ApiKeyIn {
  name?: string | null
  rate_limit_per_minute?: number
  expires_at?: string | null
  scope?: Record<string, unknown> | null
}

export const apiKeysApi = {
  list(): Promise<ApiKeyListOut> {
    return apiClient.get<ApiKeyListOut>('/v1/users/me/api-keys')
  },
  create(payload: ApiKeyIn = {}): Promise<ApiKeyCreated> {
    return apiClient.post<ApiKeyCreated>('/v1/users/me/api-keys', payload)
  },
  revoke(id: string): Promise<void> {
    return apiClient.delete<void>(`/v1/users/me/api-keys/${id}`)
  },
}
