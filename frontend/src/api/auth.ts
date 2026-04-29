const API_BASE = '/api'

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

async function parseError(res: Response): Promise<Error> {
  try {
    const data = await res.json()
    const message =
      data?.message ||
      data?.detail?.message ||
      data?.detail?.reason ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      res.statusText
    return new Error(message)
  } catch {
    return new Error(res.statusText || 'Unknown error')
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const authApi = {
  async register(email: string): Promise<RegisterResponse> {
    return request<RegisterResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async lookup(email: string): Promise<LookupResponse> {
    return request<LookupResponse>('/auth/lookup', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  async forgotPassword(email: string): Promise<{ message: string }> {
    return request<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async getMe(token: string): Promise<MeResponse> {
    return request<MeResponse>('/auth/me', { method: 'GET' }, token)
  },

  getGoogleOAuthUrl(): string {
    return '/api/auth/google'
  },

  async checkEmail(email: string): Promise<{ exists: boolean }> {
    return request<{ exists: boolean }>(`/auth/check-email?email=${encodeURIComponent(email)}`)
  },

  async resendVerification(email: string): Promise<void> {
    await request<void>('/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async getSetupToken(token: string): Promise<SetupTokenResponse> {
    return request<SetupTokenResponse>(`/auth/setup-token?token=${encodeURIComponent(token)}`)
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
    return request<LoginResponse>('/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async resetPassword(token: string, password: string): Promise<void> {
    await request<void>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    })
  },
}
