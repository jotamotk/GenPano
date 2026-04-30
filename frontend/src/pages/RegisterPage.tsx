import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { useLanguage } from '../context/LanguageContext'
import { useEmailValidation } from '../hooks/useEmailValidation'
import { authApi } from '../api/auth'
import { showToast } from '../components/Toast'

export default function RegisterPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [emailExists, setEmailExists] = useState(false)

  const { error: emailError, validate, handleBlur, handleChange } = useEmailValidation()

  // Pre-fill email from query param (redirected from login step 1)
  useEffect(() => {
    const emailParam = searchParams.get('email')
    if (emailParam) setEmail(emailParam)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setEmailExists(false)

    if (!validate(email)) return

    setIsLoading(true)
    try {
      await authApi.register(email)
      navigate(`/email-sent?email=${encodeURIComponent(email)}&type=verify`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.toLowerCase().includes('exists') || msg.toLowerCase().includes('already') || msg.toLowerCase().includes('已注册')) {
        setEmailExists(true)
      } else {
        showToast(msg || t.errors.serverError, 'error')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleRegister = () => {
    window.location.href = authApi.getGoogleOAuthUrl()
  }

  return (
    <AuthLayout>
      {/* Title */}
      <div className="mb-8">
        <h1 className="text-[32px] font-heading font-semibold text-[#1A1A2E] mb-2">
          {t.register.title}
        </h1>
        <p className="text-sm text-gray-500">
          {t.register.hasAccount}{' '}
          <Link
            to="/login"
            className="text-primary-500 hover:text-primary-600 hover:underline font-medium transition-colors"
          >
            {t.register.login}
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Email field */}
        <div>
          <label
            htmlFor="email"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            {t.register.emailLabel}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={e => {
              setEmail(e.target.value)
              setEmailExists(false)
              handleChange(e.target.value)
            }}
            onBlur={() => handleBlur(email)}
            placeholder={t.register.emailPlaceholder}
            aria-describedby={emailError ? 'email-error' : undefined}
            aria-invalid={!!emailError}
            className={`w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors outline-none
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

        {/* Email exists hint */}
        {emailExists && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3.5 py-2.5 text-sm text-amber-800">
            {t.register.emailExists}{' '}
            <Link to="/login" className="font-medium underline hover:no-underline">
              {t.register.login} →
            </Link>
          </div>
        )}

        {/* Register button */}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full h-12 px-4 text-base font-semibold text-white rounded-[10px] transition-colors
            bg-primary-500 hover:bg-primary-600 hover:-translate-y-[1px] hover:shadow-lg hover:shadow-purple-500/25 active:bg-primary-700 active:translate-y-0 focus:ring-2 focus:ring-primary-100 focus:outline-none
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
          ) : t.register.registerButton}
        </button>

        {/* Privacy policy — plain text, no link */}
        <p className="text-xs text-gray-400 text-center leading-relaxed">
          {t.register.privacyText}
        </p>
      </form>

      {/* Divider */}
      <div className="my-6 flex items-center gap-3">
        <div className="flex-1 h-px bg-gray-200" />
        <span className="text-xs text-gray-400 font-medium">{t.or}</span>
        <div className="flex-1 h-px bg-gray-200" />
      </div>

      {/* Google OAuth button */}
      <button
        type="button"
        onClick={handleGoogleRegister}
        className="w-full h-12 flex items-center justify-center gap-3 px-4 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-[10px] hover:bg-gray-50 hover:shadow-sm focus:ring-2 focus:ring-primary-100 focus:outline-none transition-all duration-200"
      >
        <GoogleIcon />
        {t.register.googleButton}
      </button>
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
