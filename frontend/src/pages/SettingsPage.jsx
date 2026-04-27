import { useState } from 'react';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';

/* ─────────────────────────────────────────────────────────────
   SettingsPage — PRD §4.10 国际化覆盖
   ─────────────────────────────────────────────────────────────
   所有 UI 文案通过 useLocale().t() 读取 messages.settings.*
   用户名 / 邮箱 / 注册时间 来自 LocaleContext 默认 user 对象
   (未来接入 auth 后替换为 useAuth() hook 输出).
*/
export default function SettingsPage() {
  const { t, locale, formatDate } = useLocale();

  const [toggles, setToggles] = useState({
    p0p1Alerts: true,
    weeklyReport: true,
    competitorAlert: false,
  });

  const toggleSwitch = (key) => {
    setToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Mock 用户资料 — 之后由 useAuth() 提供
  const user = {
    username: 'Frank Wang',
    email: t('user.profile_default_email'),
    registeredAt: '2026-04-01',
  };

  return (
    <>
      <div className="max-w-3xl space-y-6">
        {/* Account Card */}
        <Card>
          <h2 className="text-sm font-semibold text-themed-primary mb-5">
            {t('settings.account.title')}
          </h2>

          <div className="space-y-1">
            {/* Username Row */}
            <div className="flex items-center justify-between py-4 border-b border-themed">
              <div className="text-sm text-themed-secondary">{t('settings.account.username')}</div>
              <div className="text-sm font-medium text-themed-primary">{user.username}</div>
            </div>

            {/* Email Row */}
            <div className="flex items-center justify-between py-4 border-b border-themed">
              <div className="text-sm text-themed-secondary">{t('settings.account.email')}</div>
              <div className="text-sm font-medium text-themed-primary">{user.email}</div>
            </div>

            {/* Registration Date Row */}
            <div className="flex items-center justify-between py-4">
              <div className="text-sm text-themed-secondary">{t('settings.account.registered_date')}</div>
              <div className="text-sm font-medium text-themed-primary tabular-nums">
                {formatDate(user.registeredAt)}
              </div>
            </div>
          </div>
        </Card>

        {/* API Keys Card */}
        <Card>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-sm font-semibold text-themed-primary">{t('settings.api_keys.title')}</h2>
            <Button variant="primary" size="sm">
              {t('settings.api_keys.generate_new')}
            </Button>
          </div>

          <div
            style={{
              background: 'var(--color-bg-badge)',
              borderRadius: '0.5rem',
              padding: '1rem',
              border: '1px solid var(--color-border)',
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <code className="text-sm tabular-nums text-themed-secondary">
                gp_sk_****************************a3f7
              </code>
              <Button variant="secondary" size="sm">
                {t('settings.api_keys.copy')}
              </Button>
            </div>
            <div className="flex items-center justify-between text-xs text-themed-muted">
              <span>
                {t('settings.api_keys.created_at', { date: formatDate('2026-03-15') })}
              </span>
              <div className="flex items-center gap-2">
                <span>{t('settings.api_keys.usage', { used: 23, total: 100 })}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  style={{
                    background: 'var(--color-accent-subtle)',
                    color: 'var(--color-accent)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  {t('settings.api_keys.delete')}
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* MCP Server Card */}
        <Card>
          <h2 className="text-sm font-semibold text-themed-primary mb-2">
            {t('settings.mcp.title')}
          </h2>
          <p className="text-sm text-themed-secondary mb-4">{t('settings.mcp.description')}</p>

          <div
            style={{
              background: 'var(--color-bg-elevated)',
              borderRadius: '0.5rem',
              padding: '1rem',
              border: '1px solid var(--color-border)',
              overflow: 'auto',
            }}
          >
            <pre className="tabular-nums text-sm" style={{ color: 'var(--color-text-secondary)' }}>
{`{
  "mcpServers": {
    "genpano": {
      "url": "https://mcp.genpano.com/sse",
      "headers": { "Authorization": "Bearer gp_sk_..." }
    }
  }
}`}
            </pre>
          </div>
        </Card>

        {/* Notifications Card */}
        <Card>
          <h2 className="text-sm font-semibold text-themed-primary mb-5">
            {t('settings.notifications.title')}
          </h2>

          <div className="space-y-4">
            {/* Toggle 1: P0/P1 Alerts */}
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

            {/* Toggle 2: Weekly Report */}
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

            {/* Toggle 3: Competitor Alert */}
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
      </div>
    </>
  );
}

// Custom Toggle Component
function Toggle({ checked, onChange }) {
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
  );
}
