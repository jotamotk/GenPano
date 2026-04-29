import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { useLanguage } from '../context/LanguageContext'
import { authApi } from '../api/auth'
import { showToast } from '../components/Toast'

export default function ResetPasswordPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const [newPasswordError, setNewPasswordError] = useState('')
  const [confirmPasswordError, setConfirmPasswordError] = useState('')

  const isStrongPassword = (value: string) =>
    value.length >= 8 && /[a-z]/.test(value) && /[A-Z]/.test(value) && /\d/.test(value)

  const validate = (): boolean => {
    let valid = true

    if (!isStrongPassword(newPassword)) {
      setNewPasswordError(t.resetPassword.passwordError)
      valid = false
    } else {
      setNewPasswordError('')
    }

    if (!confirmPassword) {
      setConfirmPasswordError(t.resetPassword.confirmError)
      valid = false
    } else if (newPassword !== confirmPassword) {
      setConfirmPasswordError(t.resetPassword.mismatchError)
      valid = false
    } else {
      setConfirmPasswordError('')
    }

    return valid
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    setIsLoading(true)
    try {
      await authApi.resetPassword(token, newPassword)
      navigate('/reset-password-success')
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
        <h1 className="text-[32px] font-brand font-semibold text-themed-primary">
          {t.resetPassword.title}
        </h1>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* New Password */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            {t.resetPassword.newPasswordLabel}
            <span className="text-red-500 ml-0.5">★</span>
            <button
              type="button"
              title={t.resetPassword.passwordInfo}
              className="ml-1.5 text-gray-400 hover:text-gray-600 transition-colors inline-flex items-center"
            >
              <InfoIcon />
            </button>
          </label>
          <div className="relative">
            <input
              type={showNewPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={newPassword}
              onChange={e => { setNewPassword(e.target.value); setNewPasswordError('') }}
              placeholder={t.resetPassword.passwordPlaceholder}
              aria-invalid={!!newPasswordError}
              className={`w-full px-3.5 py-2.5 pr-10 text-sm rounded-lg border transition-colors outline-none
                ${newPasswordError
                  ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                  : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                } placeholder:text-gray-400 text-gray-900`}
            />
            <button
              type="button"
              onClick={() => setShowNewPassword(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              tabIndex={-1}
            >
              {showNewPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>
          {newPasswordError && (
            <p className="mt-1 text-xs text-red-500" role="alert">{newPasswordError}</p>
          )}
        </div>

        {/* Confirm Password */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            {t.resetPassword.confirmPasswordLabel}
            <span className="text-red-500 ml-0.5">★</span>
          </label>
          <div className="relative">
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={e => { setConfirmPassword(e.target.value); setConfirmPasswordError('') }}
              placeholder={t.resetPassword.passwordPlaceholder}
              aria-invalid={!!confirmPasswordError}
              className={`w-full px-3.5 py-2.5 pr-10 text-sm rounded-lg border transition-colors outline-none
                ${confirmPasswordError
                  ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                  : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                } placeholder:text-gray-400 text-gray-900`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              tabIndex={-1}
            >
              {showConfirmPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>
          {confirmPasswordError && (
            <p className="mt-1 text-xs text-red-500" role="alert">{confirmPasswordError}</p>
          )}
        </div>

        {/* Submit button */}
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
          ) : t.resetPassword.submitButton}
        </button>
      </form>
    </AuthLayout>
  )
}

function InfoIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
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
