import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { adminUsersApi } from '../../lib/adminApi.js';
import ConfirmActionModal from '../../components/ConfirmActionModal';

type TabKey = 'basic' | 'projects' | 'monitor' | 'history';

const TAB_DEFS: Array<{ value: TabKey; label: string }> = [
  { value: 'basic', label: '基本信息' },
  { value: 'projects', label: '项目' },
  { value: 'monitor', label: '监控配置' },
  { value: 'history', label: '操作历史' },
];

/**
 * Module A · Y2 — GET /admin/api/v1/users/{user_id}
 *                + Y3 (freeze) / Y4 (force-password-reset) / Y5 (soft-delete)
 *
 * ADMIN_PRD §4.1.2: 4-tab detail (基本信息 / 项目 / 监控配置 / 操作历史).
 * Step 9 wires the 4 tabs to the backend's UserDetailResponse + 3 confirm
 * actions; project / monitor-config tabs render an awaiting-data card so
 * the route surface is honest until App-side User/Project schema lands
 * (Session 4a').
 */

interface ModerationEntry {
  id: string;
  action: string;
  reason: string | null;
  expires_at: string | null;
  operator_id: string;
  created_at: string;
}

interface UserDetail {
  id: string;
  email: string;
  name_zh: string | null;
  name_en: string | null;
  email_verified_at: string | null;
  preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  deletion_requested_at: string | null;
  is_frozen: boolean;
  recent_moderation: ModerationEntry[];
}

type ActionKind = 'freeze' | 'force-password-reset' | 'soft-delete' | null;

const ACTION_COPY: Record<
  Exclude<ActionKind, null>,
  { title: string; description: string; cta: string }
> = {
  freeze: {
    title: '冻结此用户',
    description: '冻结后用户登录会被拒绝。冻结由 user_moderation_actions 表驱动 (decision #30.H Path B Variant 2), 不写 users 表。',
    cta: '确认冻结',
  },
  'force-password-reset': {
    title: '强制密码重置',
    description: '用户下次登录时需要先改密。会写一条 force_password_reset moderation 行 + 触发 App 侧重置邮件 (Session 4a\' 落地)。',
    cta: '确认强制改密',
  },
  'soft-delete': {
    title: '软删除此用户',
    description: '会设置 users.deletion_requested_at = now() 并写 soft_delete moderation 行。可由数据流程恢复，但用户登录立即拒绝。',
    cta: '确认软删',
  },
};

