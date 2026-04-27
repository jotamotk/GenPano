import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';

/* ─────────────────────────────────────────────────────────────
   AdminDashboardPage — Session A0 · Step 8 stub (CLAUDE.md #24)

   A placeholder destination so the login → guard → dashboard path can
   be walked end-to-end for the Phase Gate self-test. Real admin home
   (operator metrics, today's queue, cost overview) lands in Session
   A1+. For A0 we just show the currently authenticated admin's email
   + role and a logout button so the cross-tab BroadcastChannel
   behavior can be verified by hand.
   ───────────────────────────────────────────────────────────── */

export default function AdminDashboardPage() {
  const { user, logout } = useAdminAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/admin/login', { replace: true });
  };

  return (
    <div
      className="min-h-screen w-full flex flex-col items-center py-14 px-6"
      style={{ background: 'var(--color-bg-page)' }}
    >
      <div
        className="w-full max-w-[640px] rounded-card p-8"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        <h1
          className="text-[24px] font-brand font-bold mb-2 leading-tight"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
        >
          Admin Console
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)' }}>
          Session A0 Phase Gate 占位页。完整的管理员首页 (运营指标 / 今日队列 / 成本总览) 在 Session A1 落地。
        </p>

        <dl className="space-y-3 text-sm mb-6">
          <div className="flex items-start gap-3">
            <dt
              className="w-20 shrink-0 font-semibold"
              style={{ color: 'var(--color-text-muted)' }}
            >
              邮箱
            </dt>
            <dd style={{ color: 'var(--color-text-primary)' }}>
              {user?.email ?? '—'}
            </dd>
          </div>
          <div className="flex items-start gap-3">
            <dt
              className="w-20 shrink-0 font-semibold"
              style={{ color: 'var(--color-text-muted)' }}
            >
              角色
            </dt>
            <dd style={{ color: 'var(--color-text-primary)' }}>
              {user?.role ?? '—'}
            </dd>
          </div>
        </dl>

        <button
          type="button"
          onClick={handleLogout}
          className="t-btn-secondary h-10 px-4 text-sm font-semibold"
        >
          退出登录
        </button>
      </div>
    </div>
  );
}
