import { useState } from 'react'
import { Card } from '../../components/ui'
import { useLocale } from '../../contexts/LocaleContext'
import { useNotifications, useUpdateNotifications } from '../../hooks/useNotifications'

/* ─────────────────────────────────────────────────────────────
   NotificationsSettingsPage — toggles persisted via
   PATCH /v1/users/me/notifications (Phase N).

   Optimistic update + rollback on failure (rate limit / 401 /
   network). Pre-load default (all off) until the GET resolves.
   ───────────────────────────────────────────────────────────── */
export default function NotificationsSettingsPage() {
  const { t } = useLocale()
  const { data: prefs } = useNotifications()
  const updatePrefs = useUpdateNotifications()

  const [localToggles, setLocalToggles] = useState({
    p0p1Alerts: true,
    weeklyReport: true,
    competitorAlert: false,
  })
  const toggles = prefs
    ? {
        p0p1Alerts: prefs.p0p1_alerts,
        weeklyReport: prefs.weekly_report,
        competitorAlert: prefs.competitor_alert,
      }
    : localToggles

  const toggleSwitch = (key: 'p0p1Alerts' | 'weeklyReport' | 'competitorAlert') => {
    const next = !toggles[key]
    setLocalToggles((prev) => ({ ...prev, [key]: next }))
    if (!prefs) return
    const apiKey =
      key === 'p0p1Alerts'
        ? 'p0p1_alerts'
        : key === 'weeklyReport'
          ? 'weekly_report'
          : 'competitor_alert'
    updatePrefs.mutate({ [apiKey]: next })
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold text-themed-primary mb-5">
        {t('settings.notifications.title')}
      </h2>

      <div className="space-y-4">
        <div className="flex items-center justify-between py-4 border-b border-themed">
          <div>
            <div className="text-sm font-medium text-themed-primary">
              {t('settings.notifications.p0p1_alerts_title')}
            </div>
            <div className="text-xs text-themed-muted mt-1">
              {t('settings.notifications.p0p1_alerts_hint')}
            </div>
          </div>
          <Toggle
            checked={toggles.p0p1Alerts}
            onChange={() => toggleSwitch('p0p1Alerts')}
          />
        </div>

        <div className="flex items-center justify-between py-4 border-b border-themed">
          <div>
            <div className="text-sm font-medium text-themed-primary">
              {t('settings.notifications.weekly_report_title')}
            </div>
            <div className="text-xs text-themed-muted mt-1">
              {t('settings.notifications.weekly_report_hint')}
            </div>
          </div>
          <Toggle
            checked={toggles.weeklyReport}
            onChange={() => toggleSwitch('weeklyReport')}
          />
        </div>

        <div className="flex items-center justify-between py-4">
          <div>
            <div className="text-sm font-medium text-themed-primary">
              {t('settings.notifications.competitor_alert_title')}
            </div>
            <div className="text-xs text-themed-muted mt-1">
              {t('settings.notifications.competitor_alert_hint')}
            </div>
          </div>
          <Toggle
            checked={toggles.competitorAlert}
            onChange={() => toggleSwitch('competitorAlert')}
          />
        </div>
      </div>
    </Card>
  )
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      style={{
        position: 'relative',
        display: 'inline-flex',
        height: '1.5rem',
        width: '2.75rem',
        borderRadius: '9999px',
        background: checked ? 'var(--color-accent)' : 'var(--color-border-strong)',
        border: 'none',
        cursor: 'pointer',
        transition: 'background-color 0.2s',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          height: '1.25rem',
          width: '1.25rem',
          borderRadius: '9999px',
          background: 'white',
          transform: checked ? 'translateX(1.25rem)' : 'translateX(0.125rem)',
          transition: 'transform 0.2s',
          marginTop: '0.125rem',
        }}
      />
    </button>
  )
}
