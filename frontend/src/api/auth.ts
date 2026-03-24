import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export interface LoginResponse {
  token: string
  user: {
    id: number
    email: string
    name: string | null
    company: string | null
  }
}

export interface RegisterResponse {
  message: string
  email: string
}

export interface MeResponse {
  id: number
  email: string
  name: string | null
  company: string | null
  createdAt: string
}

export const authApi = {
  async register(email: string): Promise<RegisterResponse> {
    const res = await api.post('/auth/register', { email })
    return res.data
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    const res = await api.post('/auth/login', { email, password })
    return res.data
  },

  async forgotPassword(email: string): Promise<{ message: string }> {
    const res = await api.post('/auth/forgot-password', { email })
    return res.data
  },

  async getMe(token: string): Promise<MeResponse> {
    const res = await api.get('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return res.data
  },

  getGoogleOAuthUrl(): string {
    return '/api/auth/google'
  },

  async checkEmail(email: string): Promise<{ exists: boolean }> {
    const res = await api.get(`/auth/check-email?email=${encodeURIComponent(email)}`)
    return res.data
  },

  async resendVerification(email: string): Promise<void> {
    await api.post('/auth/resend-verification', { email })
  },

  async setup(data: {
    token: string
    email: string
    password: string
    name: string
    company: string
    newsletter: boolean
  }): Promise<LoginResponse> {
    const res = await api.post('/auth/setup', data)
    return res.data
  },

  async resetPassword(token: string, password: string): Promise<void> {
    await api.post('/auth/reset-password', { token, password })
  },
}

// Response interceptor for consistent error handling
api.interceptors.response.use(
  res => res,
  err => {
    const message = err.response?.data?.message || err.message || 'Unknown error'
    return Promise.reject(new Error(message))
  }
)
