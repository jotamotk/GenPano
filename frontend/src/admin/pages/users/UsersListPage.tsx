import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminUsersApi } from '../../lib/adminApi.js';

/**
 * Module A · Y1 — GET /admin/api/v1/users
 *
 * ADMIN_PRD §4.1.1: list rows = id / email / name / created_at / is_frozen
 * (derived from EXISTS) / is_deleted (derived from deletion_requested_at).
 * Step 9 wires the real backend; pagination is offset-based per the
 * router contract (limit 1-500, offset >= 0).
 */

interface UserItem {
  id: string;
  email: string;
  name_zh: string | null;
  name_en: string | null;
  created_at: string;
  is_frozen: boolean;
  is_deleted: boolean;
}

interface ListResponse {
  items: UserItem[];
  total: number;
}

const PAGE_SIZE = 25;

export default function UsersListPage() {
  const [data, setData] = useState<ListResponse | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminUsersApi
      .list({ limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((res) => {
        if (cancelled) return;
        setData(res as ListResponse);
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
  }, [page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="max-w-[1200px]">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h1
            className="text-xl font-bold"
            style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}
          >
            用户列表
          </h1>
          <p
            className="text-xs mt-0.5"
            style={{ color: 'var(--color-text-muted)' }}
          >
            ADMIN_PRD §4.1.1 · GET /admin/api/v1/users · 冻结态来自 EXISTS 子查询
          </p>
        </div>
        <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          共 {data?.total ?? '—'} 行
        </div>
      </div>

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
              <th className="px-3 py-2 font-semibold">邮箱</th>
              <th className="px-3 py-2 font-semibold">姓名</th>
              <th className="px-3 py-2 font-semibold">注册时间</th>
              <th className="px-3 py-2 font-semibold">状态</th>
              <th className="px-3 py-2 font-semibold w-24">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-xs"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  加载中…
                </td>
              </tr>
            )}
            {!loading && error && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-xs"
                  style={{ color: '#dc2626' }}
                >
                  请求失败: <code>{error}</code>
                </td>
              </tr>
            )}
            {!loading && !error && data?.items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-xs"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  暂无用户
                </td>
              </tr>
            )}
            {!loading &&
              !error &&
              data?.items.map((u) => (
                <tr
                  key={u.id}
                  style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                >
                  <td
                    className="px-3 py-2.5"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {u.email}
                  </td>
                  <td
                    className="px-3 py-2.5"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {u.name_zh ?? u.name_en ?? '—'}
                  </td>
                  <td
                    className="px-3 py-2.5 tabular-nums"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {new Date(u.created_at).toLocaleString('zh-CN')}
                  </td>
                  <td className="px-3 py-2.5">
                    {u.is_deleted ? (
                      <span
                        className="text-[11px] px-1.5 py-0.5 rounded font-medium"
                        style={{
                          background: 'rgba(239, 68, 68, 0.1)',
                          color: '#dc2626',
                        }}
                      >
                        已软删
                      </span>
                    ) : u.is_frozen ? (
                      <span
                        className="text-[11px] px-1.5 py-0.5 rounded font-medium"
                        style={{
                          background: 'rgba(245, 158, 11, 0.1)',
                          color: '#d97706',
                        }}
                      >
                        已冻结
                      </span>
                    ) : (
                      <span
                        className="text-[11px] px-1.5 py-0.5 rounded font-medium"
                        style={{
                          background: 'rgba(16, 185, 129, 0.1)',
                          color: '#059669',
                        }}
                      >
                        正常
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <Link
                      to={`/admin/users/${encodeURIComponent(u.id)}`}
                      className="text-[12px] font-medium"
                      style={{ color: 'var(--color-accent)' }}
                    >
                      详情 →
                    </Link>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && !error && data && (
        <div className="flex items-center justify-end gap-2 mt-3 text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>
            第 {page + 1} / {totalPages} 页
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="h-7 px-2.5 rounded disabled:opacity-40"
            style={{
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
              background: 'transparent',
            }}
          >
            上一页
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page + 1 >= totalPages}
            className="h-7 px-2.5 rounded disabled:opacity-40"
            style={{
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
              background: 'transparent',
            }}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
