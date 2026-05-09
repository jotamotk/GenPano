import { useState } from 'react'
import { Button, Card } from '../../components/ui'
import { useLocale } from '../../contexts/LocaleContext'
import {
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
} from '../../hooks/useApiKeys'

export default function ApiKeysSettingsPage() {
  const { t, formatDate } = useLocale()
  return (
    <div className="space-y-6">
      <ApiKeysCard t={t} formatDate={formatDate} />
      <McpConfigCard t={t} />
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   ApiKeysCard — wires Settings to /v1/users/me/api-keys (Phase M)
   ───────────────────────────────────────────────────────────── */
function ApiKeysCard({
  t,
  formatDate,
}: {
  t: (key: string, params?: Record<string, unknown>) => string
  formatDate: (d: string | number | Date, opts?: Intl.DateTimeFormatOptions) => string
}) {
  const { data, isLoading, error } = useApiKeys()
  const createKey = useCreateApiKey()
  const revokeKey = useRevokeApiKey()
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null)

  const items = data?.items ?? []

  const handleGenerate = () => {
    setRevealedSecret(null)
    createKey.mutate(
      { name: `key-${new Date().toISOString().slice(0, 10)}` },
      {
        onSuccess: (res) => setRevealedSecret(res.secret),
      }
    )
  }

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

      {isLoading && <p className="text-xs text-themed-muted">加载中…</p>}
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
  )
}

/* ─────────────────────────────────────────────────────────────
   McpConfigCard — renders an MCP-client config snippet with the
   user's first API key prefix (when one exists) instead of the
   generic `gp_sk_...` placeholder.
   ───────────────────────────────────────────────────────────── */
function McpConfigCard({
  t,
}: {
  t: (key: string, params?: Record<string, unknown>) => string
}) {
  const { data } = useApiKeys()
  const firstKey = data?.items?.find((k) => !k.revoked_at) ?? null
  const tokenSample = firstKey
    ? `${firstKey.prefix}····················`
    : 'gp_sk_...'
  const mcpUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/mcp/v1`
      : '/mcp/v1'
  const snippet = `{
  "mcpServers": {
    "genpano": {
      "url": "${mcpUrl}",
      "headers": { "Authorization": "Bearer ${tokenSample}" }
    }
  }
}`
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
  )
}
