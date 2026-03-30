import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { useLanguage } from '../context/LanguageContext'
import { useEmailValidation } from '../hooks/useEmailValidation'
import { authApi } from '../api/auth'
import { showToast } from '../components/Toast'

export default function ForgotPasswordPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const { error: emailError, validate, handleBlur, handleChange } = useEmailValidation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate(email)) return

    setIsLoading(true)
    try {
      await authApi.forgotPassword(email)
      navigate(`/email-sent?email=${encodeURIComponent(email)}&type=reset`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      showToast(msg || t.errors.serverError, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthLayout>
      <div className="mb-8">
        <h1 className="text-[32px] font-heading font-semibold text-[#1A1A2E] mb-2">
          {t.forgotPassword.title}
        </h1>
        <p className="text-sm text-gray-500">
          {t.forgotPassword.noAccount}{' '}
          <Link
            to="/register"
            className="text-primary-500 hover:text-primary-600 hover:underline font-medium transition-colors"
          >
            {t.forgotPassword.signUp}
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
            {t.forgotPassword.emailLabel}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={e => { setEmail(e.target.value); handleChange(e.target.value) }}
            onBlur={() => handleBlur(email)}
            placeholder={t.forgotPassword.emailPlaceholder}
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
              {t.forgotPassword.emailError}
            </p>
          )}
        </div>

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
          ) : t.forgotPassword.submitButton}
        </button>
      </form>
    </AuthLayout>
  )
}
