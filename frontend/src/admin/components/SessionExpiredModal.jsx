import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';

/* ─────────────────────────────────────────────────────────────
   SessionExpiredModal — Session A0 · Step 7 (CLAUDE.md #24)

   Rendered as a sibling of <Outlet /> inside AdminAuthShell. Consumes
   AdminAuthContext.sessionExpired and mounts a blocking overlay only when
   true. The modal has ONE action: "重新登录" → navigate to /admin/login
   with ?reason=session_expired + ?redirect=<current non-login path>.

   Deliberate design choices:
     - No X-close / no backdrop click: session is actually dead, there's
       nothing to do but re-auth. Letting users dismiss silently creates a
       zombie state where the app UI says "logged in" but every API call
       401s.
     - Do not render on /admin/login itself — the login page already shows
       the session_expired banner, a modal on top would be redundant.
     - ESC key is intentionally NOT wired as a dismiss; the modal is a
       terminal state.
     - Focus is trapped on the CTA button via autoFocus; production
       Radix/Headless UI dialog lands in later sessions if needed.

   Tokens: all styling via var(--color-*), no inline hex (matches
   AdminLoginPage convention).
   ───────────────────────────────────────────────────────────── */

function WarningIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export default function SessionExpiredModal() {
  const { sessionExpired, dismissExpiredModal } = useAdminAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Never stack on top of /admin/login — it owns the same messaging.
  const onLoginPage = location.pathname.startsWith('/admin/login');
  if (!sessionExpired || onLoginPage) return null;

  const goToLogin = () => {
    dismissExpiredModal();
    const redirect =
      location.pathname +
      (location.search || '') +
      (location.hash || '');
    const params = new URLSearchParams({
      reason: 'session_expired',
      redirect,
    });
    navigate(`/admin/login?${params.toString()}`, { replace: true });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-session-expired-title"
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: 'rgba(15, 23, 42, 0.55)' }}
    >
      <div
        className="w-full max-w-[420px] rounded-card shadow-card-lg p-7"
        style={{ background: 'var(--color-bg-card)' }}
      >
        <div className="flex items-start gap-3 mb-4">
          <div
            className="w-10 h-10 rounded-card shrink-0 flex items-center justify-center"
            style={{
              background: 'var(--color-warning-bg)',
              color: 'var(--color-warning-text)',
            }}
          >
            <WarningIcon />
          </div>
          <div>
            <h2
              id="admin-session-expired-title"
              className="text-lg font-brand font-bold leading-tight mb-1"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}
            >
              会话已过期
            </h2>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              为了账户安全，管理员会话 15 分钟无活动后会自动结束。请重新登录以继续操作。
            </p>
          </div>
        </div>

        <button
          type="button"
          autoFocus
          onClick={goToLogin}
          className="t-btn-primary w-full h-11 text-sm font-semibold"
        >
          重新登录
        </button>
      </div>
    </div>
  );
}
