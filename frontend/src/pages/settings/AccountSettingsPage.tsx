import React from 'react'
import { Card } from '../../components/ui'
import { useLocale } from '../../contexts/LocaleContext'
import { useAuth } from '../../contexts/AuthContext'

export default function AccountSettingsPage() {
  const { t, formatDate } = useLocale()
  const { user } = useAuth()

  const username = user?.name || t('user.profile_default_name')
  const email = user?.email || t('user.profile_default_email')

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-sm font-semibold text-themed-primary mb-5">
          {t('settings.account.title')}
        </h2>

        <div className="space-y-1">
          <div className="flex items-center justify-between py-4 border-b border-themed">
            <div className="text-sm text-themed-secondary">{t('settings.account.username')}</div>
            <div className="text-sm font-medium text-themed-primary">{username}</div>
          </div>

          <div className="flex items-center justify-between py-4 border-b border-themed">
            <div className="text-sm text-themed-secondary">{t('settings.account.email')}</div>
            <div className="text-sm font-medium text-themed-primary">{email}</div>
          </div>

          <div className="flex items-center justify-between py-4">
            <div className="text-sm text-themed-secondary">{t('settings.account.registered_date')}</div>
            <div className="text-sm font-medium text-themed-primary tabular-nums">
              {formatDate('2026-04-01')}
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}
