import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAdminAuth } from '../context/AdminAuthContext.jsx';
import { AdminApiError } from '../lib/adminApi.js';

/* ─────────────────────────────────────────────────────────────
   AdminLoginPage — Session A0 · CLAUDE.md #24

   Deliberately simpler than user-facing AuthPage:
   - No email-first 2-step (admin count is fixed, no identifier probing)
   - No OAuth (email + password only)
   - No Sign-up link (admin accounts come from admin-bootstrap.ts seed,
     or later A5 invite flow)
   - Left panel = env-aware solid color band (dev=green / staging=orange /
     prod=red) reading import.meta.env.VITE_ENV_NAME. This is how Frank
     knows at a glance which environment he is about to act in.
   - Anti-enum: every credential failure returns the same message, no
     "email not found" leakage.

   First-login flow (ADMIN_PRD §5.6.4-8 + CLAUDE.md #24.C2):
     POST /admin/api/v1/auth/login returns { user: { forcePasswordChangeAt } }
     on success. If present AND ≤ now(), navigate to /admin/change-password;
     otherwise → /admin/dashboard (or ?redirect=).

   URL contract:
     /admin/login
     /admin/login?reason=session_expired   — silent-refresh failure
     /admin/login?reason=invalid_session   — JWT tamper
     /admin/login?redirect=/admin/users    — deep-link after login

   Step 4 will swap the stub submitLogin() for a real fetch.
   ─────────────────────────────────────────────────────────────── */

/* ── Env band resolver ──────────────────────────────────────── */

const ENV_META = {
  dev: {
    label: 'DEV',
    band: 'var(--color-env-dev)',
    bandBg: 'var(--color-env-dev-bg)',
    tagline: '本地开发环境',
    warning: '你正在本地开发环境中进行管理操作。',
  },
  staging: {
    label: 'STAGING',
    band: 'var(--color-env-staging)',
    bandBg: 'var(--color-env-staging-bg)',
    tagline: '预发布环境',
    warning: '预发布环境 · 操作不会影响生产数据，但会被完整审计。',
  },
  prod: {
    label: 'PROD',
    band: 'var(--color-env-prod)',
    bandBg: 'var(--color-env-prod-bg)',
    tagline: '生产环境',
    warning: '生产环境 · 所有操作都会影响真实用户，且不可撤销。',
  },
};

function resolveEnv() {
  const raw = (import.meta.env.VITE_ENV_NAME || 'dev').toString().toLowerCase();
  if (raw === 'production' || raw === 'prod') return 'prod';
  if (raw === 'staging' || raw === 'stage') return 'staging';
  return 'dev';
}

/* ── Icons ──────────────────────────────────────────────────── */

function LockIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0110 0v4" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" aria-hidden="true"
         style={{ animation: 'spin 0.8s linear infinite' }}>
      <path d="M21 12a9 9 0 11-6.219-8.56" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

/* ── Left env-aware color band ──────────────────────────────── */

function EnvBand({ env }) {
  const meta = ENV_META[env];
  return (
    <div
      className="relative w-full h-full flex flex-col justify-between px-10 py-12"
      style={{ background: meta.band, color: '#FFFFFF' }}
    >
      {/* Top: Logo + env tag */}
      <div>
        <div className="flex items-center gap-3 mb-12">
          <div
            className="w-11 h-11 rounded-card flex items-center justify-center"
            style={{ background: 'rgba(255,255,255,0.18)' }}
          >
            <LockIcon />
          </div>
          <div className="flex flex-col">
            <span className="text-2xl font-brand font-bold leading-none"
                  style={{ letterSpacing: '-0.02em' }}>
              GenPano
            </span>
            <span className="text-xs mt-1 opacity-80 tracking-widest uppercase">
              Admin Console
            </span>
          </div>
        </div>

        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-btn-lg text-xs font-semibold tracking-wider mb-8"
          style={{ background: 'rgba(255,255,255,0.18)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#FFFFFF' }} />
          {meta.label}
        </div>

        <h2 className="text-[28px] font-brand font-bold leading-tight mb-3"
            style={{ letterSpacing: '-0.02em' }}>
          {meta.tagline}
        </h2>
        <p className="text-sm leading-relaxed opacity-90 max-w-sm">
          {meta.warning}
        </p>
      </div>

      {/* Bottom: disclaimers */}
      <div className="space-y-2 text-xs opacity-80">
        <p>仅授权管理员访问 · 所有登录尝试将被记录</p>
        <p>会话 15 分钟自动过期，空闲 7 天强制重新登录</p>
      </div>
    </div>
  );
}

