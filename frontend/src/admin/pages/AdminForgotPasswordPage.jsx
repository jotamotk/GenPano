import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminAuthApi } from '../lib/adminApi.js';

/* ─────────────────────────────────────────────────────────────
   AdminForgotPasswordPage — Session A0 · wired in Step 7

   Fires POST /admin/api/v1/auth/forgot-password. The response is
   deliberately uniform whether or not the email exists (the backend
   always returns 200 with the same shape — anti-enum parity with login).

   We therefore ALWAYS show the generic "email sent if it exists"
   confirmation on submit, regardless of what the backend actually did
   under the hood. The 60-min token is minted + dispatched server-side
   via Resend (or dev console fallback).
   ─────────────────────────────────────────────────────────────── */

export default function AdminForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await adminAuthApi.forgotPassword({ email: email.trim().toLowerCase() });
    } catch {
      // Endpoint always 200s on the happy path; a failure here is either
      // network or 429. Either way we still show the uniform confirmation
      // — leaking "rate limited" or "validation error" would tell probes
      // something. The backend already enforces the limits silently.
    }
    setSubmitting(false);
    setSent(true);
  };

  return (
    <div
      className="flex h-screen w-full items-center justify-center"
      style={{ background: 'var(--color-bg-page)' }}
    >
      <div
        className="w-full max-w-[440px] p-8 rounded-card"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        {sent ? (
          <>
            <h1
              className="text-[22px] font-brand font-bold mb-2 leading-tight"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
            >
              重置邮件已发送
            </h1>
            <p className="text-sm leading-relaxed mb-6" style={{ color: 'var(--color-text-body)' }}>
              如果 {email} 是授权管理员的邮箱，我们已把重置链接发过去。<br />
              请在 60 分钟内点击邮件中的链接完成密码重置。
            </p>
            <button
              type="button"
              onClick={() => navigate('/admin/login')}
              className="t-btn-primary w-full h-11 text-sm font-semibold"
            >
              返回登录
            </button>
          </>
        ) : (
          <>
            <h1
              className="text-[22px] font-brand font-bold mb-2 leading-tight"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
            >
              重置管理员密码
            </h1>
            <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)' }}>
              输入你的管理员邮箱，我们会把重置链接发到你的邮箱。
            </p>

            <form onSubmit={submit} className="space-y-4" noValidate>
              <div>
                <label
                  className="block text-sm font-semibold mb-1.5"
                  style={{ color: 'var(--color-text-body)' }}
                >
                  邮箱
                </label>
                <input
                  ref={inputRef}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@genpano.com"
                  className="t-input"
                  autoComplete="email"
                  disabled={submitting}
                  required
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {submitting ? '发送中…' : '发送重置链接'}
              </button>

              <button
                type="button"
                onClick={() => navigate('/admin/login')}
                className="w-full text-xs hover:underline"
                style={{ color: 'var(--color-text-muted)' }}
              >
                返回登录
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
