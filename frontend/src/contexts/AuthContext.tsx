import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { authApi } from '../api/auth'
import { track, reset as resetAnalytics } from '../lib/analytics'

interface User {
  id: string
  email: string
  name: string | null
  company: string | null
  role?: string
  provider?: string
  emailVerified?: boolean
  locale?: 'zh-CN' | 'en-US'
  // True when the user has zero non-deleted Project rows. Drives
  // RequireOnboarded → /onboarding redirect.
  needsOnboarding?: boolean
}

interface AuthContextValue {
  user: User | null
  token: string | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  setTokenAndUser: (token: string, user: User) => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem('genpano_token')
  )
  const [isLoading, setIsLoading] = useState(!!localStorage.getItem('genpano_token'))

  // Rehydrate user from token on mount
  useEffect(() => {
    const stored = localStorage.getItem('genpano_token')
    if (!stored) {
      setIsLoading(false)
      return
    }
    authApi.getMe(stored)
      .then(u => setUser(u))
      .catch(() => {
        localStorage.removeItem('genpano_token')
        setToken(null)
      })
      .finally(() => setIsLoading(false))
  }, [])

  const setTokenAndUser = useCallback((newToken: string, newUser: User) => {
    localStorage.setItem('genpano_token', newToken)
    setToken(newToken)
    setUser(newUser)
  }, [])

  // Re-fetch /auth/me without a full re-login. Used after onboarding so
  // the freshly-flipped `needsOnboarding=false` flag unblocks the guard.
  const refreshUser = useCallback(async () => {
    const stored = localStorage.getItem('genpano_token')
    if (!stored) return
    try {
      const u = await authApi.getMe(stored)
      setUser(u as User)
    } catch {
      /* swallow — caller can fall back to a hard reload if needed */
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password)
    setTokenAndUser(res.token, res.user)
  }, [setTokenAndUser])

  // Logout 6-step contract (Harness D2 `logout-6-step-order` — see lib/analytics.ts):
  //   server-revoke -> track('user_logged_out') -> mixpanel.reset() -> clear local
  //   token+user -> caller navigates. The track() must run before reset() so it
  //   still carries the current distinct_id; reset() must run before the local
  //   state clear so analytics see the same identity at logout time.
  const logout = useCallback(async () => {
    await authApi.logout()
    await track('user_logged_out')
    await resetAnalytics()
    localStorage.removeItem('genpano_token')
    try {
      window.sessionStorage?.removeItem('genpano_onboarding_skipped')
    } catch {
      /* ignore — non-critical */
    }
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, setTokenAndUser, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
