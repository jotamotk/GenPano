import { useState } from 'react';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useNotifications, useUpdateNotifications } from '../hooks/useNotifications';
import {
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
} from '../hooks/useApiKeys';

/* ─────────────────────────────────────────────────────────────
   SettingsPage — PRD §4.10 国际化覆盖
   ─────────────────────────────────────────────────────────────
   所有 UI 文案通过 useLocale().t() 读取 messages.settings.*
   用户名 / 邮箱 / 注册时间 来自 LocaleContext 默认 user 对象
   (未来接入 auth 后替换为 useAuth() hook 输出).

   Notifications toggles are persisted via PATCH /v1/users/me/notifications
   (Phase N) — optimistic update + rollback on failure (rate limit / 401 /
   network). Pre-load default (all off) until the GET resolves.
*/
export default function SettingsPage() {
  const { t, locale, formatDate } = useLocale();

  const { data: prefs, isLoading: prefsLoading } = useNotifications();
  const updatePrefs = useUpdateNotifications();

  // Backend prefs are the source of truth; while loading, fall back to
  // defaults so the UI doesn't flash wrong state.
  const [localToggles, setLocalToggles] = useState({
    p0p1Alerts: true,
    weeklyReport: true,
    competitorAlert: false,
  });
  const toggles = prefs
    ? {
        p0p1Alerts: prefs.p0p1_alerts,
        weeklyReport: prefs.weekly_report,
        competitorAlert: prefs.competitor_alert,
      }
    : localToggles;

  const toggleSwitch = (key: 'p0p1Alerts' | 'weeklyReport' | 'competitorAlert') => {
    const next = !toggles[key];
    setLocalToggles((prev) => ({ ...prev, [key]: next }));
    if (!prefs) return; // not loaded yet — local-only optimistic
    const apiKey =
      key === 'p0p1Alerts'
        ? 'p0p1_alerts'
        : key === 'weeklyReport'
          ? 'weekly_report'
          : 'competitor_alert';
    updatePrefs.mutate({ [apiKey]: next });
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

        {/* API Keys Card — Phase M live (POST /v1/users/me/api-keys) */}
        <ApiKeysCard t={t} formatDate={formatDate} />

        {/* MCP Server Card — config snippet uses the user's first key prefix */}
        <McpConfigCard t={t} />

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

/* ─────────────────────────────────────────────────────────────
   ApiKeysCard — wires Settings to /v1/users/me/api-keys (Phase M)
   ───────────────────────────────────────────────────────────── */
function ApiKeysCard({
  t,
  formatDate,
}: {
  t: (key: string, params?: Record<string, unknown>) => string;
  formatDate: (d: string | number | Date, opts?: Intl.DateTimeFormatOptions) => string;
}) {
  const { data, isLoading, error } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);

  const items = data?.items ?? [];

  const handleGenerate = () => {
    setRevealedSecret(null);
    createKey.mutate(
      { name: `key-${new Date().toISOString().slice(0, 10)}` },
      {
        onSuccess: (res) => setRevealedSecret(res.secret),
      }
    );
  };

  return (
    <Card>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-semibold text-themed-primary">
          {t('settings.api_keys.title')}
        </h2>
        <Button
          variant="primary"
          size="sm"
          onClick={handleGenerate}
          disabled={createKey.isPending}
        >
          {createKey.isPending ? '生成中…' : t('settings.api_keys.generate_new')}
        </Button>
      </div>

      {revealedSecret && (
        <div
          className="mb-4"
          style={{
            background: 'var(--color-accent-subtle)',
            borderRadius: '0.5rem',
            padding: '0.75rem',
            border: '1px solid var(--color-accent)',
          }}
        >
          <p className="text-xs font-semibold text-themed-accent mb-2">
            {t('settings.api_keys.secret_once_warning') ||
              '此密钥仅显示一次, 请立即复制并保存:'}
          </p>
          <div className="flex items-center justify-between gap-2">
            <code className="text-sm tabular-nums text-themed-primary break-all">
              {revealedSecret}
            </code>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigator.clipboard?.writeText(revealedSecret)}
            >
              {t('settings.api_keys.copy')}
            </Button>
          </div>
        </div>
      )}

      {isLoading && (
        <p className="text-xs text-themed-muted">加载中…</p>
      )}
      {error && (
        <p className="text-xs text-themed-muted">
          加载失败 — {error instanceof Error ? error.message : 'fetch failed'}
        </p>
      )}

      {items.length === 0 && !isLoading && !error && (
        <p className="text-xs text-themed-muted">
          {t('settings.api_keys.empty') || '还没有 API 密钥. 点击右上角生成第一把.'}
        </p>
      )}

      <div className="space-y-3">
        {items.map((k) => (
          <div
            key={k.id}
            style={{
              background: 'var(--color-bg-badge)',
              borderRadius: '0.5rem',
              padding: '1rem',
              border: '1px solid var(--color-border)',
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <code className="text-sm tabular-nums text-themed-secondary">
                {k.prefix}{'·'.repeat(20)}
              </code>
              {k.name && (
                <span className="text-[11px] text-themed-muted">{k.name}</span>
              )}
            </div>
            <div className="flex items-center justify-between text-xs text-themed-muted">
              <span>
                {t('settings.api_keys.created_at', {
                  date: formatDate(k.created_at),
                })}
              </span>
              <div className="flex items-center gap-2">
                <span>
                  {t('settings.api_keys.usage', {
                    used: k.usage_count,
                    total: k.rate_limit_per_minute * 60 * 24,
                  })}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => revokeKey.mutate(k.id)}
                  disabled={revokeKey.isPending}
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
        ))}
      </div>
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────────
   McpConfigCard — renders an MCP-client config snippet with the
   user's first API key prefix (when one exists) instead of the
   generic `gp_sk_...` placeholder.
   ───────────────────────────────────────────────────────────── */
function McpConfigCard({
  t,
}: {
  t: (key: string, params?: Record<string, unknown>) => string;
}) {
  const { data } = useApiKeys();
  const firstKey = data?.items?.find((k) => !k.revoked_at) ?? null;
  const tokenSample = firstKey
    ? `${firstKey.prefix}····················`
    : 'gp_sk_...';
  const mcpUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/mcp/v1`
      : '/mcp/v1';
  const snippet = `{
  "mcpServers": {
    "genpano": {
      "url": "${mcpUrl}",
      "headers": { "Authorization": "Bearer ${tokenSample}" }
    }
  }
}`;
  return (
    <Card>
      <h2 className="text-sm font-semibold text-themed-primary mb-2">
        {t('settings.mcp.title')}
      </h2>
      <p className="text-sm text-themed-secondary mb-4">
        {t('settings.mcp.description')}
      </p>

      <div
        style={{
          background: 'var(--color-bg-elevated)',
          borderRadius: '0.5rem',
          padding: '1rem',
          border: '1px solid var(--color-border)',
          overflow: 'auto',
        }}
      >
        <pre
          className="tabular-nums text-sm"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {snippet}
        </pre>
      </div>
      {!firstKey && (
        <p className="text-[11px] text-themed-muted mt-2">
          {t('settings.mcp.no_key_hint') ||
            '生成一把 API 密钥后, 这里会显示你的真实 prefix.'}
        </p>
      )}
    </Card>
  );
}
