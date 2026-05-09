import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useLocale } from '../contexts/LocaleContext';
import { authApi } from '../api/auth';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { validateEmailFormat } from '../hooks/useEmailValidation';
import AuthVisualPanel from '../components/AuthVisualPanel';

/* ─────────────────────────────────────────────────────────────
   AuthPage — PRD §4.1.1 + §4.1.1-form (Email-first 2-step)
   ─────────────────────────────────────────────────────────────
   2026-04-19 重构: 原 login/register/forgot 三模式单表单改为
   Stripe/Linear/Vercel/Claude.ai 的 identifier-first 2 步流程.

   States (step machine):
     step_0_email         → 只输邮箱 + Continue
     step_1_looking_up    → loading (anti-enum 固定 ≥400ms)
     step_1_new           → 新邮箱创建账号 (password + confirm)
     step_1_existing      → 已注册输密码登录
     step_1_forgot        → 忘记密码: 邮箱 + 发送重置
     step_1_forgot_sent   → 重置邮件已发送确认

   URL 契约 (PRD §4.1.1-form):
     /login 和 /register 两条路由都保留, 均 mount 本组件.
     `type` prop 仅用于默认 focus (Step 0 email) 和 deep-link 预填.
     Step 切换不改 URL — 状态内部化, 避免 refresh 丢 progress.

   Query params (原样透传, 不动):
     monitor_brand = anon WatchBrandButton 点击时的 brand id
     return_to     = auth 完成后的重定向绝对路径
     action        = T1-T9 hook 二级意图 (如 create_project)
     entry_source  = 触发 signup 的 Empty Surface 标识
     email         = 深链预填 (Landing?email=foo 式进入)

   API:
     POST /api/auth/lookup — 本 Session stub 一个本地 mock, 真实接入见
     SESSIONS §1. 响应固定 ≥400ms (anti-enum), 结构两分支一致:
       { next: 'register' | 'login', hasPassword: boolean }
*/

/* ── i18n 小工具: 失败时回退到 key, 避免白屏 ── */
function tOr(t, key, fallback) {
  const v = t(key);
  return v && v !== key ? v : fallback;
}

/* ── Icons ───────────────────────────────────────────────── */

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20" />
      <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
    </svg>
  );
}

function ArrowLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <path d="M21 12a9 9 0 11-6.219-8.56" />
    </svg>
  );
}

/* ── Left brand panel ─────────────────────────────────────────
   Stripe Light 风格: 浅色背景, 用 tokens, 无装饰 blob. */

