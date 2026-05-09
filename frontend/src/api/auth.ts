import { apiClient } from '../lib/apiClient'

/**
 * Auth API client.
 *
 * Routes through the shared `apiClient` so every request:
 *   • carries the standard headers (`Accept-Language`, `Authorization` from
 *     the persisted JWT when present);
 *   • surfaces backend errors as the structured `ApiError` (with
 *     request_id, status, problem.code, etc.) so callers can render the
 *     copyable diagnostic panel instead of a bare "Unknown error" string;
 *   • participates in the same correlation pipeline as the rest of the app.
 */

export interface LoginResponse {
  token: string
  user: {
    id: string
    email: string
    name: string | null
    company: string | null
    role?: string
    provider?: string
    emailVerified?: boolean
    locale?: 'zh-CN' | 'en-US'
  }
}

export interface RegisterResponse {
  message: string
  email: string
  previewUrl?: string | null
}

export interface MeResponse {
  id: string
  email: string
  name: string | null
  company: string | null
  role?: string
  provider?: string
  emailVerified?: boolean
  locale?: 'zh-CN' | 'en-US'
  createdAt: string
}

export interface LookupResponse {
  next: 'register' | 'login'
  exists: boolean
  hasPassword: boolean
  provider: 'email' | 'google' | null
  localeHint: 'zh-CN' | 'en-US' | null
}

export interface SetupTokenResponse {
  email: string
  provider: 'email' | 'google'
  name: string | null
  company: string | null
  requiresPassword: boolean
  tokenType: 'verify_email' | 'oauth_setup'
}

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')
const appBase = trimTrailingSlash(import.meta.env.BASE_URL || '')
const configuredApiBase = (import.meta.env as Record<string, string | undefined>).VITE_API_BASE
const API_BASE = trimTrailingSlash(configuredApiBase || `${appBase}/api` || '/api')

export const authApi = {
  async register(email: string): Promise<RegisterResponse> {
    return apiClient.post<RegisterResponse>('/auth/register', { email }, { skipAuth: true })
  },

  async lookup(email: string): Promise<LookupResponse> {
    return apiClient.post<LookupResponse>('/auth/lookup', { email }, { skipAuth: true })
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    // skipAuth: avoid the global 401-redirect; LoginPage handles invalid
    // credentials inline.
    return apiClient.post<LoginResponse>('/auth/login', { email, password }, { skipAuth: true })
  },

  async forgotPassword(email: string): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>(
      '/auth/forgot-password',
      { email },
      { skipAuth: true },
    )
  },

  async getMe(token: string): Promise<MeResponse> {
    return apiClient.get<MeResponse>('/auth/me', { token })
  },

  getGoogleOAuthUrl(): string {
    return `${API_BASE}/auth/google`
  },

  async checkEmail(email: string): Promise<{ exists: boolean }> {
    return apiClient.get<{ exists: boolean }>(
      `/auth/check-email?email=${encodeURIComponent(email)}`,
      { skipAuth: true },
    )
  },

  async resendVerification(email: string): Promise<void> {
    await apiClient.post<void>('/auth/resend-verification', { email }, { skipAuth: true })
  },

  async getSetupToken(token: string): Promise<SetupTokenResponse> {
    return apiClient.get<SetupTokenResponse>(
      `/auth/setup-token?token=${encodeURIComponent(token)}`,
      { skipAuth: true },
    )
  },

  async setup(data: {
    token: string
    email: string
    password?: string
    name: string
    company: string
    newsletter: boolean
    locale?: 'zh-CN' | 'en-US'
  }): Promise<LoginResponse> {
    return apiClient.post<LoginResponse>('/auth/setup', data, { skipAuth: true })
  },

  async resetPassword(token: string, password: string): Promise<void> {
    await apiClient.post<void>('/auth/reset-password', { token, password }, { skipAuth: true })
  },
}