/* ── AdminLoginPage ─────────────────────────────────────────── */

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const env = resolveEnv();
  const { login, status } = useAdminAuth();

  const reason = searchParams.get('reason') || '';
  const redirect = searchParams.get('redirect') || '/admin/dashboard';

  // If a valid session is already active (user navigated back to /admin/login
  // by accident with an unexpired cookie) send them onward. The Provider's
  // initial /refresh probe populates `status`.
  useEffect(() => {
    if (status === 'authenticated') {
      navigate(redirect, { replace: true });
    }
  }, [status, redirect, navigate]);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState(() => {
    if (reason === 'session_expired') {
      return { kind: 'info', text: '会话已过期，请重新登录' };
    }
    if (reason === 'invalid_session') {
      return { kind: 'danger', text: '会话已失效，请重新登录' };
    }
    return null;
  });

  const emailInputRef = useRef(null);
  useEffect(() => {
    emailInputRef.current?.focus();
  }, []);

  const isValidEmail = useCallback(
    (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((v || '').trim()),
    [],
  );

  /* ── Real login (Step 7 swapped in via AdminAuthContext) ── */
  const submitLogin = async (e) => {
    e.preventDefault();
    setError(null);
    setBanner(null);

    if (!isValidEmail(email)) {
      // Anti-enum: don't say "email invalid" specifically either; use the
      // same generic fallback so probing tools learn nothing.
      setError('邮箱或密码错误');
      return;
    }
    if (password.length < 1) {
      setError('邮箱或密码错误');
      return;
    }

    setSubmitting(true);

    try {
      const res = await login({
        email: email.trim().toLowerCase(),
        password,
      });

      const forcePasswordChangeAt = res?.user?.forcePasswordChangeAt ?? null;
      const mustChange =
        forcePasswordChangeAt &&
        new Date(forcePasswordChangeAt).getTime() <= Date.now();

      if (mustChange) {
        navigate('/admin/change-password', { replace: true });
      } else {
        navigate(redirect, { replace: true });
      }
    } catch (err) {
      if (err instanceof AdminApiError) {
        // Map backend error codes to UI copy. All 4xx paths collapse to the
        // same generic message to preserve anti-enum posture — the one
        // exception is explicit rate-limit (429), where the user needs to
        // know waiting is the remedy.
        if (err.status === 429) {
          setError('尝试次数过多，请稍后再试');
        } else {
          setError('邮箱或密码错误');
        }
      } else {
        // Network / unexpected — same generic error.
        setError('暂时无法登录，请稍后再试');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const bannerColor =
    banner?.kind === 'danger'
      ? { bg: 'var(--color-danger-bg)', fg: 'var(--color-danger-text)' }
      : { bg: 'var(--color-info-bg)', fg: 'var(--color-info-text)' };

  return (
    <div className="flex h-screen w-full" style={{ background: 'var(--color-bg-card)' }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>

      {/* Left env color band (hidden on narrow screens) */}
      <div className="hidden lg:block w-[480px] shrink-0">
        <EnvBand env={env} />
      </div>

      {/* Right form panel */}
      <div
        className="flex-1 h-full flex flex-col items-center justify-center relative px-6 py-10 overflow-y-auto"
        style={{ background: 'var(--color-bg-card)' }}
      >
        {/* Compact env indicator visible on mobile (where band is hidden) */}
        <div
          className="lg:hidden absolute top-5 left-5 flex items-center gap-2 px-2.5 py-1 rounded-btn-lg text-[11px] font-semibold tracking-wider"
          style={{
            background: ENV_META[env].bandBg,
            color: ENV_META[env].band,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: ENV_META[env].band }} />
          {ENV_META[env].label}
        </div>

        <div className="w-full max-w-[400px]">
          <div className="mb-7">
            <h1
              className="text-[28px] font-brand font-bold mb-2 leading-tight"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
            >
              管理员登录
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
              GenPano Admin Console · 仅授权运营人员使用
            </p>
          </div>

          {banner && (
            <div
              className="flex items-start gap-2 rounded-card px-3 py-2.5 mb-5 text-sm"
              style={{ background: bannerColor.bg, color: bannerColor.fg }}
              role="status"
            >
              <div style={{ marginTop: 2 }}>
                <AlertIcon />
              </div>
              <span>{banner.text}</span>
            </div>
          )}

          <form onSubmit={submitLogin} className="space-y-4" noValidate>
            <div>
              <label
                className="block text-sm font-semibold mb-1.5"
                style={{ color: 'var(--color-text-body)' }}
                htmlFor="admin-email"
              >
                邮箱
              </label>
              <input
                id="admin-email"
                ref={emailInputRef}
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); if (error) setError(null); }}
                placeholder="admin@genpano.com"
                className={`t-input ${error ? 't-input-error' : ''}`}
                autoComplete="username"
                disabled={submitting}
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label
                  className="block text-sm font-semibold"
                  style={{ color: 'var(--color-text-body)' }}
                  htmlFor="admin-password"
                >
                  密码
                </label>
                <button
                  type="button"
                  onClick={() => navigate('/admin/forgot-password')}
                  className="text-xs hover:underline"
                  style={{ color: 'var(--color-accent)' }}
                >
                  忘记密码？
                </button>
              </div>
              <input
                id="admin-password"
                type="password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (error) setError(null); }}
                placeholder="••••••••••••"
                className={`t-input ${error ? 't-input-error' : ''}`}
                autoComplete="current-password"
                disabled={submitting}
              />
              {error && (
                <p
                  className="text-xs mt-1.5 flex items-center gap-1"
                  style={{ color: 'var(--color-danger-text)' }}
                  role="alert"
                >
                  <AlertIcon />
                  <span>{error}</span>
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <Spinner />
                  <span>登录中…</span>
                </>
              ) : (
                <span>登录</span>
              )}
            </button>
          </form>

          <p
            className="text-xs text-center leading-relaxed mt-7"
            style={{ color: 'var(--color-text-muted)' }}
          >
            本系统仅供 GenPano 授权管理员使用。<br />
            所有登录尝试均被记录，未经授权的访问将被追查。
          </p>
        </div>
      </div>
    </div>
  );
}
