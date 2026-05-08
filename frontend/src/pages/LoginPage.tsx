import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { useLanguage } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'
import { useEmailValidation } from '../hooks/useEmailValidation'
import { authApi } from '../api/auth'
import { showToast } from '../components/Toast'
import { ApiError } from '../lib/apiClient'
import { showApiError } from '../lib/showApiError'

export default function LoginPage() {
  const { t } = useLanguage()
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState(1)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [credentialsError, setCredentialsError] = useState('')

  const { error: emailError, validate, handleBlur, handleChange, reset: resetEmailError } = useEmailValidation()

  // Pre-fill email from query param (e.g. coming back from /register)
  useEffect(() => {
    const emailParam = searchParams.get('email')
    if (emailParam) setEmail(emailParam)

    const error = searchParams.get('error')
    if (error === 'invalid_email') {
      showToast(t.validation.emailInvalid, 'error')
    } else if (error === 'oauth_failed') {
      showToast(t.errors.serverError, 'error')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleStep1Submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate(email)) return

    setIsLoading(true)
    try {
      const result = await authApi.checkEmail(email)
      if (result.exists) {
        setStep(2)
        setPassword('')
        setPasswordError('')
        setCredentialsError('')
      } else {
        navigate(`/register?email=${encodeURIComponent(email)}`)
      }
    } catch {
      // On error, still proceed to step 2 (let login handle it)
      setStep(2)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStep2Submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')
    setCredentialsError('')

    if (!password.trim()) {
      setPasswordError(t.login.passwordEmpty)
      return
    }

    setIsLoading(true)
    try {
      await login(email, password)
      showToast(t.login.loginSuccess, 'success')
      navigate('/dashboard')
    } catch (err: unknown) {
      // Bad-credentials → keep inline form error (no red toast). Anything
      // else (network down, 500, rate limited, ...) goes through the
      // sticky error panel so the user can copy a request_id for support.
      if (
        err instanceof ApiError &&
        (err.is('invalid_credentials') || err.is('unauthorized') || err.status === 401)
      ) {
        setCredentialsError(t.login.invalidCredentials)
      } else {
        showApiError(err, { fallback: t.errors.serverError })
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleEditEmail = () => {
    setStep(1)
    setPassword('')
    setPasswordError('')
    setCredentialsError('')
    resetEmailError()
  }

  const handleGoogleLogin = () => {
    window.location.href = authApi.getGoogleOAuthUrl()
  }

  return (
    <AuthLayout>
      {/* Title */}
      <div className="mb-8">
        <h1 className="text-[32px] font-heading font-semibold text-[#1A1A2E] mb-2">
          {t.login.title}
        </h1>
        <p className="text-sm text-gray-500">
          {t.login.noAccount}{' '}
          <Link
            to="/register"
            className="text-primary-500 hover:text-primary-600 hover:underline font-medium transition-colors"
          >
            {t.login.signUp}
          </Link>
        </p>
      </div>

      {step === 1 ? (
        <form onSubmit={handleStep1Submit} noValidate className="space-y-4">
          {/* Email field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
              {t.login.emailLabel}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={e => {
                setEmail(e.target.value)
                handleChange(e.target.value)
              }}
              onBlur={() => handleBlur(email)}
              placeholder={t.login.emailPlaceholder}
              aria-describedby={emailError ? 'email-error' : undefined}
              aria-invalid={!!emailError}
              className={`w-full px-3.5 h-12 text-sm rounded-lg border transition-colors outline-none
                ${emailError
                  ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                  : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                } placeholder:text-gray-400 text-gray-900`}
            />
            {emailError && (
              <p id="email-error" className="mt-1 text-xs text-red-500" role="alert">
                {emailError}
              </p>
            )}
          </div>

          {/* Continue button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-12 px-4 text-base font-semibold text-white rounded-[10px] transition-colors
              bg-primary-500 hover:bg-primary-600 hover:-translate-y-[1px] hover:shadow-lg hover:shadow-purple-500/25
              active:bg-primary-700 active:translate-y-0 focus:ring-2 focus:ring-primary-100 focus:outline-none
              disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading...
              </span>
            ) : t.login.continueButton}
          </button>

          {/* Forgot password */}
          <div className="text-right">
            <Link
              to="/forgot-password"
              className="text-xs text-gray-400 hover:text-primary-500 transition-colors"
            >
              {t.login.forgotPassword}
            </Link>
          </div>

          {/* Hint text */}
          <p className="text-xs text-gray-400 text-center">{t.login.noAccountHint}</p>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-400 font-medium">{t.or}</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          {/* Google button */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            className="w-full h-12 flex items-center justify-center gap-3 px-4 text-sm font-medium
              text-gray-600 bg-white border border-gray-200 rounded-[10px] hover:bg-gray-50 hover:shadow-sm
              focus:ring-2 focus:ring-primary-100 focus:outline-none transition-all duration-200"
          >
            <GoogleIcon />
            {t.login.googleButton}
          </button>
        </form>
      ) : (
        <form onSubmit={handleStep2Submit} noValidate className="space-y-4">
          {/* Read-only email with pencil icon */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              {t.login.emailLabel}
            </label>
            <div className="relative">
              <input
                type="email"
                value={email}
                readOnly
                className="w-full px-3.5 h-12 pr-10 text-sm rounded-lg border border-gray-200
                  bg-gray-50 text-gray-700 outline-none cursor-default"
              />
              <button
                type="button"
                onClick={handleEditEmail}
                title={t.login.editEmail}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-primary-500 transition-colors"
              >
                <PencilIcon />
              </button>
            </div>
          </div>

          {/* Password field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
              {t.login.passwordLabel}
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                autoFocus
                value={password}
                onChange={e => {
                  setPassword(e.target.value)
                  setPasswordError('')
                  setCredentialsError('')
                }}
                placeholder={t.login.passwordPlaceholder}
                aria-invalid={!!(passwordError || credentialsError)}
                className={`w-full px-3.5 h-12 pr-10 text-sm rounded-lg border transition-colors outline-none
                  ${(passwordError || credentialsError)
                    ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                    : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                  } placeholder:text-gray-400 text-gray-900`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {passwordError && (
              <p className="mt-1 text-xs text-red-500" role="alert">{passwordError}</p>
            )}
            {credentialsError && (
              <p className="mt-1 text-xs text-red-500" role="alert">{credentialsError}</p>
            )}
          </div>

          {/* Continue button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-12 px-4 text-base font-semibold text-white rounded-[10px] transition-colors
              bg-primary-500 hover:bg-primary-600 hover:-translate-y-[1px] hover:shadow-lg hover:shadow-purple-500/25
              active:bg-primary-700 active:translate-y-0 focus:ring-2 focus:ring-primary-100 focus:outline-none
              disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading...
              </span>
            ) : t.login.continueButton}
          </button>

          {/* Forgot password */}
          <div className="text-right">
            <Link
              to="/forgot-password"
              className="text-xs text-gray-400 hover:text-primary-500 transition-colors"
            >
              {t.login.forgotPassword}
            </Link>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-400 font-medium">{t.or}</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          {/* Google button */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            className="w-full h-12 flex items-center justify-center gap-3 px-4 text-sm font-medium
              text-gray-600 bg-white border border-gray-200 rounded-[10px] hover:bg-gray-50 hover:shadow-sm
              focus:ring-2 focus:ring-primary-100 focus:outline-none transition-all duration-200"
          >
            <GoogleIcon />
            {t.login.googleButtonStep2}
          </button>
        </form>
      )}
    </AuthLayout>
  )
}

function GoogleIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
    </svg>
  )
}
