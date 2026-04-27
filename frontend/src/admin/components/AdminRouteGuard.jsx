import React, { useEffect } from 'react';
import { useLocation, useNavigate, Outlet } from 'react-router-dom';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';

/* ─────────────────────────────────────────────────────────────
   AdminRouteGuard — Session A0 · Step 8 (CLAUDE.md #24)

   Client-side gate for /admin/** pages that REQUIRE an authenticated
   session. Wraps any route group that should not render without a valid
   user. The Next.js middleware (backend/middleware.ts) is the first line
   of defense; this guard is the second, covering two cases the middleware
   cannot:
     1. SPA soft navigations (no full-page request — middleware never runs).
     2. Force-password-change gate (middleware can't query DB to check
        AdminUser.forcePasswordChangeAt; the Provider got it from
        /refresh and we enforce here).

   Decision matrix (mirrors decideAdminAuth() semantics):
     status='initializing'          → <Placeholder /> (don't flash unauth)
     status='anonymous'              → navigate /admin/login?redirect=...
     status='expired'                → render children; global
                                      SessionExpiredModal (sibling in
                                      AdminAuthShell) shows the blocking UI
     status='authenticated' + forcePasswordChangeAt ≤ now
                                    → navigate /admin/change-password
                                      (unless already there)
     status='authenticated' + OK     → render children
   ───────────────────────────────────────────────────────────── */

function Placeholder() {
  // Minimal spinner so the initial /refresh probe doesn't flash the
  // login page underneath the Provider's state transition.
  return (
    <div
      className="flex h-screen w-full items-center justify-center"
      style={{ background: 'var(--color-bg-page)' }}
    >
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <div
        className="w-8 h-8 rounded-full"
        style={{
          border: '3px solid var(--color-border-subtle)',
          borderTopColor: 'var(--color-accent)',
          animation: 'spin 0.8s linear infinite',
        }}
        aria-label="加载中"
      />
    </div>
  );
}

export default function AdminRouteGuard({ children }) {
  const { status, user } = useAdminAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const forceChange =
    user?.forcePasswordChangeAt &&
    new Date(user.forcePasswordChangeAt).getTime() <= Date.now();

  const onChangePasswordPage = location.pathname === '/admin/change-password';

  useEffect(() => {
    if (status === 'anonymous') {
      const redirect =
        location.pathname +
        (location.search || '') +
        (location.hash || '');
      const params = new URLSearchParams({ redirect });
      navigate(`/admin/login?${params.toString()}`, { replace: true });
      return;
    }
    if (status === 'authenticated' && forceChange && !onChangePasswordPage) {
      navigate('/admin/change-password', { replace: true });
    }
  }, [status, forceChange, onChangePasswordPage, location, navigate]);

  if (status === 'initializing') return <Placeholder />;
  if (status === 'anonymous') return <Placeholder />; // brief flash before nav
  if (status === 'authenticated' && forceChange && !onChangePasswordPage) {
    return <Placeholder />;
  }

  // authenticated OR expired — expired still renders underlying content
  // behind the SessionExpiredModal overlay.
  return children ?? <Outlet />;
}