function LeftPanel({ t }) {
  return (
    <div
      className="relative w-full h-full overflow-hidden flex flex-col items-center justify-center px-12"
      style={{
        background: 'var(--color-bg-page)',
        borderRight: '1px solid var(--color-border-subtle)',
      }}
    >
      <div className="relative z-10 max-w-md">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-11 h-11 rounded-card flex items-center justify-center"
            style={{ background: 'var(--color-accent)' }}
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="white" />
              <path d="M8 12l3 3 5-6" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span
            className="text-2xl font-brand font-bold"
            style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
          >
            GenPano
          </span>
        </div>

        <div
          className="h-[300px] overflow-hidden rounded-[28px] border mb-8 shadow-[0_18px_60px_rgba(28,34,58,0.10)]"
          style={{ borderColor: 'var(--color-border-subtle)' }}
        >
          <ParticleArt />
        </div>

        <h2
          className="text-[28px] font-brand font-bold leading-tight mb-4"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
        >
          {tOr(t, 'auth.leftpanel.tagline', '管理你的品牌监测数据')}
        </h2>
        <p
          className="text-base leading-relaxed mb-8"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {tOr(
            t,
            'auth.leftpanel.body',
            '登录后查看品牌可见度、情感、引用和竞品表现，继续完成项目配置与报告管理。'
          )}
        </p>

        {/* Feature bullets — muted, non-decorative */}
        <div className="space-y-3">
          {[
            ['auth.leftpanel.bullet_1', '品牌、竞品和人群分组统一管理'],
            ['auth.leftpanel.bullet_2', '监测结果、诊断和报告集中查看'],
            ['auth.leftpanel.bullet_3', '支持团队后续接入 API 与自动化流程'],
          ].map(([key, fallback]) => (
            <div key={key} className="flex items-start gap-2.5">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center mt-0.5 shrink-0"
                style={{ background: 'var(--color-accent-soft)' }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ color: 'var(--color-accent)' }}>
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <span className="text-sm leading-relaxed" style={{ color: 'var(--color-text-body)' }}>
                {tOr(t, key, fallback)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── AuthPage ───────────────────────────────────────────── */

/**
 * @param {object} props
 * @param {'login'|'register'} [props.type] — mount route hint only.
 *   Step 0 is shown regardless; type only nudges the "new user" framing
 *   on /register (subtitle emphasizes sign-up) vs "returning" on /login.
 */
export default function AuthPage({ type = 'login', initialStep = null }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t, locale, setLocale } = useLocale();
  const { setLanguage } = useLanguage();
  const { setTokenAndUser } = useAuth();

  /* ── Query passthrough (PRD §4.1.2a / §4.1.1c / §4.1.1d) ── */
  const monitorBrand = searchParams.get('monitor_brand') || '';
  const returnTo = searchParams.get('redirect') || searchParams.get('return_to') || '';
  const action = searchParams.get('action') || '';
  const entrySource = searchParams.get('entry_source') || '';
  const emailPrefill = searchParams.get('email') || '';

  const passthroughQs = useMemo(() => {
    const p = new URLSearchParams();
    if (monitorBrand) p.set('monitor_brand', monitorBrand);
    if (returnTo) p.set('return_to', returnTo);
    if (action) p.set('action', action);
    if (entrySource) p.set('entry_source', entrySource);
    const s = p.toString();
    return s ? `?${s}` : '';
  }, [monitorBrand, returnTo, action, entrySource]);

  /* ── State machine ── */
  const [step, setStep] = useState(initialStep === 'forgot' ? 'step_1_forgot' : 'step_0_email');
  const [email, setEmail] = useState(emailPrefill);
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [nextAction, setNextAction] = useState(null); // 'register' | 'login' | null
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // OAuth callback notice — separate from `error` so it renders as a
  // banner above the form instead of styling the email input as invalid.
  // ?error=oauth_not_configured | oauth_failed comes from the backend
  // when GOOGLE_CLIENT_ID is missing or the OAuth handshake aborts.
  const oauthErrorParam = searchParams.get('error');
  const [oauthNotice, setOAuthNotice] = useState(
    oauthErrorParam === 'oauth_not_configured'
      ? tOr(t, 'auth.errors.oauth_not_configured', 'Google 登录暂未启用，请使用邮箱继续。')
      : oauthErrorParam === 'oauth_failed'
        ? tOr(t, 'auth.errors.oauth_failed', 'Google 登录未完成，请重试或使用邮箱继续。')
        : null,
  );

  const emailInputRef = useRef(null);
  const passwordInputRef = useRef(null);

  // Focus the right input when step changes
  useEffect(() => {
    if (step === 'step_0_email' && emailInputRef.current) {
      emailInputRef.current.focus();
    } else if ((step === 'step_1_new' || step === 'step_1_existing') && passwordInputRef.current) {
      passwordInputRef.current.focus();
    }
  }, [step]);

  /* ── Validation ── */
  const isValidEmail = useCallback((v) => validateEmailFormat(v) === 'valid', []);

  const safeRedirect = useCallback((value) => {
    return value && value.startsWith('/') && !value.startsWith('//') ? value : '/brand/overview';
  }, []);

  /* ── Step 0 → Step 1 (lookup) ── */
  const submitEmail = async (e) => {
    if (e) e.preventDefault();
    setError(null);

    if (!isValidEmail(email)) {
      setError(tOr(t, 'auth.errors.email_invalid', '请输入有效的邮箱地址'));
      return;
    }

    setSubmitting(true);
    setStep('step_1_looking_up');

    try {
      const { next } = await authApi.lookup(email);
      setNextAction(next);
      setPassword('');
      setPasswordConfirm('');
      setStep(next === 'register' ? 'step_1_new' : 'step_1_existing');
    } catch {
      setError(tOr(t, 'auth.errors.lookup_failed', '服务暂时繁忙，请稍后重试'));
      setStep('step_0_email');
    } finally {
      setSubmitting(false);
    }
  };

  /* ── Step 1 New → Create account ── */
  const submitRegister = async (e) => {
    e.preventDefault();
    setError(null);

    if (!isValidEmail(email)) {
      setError(tOr(t, 'auth.errors.email_invalid', '请输入有效的邮箱地址'));
      return;
    }

    setSubmitting(true);
    try {
      const result = await authApi.register(email);
      const qs = new URLSearchParams({ email, type: 'verify' });
      if (result?.previewUrl) qs.set('previewUrl', result.previewUrl);
      if (returnTo) qs.set('redirect', returnTo);
      navigate(`/email-sent?${qs.toString()}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      setError(msg || tOr(t, 'auth.errors.lookup_failed', '服务暂时繁忙，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  /* ── Step 1 Existing → Login ── */
  const submitLogin = async (e) => {
    e.preventDefault();
    setError(null);

    if (password.length < 1) {
      setError(tOr(t, 'auth.errors.password_too_short', '密码至少需要 8 个字符'));
      return;
    }

    setSubmitting(true);
    try {
      const res = await authApi.login(email, password);
      setTokenAndUser(res.token, res.user);
      navigate(safeRedirect(returnTo));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      setError(msg || tOr(t, 'auth.errors.invalid_credentials', '用户名或密码不正确'));
    } finally {
      setSubmitting(false);
    }
  };

  /* ── Step 1 Forgot → Send reset link ── */
  const submitForgot = async (e) => {
    e.preventDefault();
    setError(null);

    if (!isValidEmail(email)) {
      setError(tOr(t, 'auth.errors.email_invalid', '请输入有效的邮箱地址'));
      return;
    }

    setSubmitting(true);
    try {
      await authApi.forgotPassword(email);
      const qs = new URLSearchParams({ email, type: 'reset' });
      navigate(`/email-sent?${qs.toString()}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      setError(msg || tOr(t, 'auth.errors.lookup_failed', '服务暂时繁忙，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  const startGoogleOAuth = () => {
    setOAuthNotice(null);
    window.location.href = authApi.getGoogleOAuthUrl();
  };

  /* ── Back / switch email ── */
  const backToEmail = () => {
    setError(null);
    setPassword('');
    setPasswordConfirm('');
    setNextAction(null);
    setStep('step_0_email');
  };

  const gotoForgot = () => {
    setError(null);
    setPassword('');
    setStep('step_1_forgot');
  };

  const backToLogin = () => {
    setError(null);
    setStep('step_1_existing');
  };

  /* ── Language toggle — real setLocale, no more placeholder button ── */
  const toggleLocale = () => {
    const nextLocale = locale === 'zh-CN' ? 'en-US' : 'zh-CN';
    setLocale(nextLocale);
    setLanguage(nextLocale === 'zh-CN' ? 'zh' : 'en');
  };

  /* ── Render helpers ── */

  const renderStep0 = () => (
    <form onSubmit={submitEmail} className="space-y-4" noValidate>
      {oauthNotice && (
        <div
          role="status"
          className="rounded-card p-3 text-sm leading-relaxed"
          style={{
            background: 'var(--color-warning-bg, rgba(255,165,0,0.08))',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-body)',
          }}
        >
          {oauthNotice}
        </div>
      )}
      <div>
        <label className="block text-sm font-semibold mb-1.5" style={{ color: 'var(--color-text-body)' }}>
          {tOr(t, 'auth.step0.email_label', '邮箱')}
        </label>
        <input
          ref={emailInputRef}
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (error) setError(null);
          }}
          placeholder={tOr(t, 'auth.step0.email_placeholder', 'name@example.com')}
          className={`t-input ${error ? 't-input-error' : ''}`}
          autoComplete="email"
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
        className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {submitting ? (
          <>
            <Spinner />
            <span>{tOr(t, 'auth.step0.submitting', '请稍候…')}</span>
          </>
        ) : (
          <span>{tOr(t, 'auth.step0.submit', '继续')}</span>
        )}
      </button>

      <div className="flex items-center gap-3 py-1">
        <div className="flex-1 h-px" style={{ background: 'var(--color-border-subtle)' }} />
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {tOr(t, 'auth.step0.divider', '或')}
        </span>
        <div className="flex-1 h-px" style={{ background: 'var(--color-border-subtle)' }} />
      </div>

      <button
        type="button"
        className="t-btn-secondary w-full h-11 flex items-center justify-center gap-2.5 text-sm"
        disabled={submitting}
        onClick={startGoogleOAuth}
      >
        <GoogleIcon />
        <span>{tOr(t, 'auth.step0.oauth_google', '用 Google 账号继续')}</span>
      </button>
    </form>
  );

  const renderLookingUp = () => (
    <div className="py-8 flex flex-col items-center justify-center gap-3" aria-live="polite">
      <div style={{ color: 'var(--color-accent)' }}>
        <Spinner />
      </div>
      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
        {tOr(t, 'auth.step0.submitting', '请稍候…')}
      </span>
    </div>
  );

  const renderEmailChip = (chipKey, chipFallback) => (
    <div
      className="flex items-center justify-between mb-4 px-3 py-2 rounded-card"
      style={{
        background: 'var(--color-bg-page)',
        border: '1px solid var(--color-border-subtle)',
      }}
    >
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-[10px] uppercase tracking-wide font-semibold" style={{ color: 'var(--color-text-muted)' }}>
          {tOr(t, chipKey, chipFallback)}
        </span>
        <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
          {email}
        </span>
      </div>
      <button
        type="button"
        onClick={backToEmail}
        className="text-xs font-medium shrink-0 hover:underline"
        style={{ color: 'var(--color-accent)' }}
      >
        {tOr(t, 'auth.step1.new.switch_email', '换个邮箱')}
      </button>
    </div>
  );

  const renderStep1New = () => (
    <form onSubmit={submitRegister} className="space-y-4" noValidate>
      {renderEmailChip('auth.step1.new.chip', '新账号')}

      <div
        className="rounded-card p-4"
        style={{
          background: 'var(--color-auth-note-bg)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-body)' }}>
          {tOr(
            t,
            'auth.step1.new.verify_body',
            '我们会发送一封验证邮件。验证完成后，你可以设置密码并补充账号信息。'
          )}
        </p>
        {error && (
          <p className="text-xs mt-2" style={{ color: 'var(--color-danger-text)' }}>
            {error}
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
            <span>{tOr(t, 'auth.step1.new.submitting', '发送中…')}</span>
          </>
        ) : (
          <span>{tOr(t, 'auth.step1.new.submit', '发送验证邮件')}</span>
        )}
      </button>

      <p className="text-xs text-center leading-relaxed mt-4" style={{ color: 'var(--color-text-muted)' }}>
        {tOr(t, 'auth.step1.new.terms_prefix', '继续即表示你同意 GenPano 的')}{' '}
        <a className="hover:underline" style={{ color: 'var(--color-accent)' }}>
          {tOr(t, 'auth.step1.new.terms', '服务条款')}
        </a>{' '}
        {tOr(t, 'auth.step1.new.terms_join', '和')}{' '}
        <a className="hover:underline" style={{ color: 'var(--color-accent)' }}>
          {tOr(t, 'auth.step1.new.privacy', '隐私政策')}
        </a>
      </p>
    </form>
  );

  const renderStep1Existing = () => (
    <form onSubmit={submitLogin} className="space-y-4" noValidate>
      {renderEmailChip('auth.step1.existing.chip', '已有账号')}

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-sm font-semibold" style={{ color: 'var(--color-text-body)' }}>
            {tOr(t, 'auth.step1.existing.password_label', '密码')}
          </label>
          <button
            type="button"
            onClick={gotoForgot}
            className="text-xs hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            {tOr(t, 'auth.step1.existing.forgot_link', '忘记密码？')}
          </button>
        </div>
        <input
          ref={passwordInputRef}
          type="password"
          value={password}
          onChange={(e) => { setPassword(e.target.value); if (error) setError(null); }}
          placeholder="••••••••"
          className={`t-input ${error ? 't-input-error' : ''}`}
          autoComplete="current-password"
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
        className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {submitting ? (
          <>
            <Spinner />
            <span>{tOr(t, 'auth.step1.existing.submitting', '登录中…')}</span>
          </>
        ) : (
          <span>{tOr(t, 'auth.step1.existing.submit', '登录')}</span>
        )}
      </button>
    </form>
  );

  const renderStep1Forgot = () => (
    <form onSubmit={submitForgot} className="space-y-4" noValidate>
      <button
        type="button"
        onClick={backToLogin}
        className="flex items-center gap-1.5 text-sm mb-2 hover:underline"
        style={{ color: 'var(--color-text-muted)' }}
      >
        <ArrowLeft />
        <span>{tOr(t, 'auth.step1.forgot.back', '返回登录')}</span>
      </button>

      <div>
        <label className="block text-sm font-semibold mb-1.5" style={{ color: 'var(--color-text-body)' }}>
          {tOr(t, 'auth.step1.forgot.email_label', '邮箱')}
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value); if (error) setError(null); }}
          placeholder={tOr(t, 'auth.step0.email_placeholder', 'name@example.com')}
          className={`t-input ${error ? 't-input-error' : ''}`}
          autoComplete="email"
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
        className="t-btn-primary w-full h-11 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {submitting ? (
          <>
            <Spinner />
            <span>{tOr(t, 'auth.step1.forgot.submitting', '发送中…')}</span>
          </>
        ) : (
          <span>{tOr(t, 'auth.step1.forgot.submit', '发送重置链接')}</span>
        )}
      </button>
    </form>
  );

  const renderStep1ForgotSent = () => {
    const bodyTpl = tOr(
      t,
      'auth.step1.forgot.sent_body',
      '如果 {email} 已注册，我们会发送密码重置邮件。请在 1 小时内完成重置。'
    );
    const body = bodyTpl.replace('{email}', email);
    return (
      <div
        className="rounded-card p-5"
        style={{ background: 'var(--color-success-bg)', border: '1px solid var(--color-border-subtle)' }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'var(--color-success)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" aria-hidden="true">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>
              {tOr(t, 'auth.step1.forgot.sent_title', '重置邮件已发送')}
            </h3>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-body)' }}>
              {body}
            </p>
            <div className="flex items-center gap-4 mt-3">
              <button
                type="button"
                onClick={submitForgot}
                className="text-sm hover:underline"
                style={{ color: 'var(--color-accent)' }}
              >
                {tOr(t, 'auth.step1.forgot.resend', '重新发送')}
              </button>
              <button
                type="button"
                onClick={backToLogin}
                className="text-sm hover:underline"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {tOr(t, 'auth.step1.forgot.back', '返回登录')}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  /* ── Header copy varies by step (but /login vs /register URL does not) ── */
  const headerFor = () => {
    if (step === 'step_1_new') {
      return {
        title: tOr(t, 'auth.step1.new.title', '验证你的邮箱'),
        subtitle: null,
      };
    }
    if (step === 'step_1_existing') {
      return {
        title: tOr(t, 'auth.step1.existing.title', '输入密码'),
        subtitle: null,
      };
    }
    if (step === 'step_1_forgot' || step === 'step_1_forgot_sent') {
      return {
        title: tOr(t, 'auth.step1.forgot.title', '重置你的密码'),
        subtitle:
          step === 'step_1_forgot'
            ? tOr(t, 'auth.step1.forgot.subtitle', '输入邮箱，我们会发送密码重置链接。')
            : null,
      };
    }
    // step_0_email or step_1_looking_up
    return {
      title: tOr(t, 'auth.step0.title', '登录或注册'),
      subtitle: tOr(t, 'auth.step0.subtitle', '输入邮箱，继续访问你的 GenPano 工作台。'),
    };
  };

  const { title, subtitle } = headerFor();

  /* ── Render ── */

  return (
    <div className="flex h-screen w-full" style={{ background: 'var(--color-bg-card)' }}>
      {/* inject small keyframes for Spinner without touching global css */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>

      <AuthVisualPanel />

      {/* Right form panel */}
      <div
        className="w-full lg:w-[520px] lg:shrink-0 h-full flex flex-col items-center justify-center relative px-6 py-10 overflow-y-auto"
        style={{ background: 'var(--color-bg-card)' }}
      >
        {/* Language toggle */}
        <button
          type="button"
          onClick={toggleLocale}
          className="absolute top-5 right-5 flex items-center gap-2 h-9 px-3 rounded-btn-lg text-sm transition-colors"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-body)',
          }}
          aria-label={tOr(t, 'lang.switch_aria', 'Switch language')}
        >
          <GlobeIcon />
          <span>{locale === 'zh-CN' ? 'English' : '中文'}</span>
        </button>

        <div className="w-full max-w-[400px]">
          {/* Header */}
          <div className="mb-7">
            <h1
              className="text-[28px] font-brand font-bold mb-2 leading-tight"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
            >
              {title}
            </h1>
            {subtitle && (
              <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                {subtitle}
              </p>
            )}
          </div>

          {/* Body */}
          {step === 'step_0_email' && renderStep0()}
          {step === 'step_1_looking_up' && renderLookingUp()}
          {step === 'step_1_new' && renderStep1New()}
          {step === 'step_1_existing' && renderStep1Existing()}
          {step === 'step_1_forgot' && renderStep1Forgot()}
          {step === 'step_1_forgot_sent' && renderStep1ForgotSent()}
        </div>
      </div>
    </div>
  );
}
