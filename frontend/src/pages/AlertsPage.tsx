import { useState } from 'react';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import {
  useAlerts,
  useMarkAllAlertsRead,
  useSnoozeAlert,
  useUpdateAlertStatus,
} from '../hooks/useAlerts';
import type { AlertOut } from '../api/alerts';
import { SNOOZE_PRESET_HOURS } from '../api/alerts';

/* ────────────────────────────────────────────────────────────────
   AlertsPage — Phase N user-facing alert center
   ────────────────────────────────────────────────────────────────
   Lists alerts.scope='user' rows from /v1/alerts/, filterable by
   status + severity. Top-bar bell click lands here.

   Each row's status PATCH (read / ignored / resolved) updates via
   useUpdateAlertStatus(). Bulk "mark all read" via
   useMarkAllAlertsRead().
*/

const SEVERITY_BG: Record<string, string> = {
  P0: '#dc2626',
  P1: '#ea580c',
  P2: '#ca8a04',
  P3: '#64748b',
};

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso);
    const ms = Date.now() - d.getTime();
    const m = Math.floor(ms / 60_000);
    if (m < 1) return '刚刚';
    if (m < 60) return `${m} 分钟前`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} 小时前`;
    const dy = Math.floor(h / 24);
    if (dy < 30) return `${dy} 天前`;
    return d.toLocaleDateString();
  } catch {
    return iso;
  }
}

function snoozeLabel(hours: number): string {
  if (hours < 24) return `${hours} 小时`;
  const days = Math.round(hours / 24);
  return `${days} 天`;
}

export default function AlertsPage() {
  const { t } = useLocale();
  const [statusFilter, setStatusFilter] = useState<'unread' | 'read' | 'all'>('unread');
  const [severityFilter, setSeverityFilter] = useState<string | 'all'>('all');
  const [snoozeOpenFor, setSnoozeOpenFor] = useState<string | null>(null);

  const { data, isLoading, isError } = useAlerts({
    status: statusFilter === 'all' ? undefined : statusFilter,
    severity: severityFilter === 'all' ? undefined : severityFilter,
    limit: 100,
  });
  const updateStatus = useUpdateAlertStatus();
  const markAll = useMarkAllAlertsRead();
  const snooze = useSnoozeAlert();

  const handleSnooze = (id: string, hours: number) => {
    snooze.mutate({ id, hours });
    setSnoozeOpenFor(null);
  };

  const items: AlertOut[] = data?.items ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            {t('topbar.alerts.aria') || '提醒'}
          </h2>
          <p className="text-sm text-themed-muted mt-1">
            P0 / P1 诊断 + 监测中断 + 引用归因下滑等关键事件
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => markAll.mutate()}
          disabled={markAll.isPending || items.length === 0}
        >
          全部标为已读
        </Button>
      </div>

      {/* Filter bar */}
      <Card className="p-3" onClick={undefined} style={{}}>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-themed-muted">状态</span>
          {(['unread', 'read', 'all'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1 rounded-pill transition-colors ${
                statusFilter === s
                  ? 'bg-themed-accent-subtle text-themed-accent'
                  : 'text-themed-muted hover:text-themed-primary hover:bg-themed-subtle'
              }`}
            >
              {s === 'unread' ? '未读' : s === 'read' ? '已读' : '全部'}
            </button>
          ))}
          <span className="ml-4 text-themed-muted">严重度</span>
          {(['all', 'P0', 'P1', 'P2', 'P3'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSeverityFilter(s)}
              className={`px-3 py-1 rounded-pill transition-colors ${
                severityFilter === s
                  ? 'bg-themed-accent-subtle text-themed-accent'
                  : 'text-themed-muted hover:text-themed-primary hover:bg-themed-subtle'
              }`}
            >
              {s === 'all' ? '全部' : s}
            </button>
          ))}
        </div>
      </Card>

      {/* List */}
      {isLoading ? (
        <Card className="p-6 text-center text-themed-muted text-sm" onClick={undefined} style={{}}>
          加载中…
        </Card>
      ) : isError ? (
        <Card className="p-6 text-center text-themed-muted text-sm" onClick={undefined} style={{}}>
          加载失败，请稍后再试。
        </Card>
      ) : items.length === 0 ? (
        <Card className="p-12 text-center" onClick={undefined} style={{}}>
          <div className="text-5xl mb-3">🎉</div>
          <h3 className="text-base font-semibold text-themed-primary mb-1">
            没有未读提醒
          </h3>
          <p className="text-sm text-themed-muted">
            P0 / P1 诊断和重要事件会在这里出现。
          </p>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <ul className="divide-y divide-themed">
            {items.map((alert) => (
              <li
                key={alert.id}
                className={`flex items-start gap-4 p-4 transition-colors ${
                  alert.status === 'unread' ? 'bg-themed-accent-subtle/40' : ''
                }`}
              >
                <span
                  className="shrink-0 mt-0.5 px-2 py-0.5 rounded-pill text-xs font-bold text-white tabular-nums"
                  style={{ background: SEVERITY_BG[alert.severity] || '#64748b' }}
                >
                  {alert.severity}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-themed-primary">
                    {alert.title}
                  </div>
                  {alert.body && (
                    <div className="text-xs text-themed-muted mt-1 line-clamp-2">
                      {alert.body}
                    </div>
                  )}
                  <div className="flex items-center gap-3 mt-2 text-[11px] text-themed-faint">
                    <span>{formatRelative(alert.triggered_at)}</span>
                    <span>来源: {alert.source}</span>
                    {alert.brand_id != null && <span>品牌: {alert.brand_id}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0 relative">
                  {alert.status === 'unread' && (
                    <button
                      type="button"
                      onClick={() =>
                        updateStatus.mutate({ id: alert.id, status: 'read' })
                      }
                      className="text-xs px-2 py-1 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle"
                    >
                      标为已读
                    </button>
                  )}
                  {/* B3-3: Snooze defers a non-urgent alert. Backend hides
                      it from unread_count until snoozed_until passes, then
                      lazily flips it back to 'unread' on next read. */}
                  {(alert.status === 'unread' || alert.status === 'snoozed') && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          setSnoozeOpenFor(
                            snoozeOpenFor === alert.id ? null : alert.id,
                          )
                        }
                        className="text-xs px-2 py-1 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle"
                        aria-expanded={snoozeOpenFor === alert.id}
                      >
                        {alert.status === 'snoozed' ? '稍后再处理 · 已暂缓' : '稍后再处理'}
                      </button>
                      {snoozeOpenFor === alert.id && (
                        <div
                          className="absolute right-0 top-full mt-1 z-10 bg-themed-card border border-themed shadow-elevated rounded-card-lg p-2 space-y-1"
                          role="menu"
                        >
                          <div className="text-[10px] text-themed-muted px-2 py-1">
                            暂缓时长
                          </div>
                          {SNOOZE_PRESET_HOURS.map((h) => (
                            <button
                              key={h}
                              type="button"
                              onClick={() => handleSnooze(alert.id, h)}
                              disabled={snooze.isPending}
                              className="block w-full text-left text-xs px-2 py-1 rounded-btn text-themed-body hover:bg-themed-subtle disabled:opacity-50"
                            >
                              {snoozeLabel(h)}
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  {alert.status === 'snoozed' && alert.snoozed_until && (
                    <span className="text-[10px] text-themed-faint px-1">
                      至 {new Date(alert.snoozed_until).toLocaleString()}
                    </span>
                  )}
                  {alert.status !== 'resolved' && (
                    <button
                      type="button"
                      onClick={() =>
                        updateStatus.mutate({ id: alert.id, status: 'resolved' })
                      }
                      className="text-xs px-2 py-1 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle"
                    >
                      已解决
                    </button>
                  )}
                  {alert.status === 'unread' && (
                    <button
                      type="button"
                      onClick={() =>
                        updateStatus.mutate({ id: alert.id, status: 'ignored' })
                      }
                      className="text-xs px-2 py-1 rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle"
                    >
                      忽略
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
