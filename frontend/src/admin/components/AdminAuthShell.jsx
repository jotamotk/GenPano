import React from 'react';
import { Outlet } from 'react-router-dom';
import { AdminAuthProvider } from '../context/AdminAuthContext.jsx';
import SessionExpiredModal from './SessionExpiredModal.jsx';

/* ─────────────────────────────────────────────────────────────
   AdminAuthShell — Session A0 · Step 7

   React-Router layout route: wraps every /admin/* leaf in the
   AdminAuthProvider so any admin page can call useAdminAuth(), and
   mounts a global SessionExpiredModal sibling that renders only when
   the silent-refresh tick fails.

   Step 8 adds AdminRouteGuard.jsx on the gated sub-routes (not here).
   ───────────────────────────────────────────────────────────── */

export default function AdminAuthShell() {
  return (
    <AdminAuthProvider>
      <Outlet />
      <SessionExpiredModal />
    </AdminAuthProvider>
  );
}