export default function UserDetailPage() {
  const { userId = '' } = useParams<{ userId: string }>();
  const [data, setData] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openAction, setOpenAction] = useState<ActionKind>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('basic');

  const refetch = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminUsersApi
      .detail(userId)
      .then((res) => {
        if (cancelled) return;
        setData(res as UserDetail);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.body?.detail?.reason ?? err?.message ?? 'unknown_error');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    return refetch();
  }, [refetch]);

  const handleConfirm = async ({ reason }: { reason: string }) => {
    if (!openAction) return;
    if (openAction === 'freeze') {
      await adminUsersApi.freeze(userId, { reason });
    } else if (openAction === 'force-password-reset') {
      await adminUsersApi.forcePasswordReset(userId, { reason });
    } else if (openAction === 'soft-delete') {
      await adminUsersApi.softDelete(userId, { reason });
    }
    refetch();
  };

  if (loading) {
    return (
      <div
        className="text-xs"
        style={{ color: 'var(--color-text-muted)' }}
      >
        加载中…
      </div>
    );
  }
  if (error || !data) {
    return (
      <div
        className="rounded p-4 text-xs"
        style={{
          background: 'rgba(239, 68, 68, 0.06)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#dc2626',
        }}
      >
        加载失败: <code>{error ?? 'unknown'}</code>
        <div className="mt-2">
          <Link
            to="/admin/users"
            className="font-medium"
            style={{ color: 'var(--color-accent)' }}
          >
            ← 返回列表
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1100px]">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <Link
            to="/admin/users"
            className="text-xs font-medium mb-1 inline-block"
            style={{ color: 'var(--color-accent)' }}
          >
            ← 用户列表
          </Link>
          <h1
            className="text-xl font-bold"
            style={{
              color: 'var(--color-text-primary)',
              letterSpacing: '-0.01em',
            }}
          >
            {data.email}
          </h1>
          <div className="flex items-center gap-2 mt-1.5 text-xs">
            {data.is_frozen && (
              <span
                className="px-1.5 py-0.5 rounded font-medium"
                style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  color: '#d97706',
                }}
              >
                已冻结
              </span>
            )}
            {data.deletion_requested_at && (
              <span
                className="px-1.5 py-0.5 rounded font-medium"
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: '#dc2626',
                }}
              >
                已软删 · {new Date(data.deletion_requested_at).toLocaleString('zh-CN')}
              </span>
            )}
            {!data.is_frozen && !data.deletion_requested_at && (
              <span
                className="px-1.5 py-0.5 rounded font-medium"
                style={{
                  background: 'rgba(16, 185, 129, 0.1)',
                  color: '#059669',
                }}
              >
                正常
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOpenAction('freeze')}
            disabled={data.is_frozen || !!data.deletion_requested_at}
            className="h-9 px-3 rounded text-[13px] font-medium disabled:opacity-40"
            style={{
              border: '1px solid var(--color-border-subtle)',
              color: '#d97706',
              background: 'transparent',
            }}
          >
            冻结
          </button>
          <button
            type="button"
            onClick={() => setOpenAction('force-password-reset')}
            disabled={!!data.deletion_requested_at}
            className="h-9 px-3 rounded text-[13px] font-medium disabled:opacity-40"
            style={{
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
              background: 'transparent',
            }}
          >
            强制改密
          </button>
          <button
            type="button"
            onClick={() => setOpenAction('soft-delete')}
            disabled={!!data.deletion_requested_at}
            className="h-9 px-3 rounded text-[13px] font-semibold disabled:opacity-40"
            style={{
              background: '#dc2626',
              color: '#fff',
            }}
          >
            软删
          </button>
        </div>
      </div>

      {/* Tabs (plain button group — no @radix-ui/react-tabs dep) */}
      <div
        role="tablist"
        className="flex gap-0 mb-4"
        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        {TAB_DEFS.map((t) => {
          const isActive = activeTab === t.value;
          return (
            <button
              key={t.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(t.value)}
              className="px-3 py-2 text-[13px] font-medium border-b-2 -mb-px bg-transparent"
              style={{
                color: isActive
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-muted)',
                borderBottomColor: isActive
                  ? 'var(--color-accent)'
                  : 'transparent',
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {activeTab === 'basic' && (
        <div role="tabpanel">
          <div
            className="rounded p-4"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
            }}
          >
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  ID
                </dt>
                <dd
                  className="font-mono"
                  style={{ color: 'var(--color-text-primary)' }}
                >
                  {data.id}
                </dd>
              </div>
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  邮箱
                </dt>
                <dd style={{ color: 'var(--color-text-primary)' }}>
                  {data.email}
                </dd>
              </div>
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  姓名 (中)
                </dt>
                <dd style={{ color: 'var(--color-text-primary)' }}>
                  {data.name_zh ?? '—'}
                </dd>
              </div>
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  姓名 (En)
                </dt>
                <dd style={{ color: 'var(--color-text-primary)' }}>
                  {data.name_en ?? '—'}
                </dd>
              </div>
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  邮箱已验证
                </dt>
                <dd style={{ color: 'var(--color-text-primary)' }}>
                  {data.email_verified_at
                    ? new Date(data.email_verified_at).toLocaleString('zh-CN')
                    : '—'}
                </dd>
              </div>
              <div>
                <dt
                  className="text-[11px] font-semibold uppercase mb-0.5"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}
                >
                  注册时间
                </dt>
                <dd style={{ color: 'var(--color-text-primary)' }}>
                  {new Date(data.created_at).toLocaleString('zh-CN')}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {activeTab === 'projects' && (
        <div role="tabpanel">
          <div
            className="rounded p-4 text-xs"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px dashed var(--color-border-subtle)',
              color: 'var(--color-text-muted)',
            }}
          >
            项目数据接入待 Session 4a' (App-side User/Project schema). 当前 UserDetail
            响应不含项目字段, 真相源 ADMIN_PRD §4.1.2.
          </div>
        </div>
      )}

      {activeTab === 'monitor' && (
        <div role="tabpanel">
          <div
            className="rounded p-4 text-xs"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px dashed var(--color-border-subtle)',
              color: 'var(--color-text-muted)',
            }}
          >
            监控配置 (品牌池 / 引擎子集 / 频次) 数据接入待 Session 3' Pipeline 落地.
            真相源 ADMIN_PRD §4.1.2.
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <div role="tabpanel">
          <div
            className="rounded overflow-hidden"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
            }}
          >
            <table className="w-full text-[13px]">
              <thead>
                <tr
                  className="text-left"
                  style={{
                    borderBottom: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-bg-page)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  <th className="px-3 py-2 font-semibold">时间</th>
                  <th className="px-3 py-2 font-semibold">操作</th>
                  <th className="px-3 py-2 font-semibold">原因</th>
                  <th className="px-3 py-2 font-semibold">操作员</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_moderation.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-3 py-6 text-center text-xs"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      暂无操作记录
                    </td>
                  </tr>
                )}
                {data.recent_moderation.map((m) => (
                  <tr
                    key={m.id}
                    style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                  >
                    <td
                      className="px-3 py-2.5 tabular-nums"
                      style={{ color: 'var(--color-text-primary)' }}
                    >
                      {new Date(m.created_at).toLocaleString('zh-CN')}
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className="text-[11px] px-1.5 py-0.5 rounded font-medium"
                        style={{
                          background: 'var(--color-bg-page)',
                          color: 'var(--color-text-primary)',
                        }}
                      >
                        {m.action}
                      </span>
                    </td>
                    <td
                      className="px-3 py-2.5"
                      style={{ color: 'var(--color-text-primary)' }}
                    >
                      {m.reason ?? '—'}
                    </td>
                    <td
                      className="px-3 py-2.5 font-mono text-xs"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {m.operator_id}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {openAction && (
        <ConfirmActionModal
          open={!!openAction}
          onOpenChange={(o) => !o && setOpenAction(null)}
          title={ACTION_COPY[openAction].title}
          description={ACTION_COPY[openAction].description}
          cta={ACTION_COPY[openAction].cta}
          onConfirm={handleConfirm}
          destructive={openAction !== 'force-password-reset'}
        />
      )}
    </div>
  );
}
