import React from 'react';
import AdminPlaceholderPage from '../../components/AdminPlaceholderPage';

/**
 * Module A · Y6 — login audit page (placeholder).
 *
 * The Y6 endpoint (read-only against `login_attempts`) depends on the
 * App-side login_attempts table, which is Session 4a' work. The route is
 * mounted now so the sidebar entry resolves; data wiring lands once the
 * backend endpoint exists.
 */
export default function LoginAuditPage() {
  return (
    <AdminPlaceholderPage
      module="A"
      title="登录审计"
      description="App 用户登录尝试明细 (成功/失败/锁定状态), 用于异常登录定位。"
      prdSection="ADMIN_PRD §4.1.3"
      pendingSession="Session 4a' (App-side login_attempts schema)"
    />
  );
}
