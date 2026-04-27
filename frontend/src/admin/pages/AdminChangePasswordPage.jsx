import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminAuthApi, AdminApiError } from '../lib/adminApi.js';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';

/* ─────────────────────────────────────────────────────────────
   AdminChangePasswordPage — Session A0 · wired in Step 7

   Reachable in two scenarios:
     1. Force-rotate (AdminUser.forcePasswordChangeAt ≤ now). The login
        redirect sends them here. They still have a valid access-token
        cookie so POST /change-password is authenticated.
     2. Voluntary rotation from a settings menu (not wired in A0).

   Shape: current + new + confirm. The endpoint also performs zxcvbn ≥3
   + length ≥12 + same_as_current rejection; we do minimum client-side
   checks (length + match) and rely on server for the strong rules.

   On success:
     - Server has cleared forcePasswordChangeAt + revoked every other
       session (keeps current session alive).
     - We call refreshNow() so the AdminAuthContext picks up the cleared
       forcePasswordChangeAt flag on the user profile, then navigate
       to /admin/dashboard.
   ───────────────────────────────────────────────────────────── */

export default function AdminChangePasswordPage() {
  const navigate = useNavigate();
  const { refreshNow } = useAdminAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const pwRef = useRef(null);

  useEffect(() => {
    pwRef.current?.focus();
  }, []);

  const clearError = () => {
    if (error) setError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!currentPassword) {
      setError('请先输入当前密码');
      return;
    }
    if (newPassword.length < 12) {
      setError('新密码至少需要 12 个字符');
      return;
    }
    if (newPassword === currentPassword) {
      setError('新密码不能与当前密码相同');
      return;
    }
    if (newPassword !== confirm) {
      setError('两次输入的密码不一致');
      return;
    }

    setSubmitting(true);
    try {
      await adminAuthApi.changePassword({ currentPassword, newPassword });
      // Server cleared forcePasswordChangeAt + revoked other sessions.
      // Refresh our context so the provider's user payload picks up the
      // cleared flag; then route to the dashboard.
      await refreshNow();
      navigate('/admin/dashboard', { replace: true });
    } catch (err) {
      if (err instanceof AdminApiError) {
        const code = err.body?.error;
        if (code === 'current_password_mismatch') {
          setError('当前密码不正确');
        } else if (code === 'same_as_current') {
          setError('新密码不能与当前密码相同');
        } else if (code === 'weak_password') {
          setError('新密码强度不足，请使用更复杂的组合');
        } else if (err.status === 401) {
          // Session died during the request — bounce to login.
          navigate('/admin/login?reason=session_expired', { replace: true });
        } else {
          setError('保存失败，请稍后再试');
        }
      } else {
        setError('网络错误，请稍后再试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="flex h-screen w-full items-center justify-center"
      style={{ background: 'var(--color-bg-page)' }}
    >
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <div
        className="w-full max-w-[440px] p-8 rounded-card"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        <h1
          className="text-[24px] font-brand font-bold mb-2 leading-tight"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
        >
          请先设置新密码
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)' }}>
          首次登录或密码已被重置。设置新密码后可继续使用管理后台。
        </p>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <label
              className="block text-sm font-semibold mb-1.5"
              style={{ color: 'var(--color-text-body)' }}
            >
              当前密码
            </label>
            <input
              ref={pwRef}
              type="password"
              value={currentPassword}
              onChange={(e) => { setCurrentPassword(e.target.value); clearError(); }}
              placeholder="从 bootstrap 或上次重置邮件中获取"
              className={`t-input ${error ? 't-input-error' : ''}`}
              autoComplete="current-password"
              disabled={submitting}
            />
          </div>

          <div>
            <label
              className="block text-sm font-semibold mb-1.5"
              style={{ color: 'var(--color-text-body)' }}
            >
              新密码
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => { setNewPassword(e.target.value); clearError(); }}
              placeholder="至少 12 个字符，建议使用密码管理器生成"
              className={`t-input ${error ? 't-input-error' : ''}`}
              autoComplete="new-password"
              disabled={submitting}
            />
          </div>

          <div>
            <label
              className="block text-sm font-semibold mb-1.5"
              style={{ color: 'var(--color-text-body)' }}
            >
              确认新密码
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => { setConfirm(e.target.value); clearError(); }}
              placeholder="再次输入"
              className={`t-input ${error ? 't-input-error' : ''}`}
              autoComplete="new-password"
              disabled={submitting}
            />
            {error && (
              <p className="text-xs mt-1.5" style={{ color: 'var(--color-danger-text)' }}>
                {error}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? '保存中…' : '保存并继续'}
          </button>
        </form>
      </div>
    </div>
  );
}
