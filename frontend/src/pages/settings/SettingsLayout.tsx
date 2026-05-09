import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useLocale } from '../../contexts/LocaleContext'

/* ─────────────────────────────────────────────────────────────
   SettingsLayout — sub-nav shell for /settings/*
   ─────────────────────────────────────────────────────────────
   The legacy single-page SettingsPage rendered Account / API Keys /
   MCP / Notifications as four cards stacked in one scroll container.
   That mixed unrelated concerns and made any deep-link awkward, so
   /settings is now a section with three sub-pages mounted under this
   layout. Each tab owns its own URL so the avatar dropdown can deep-link
   straight to e.g. /settings/api-keys.
*/

interface Tab {
  key: 'account' | 'api_keys' | 'notifications'
  to: string
}

const TABS: Tab[] = [
  { key: 'account', to: '/settings/account' },
  { key: 'api_keys', to: '/settings/api-keys' },
  { key: 'notifications', to: '/settings/notifications' },
]

export default function SettingsLayout() {
  const { t } = useLocale()
  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold text-themed-primary mb-1">
        {t('settings.page_title')}
      </h1>
      <p className="text-sm text-themed-muted mb-5">
        {t('settings.page_subtitle')}
      </p>

      <nav
        className="flex items-center gap-1 mb-6 border-b border-themed-card"
        aria-label={t('settings.nav.aria')}
      >
        {TABS.map((tab) => (
          <NavLink
            key={tab.key}
            to={tab.to}
            end
            className={({ isActive }) =>
              `relative px-4 py-2.5 text-sm font-medium transition-colors -mb-px border-b-2 ${
                isActive
                  ? 'text-themed-accent'
                  : 'text-themed-muted hover:text-themed-primary border-transparent'
              }`
            }
            style={({ isActive }) =>
              isActive
                ? { borderBottomColor: 'var(--color-accent)' }
                : { borderBottomColor: 'transparent' }
            }
          >
            {t(`settings.nav.${tab.key}`)}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
