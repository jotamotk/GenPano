import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useLocale } from '../contexts/LocaleContext'

/* ─────────────────────────────────────────────────────────────
   UserMenu — topbar avatar dropdown (account / settings / logout)
   ─────────────────────────────────────────────────────────────
   Anchored to the avatar button in DashboardLayout's Topbar. Click
   outside or press Escape to close. The Logout entry runs the 6-step
   AuthContext.logout() and then navigates to /login so the
   PublicOnly guard re-renders cleanly.
*/

interface MenuItem {
  key: 'account' | 'api_keys' | 'notifications' | 'project_settings'
  label: string
  path: string
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

function LogoutIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

export default function UserMenu() {
  const { t } = useLocale()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const items: MenuItem[] = [
    { key: 'account', label: t('user_menu.account'), path: '/settings/account' },
    { key: 'api_keys', label: t('user_menu.api_keys'), path: '/settings/api-keys' },
    { key: 'notifications', label: t('user_menu.notifications'), path: '/settings/notifications' },
    { key: 'project_settings', label: t('user_menu.project_settings'), path: '/project-settings' },
  ]

  const handleNavigate = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  const handleLogout = async () => {
    if (busy) return
    setBusy(true)
    try {
      await logout()
      setOpen(false)
      navigate('/login', { replace: true })
    } finally {
      setBusy(false)
    }
  }

  const displayName = user?.name || user?.email || t('user_menu.guest')
  const avatarLetter = (user?.name?.[0] || user?.email?.[0] || 'U').toUpperCase()

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 h-9 pl-1 pr-2 rounded-pill hover:bg-themed-subtle transition-colors"
        aria-label={t('topbar.user_menu.aria')}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <div
          className="w-8 h-8 rounded-card flex items-center justify-center text-sm font-bold text-themed-accent"
          style={{ background: 'var(--gradient-avatar-warm)' }}
        >
          {avatarLetter}
        </div>
        <span className="text-themed-muted">
          <ChevronIcon />
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-2 w-60 rounded-card overflow-hidden z-50"
          style={{
            background: 'var(--color-bg-elevated, var(--color-bg-card))',
            border: '1px solid var(--color-border)',
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.18)',
          }}
        >
          <div className="px-4 py-3 border-b border-themed-card">
            <div className="text-sm font-semibold text-themed-primary truncate">
              {displayName}
            </div>
            {user?.email && (
              <div className="text-xs text-themed-muted truncate mt-0.5">
                {user.email}
              </div>
            )}
          </div>

          <div className="py-1.5">
            {items.map((item) => (
              <button
                key={item.key}
                role="menuitem"
                onClick={() => handleNavigate(item.path)}
                className="w-full text-left px-4 py-2 text-sm text-themed-secondary hover:bg-themed-subtle hover:text-themed-primary transition-colors"
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="border-t border-themed-card py-1.5">
            <button
              role="menuitem"
              onClick={handleLogout}
              disabled={busy}
              className="w-full flex items-center gap-2 px-4 py-2 text-sm text-themed-secondary hover:bg-themed-subtle hover:text-themed-primary transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <LogoutIcon />
              <span>{busy ? t('user_menu.logging_out') : t('user_menu.logout')}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
