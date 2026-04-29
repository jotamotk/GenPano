import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useLanguage } from '../context/LanguageContext'
import { useAuth } from '../context/AuthContext'
import { authApi } from '../api/auth'
import { useEmailValidation } from '../hooks/useEmailValidation'
import { showToast } from '../components/Toast'
import ParticleArt from '../components/ParticleArt'
import LanguageSwitcher from '../components/LanguageSwitcher'

export default function SetupPage() {
  const { t, language } = useLanguage()
  const navigate = useNavigate()
  const { setTokenAndUser } = useAuth()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [name, setName] = useState('')
  const [company, setCompany] = useState('')
  const [newsletter, setNewsletter] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [requiresPassword, setRequiresPassword] = useState(true)
  const [tokenLoading, setTokenLoading] = useState(true)

  const [emailError, setEmailError] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [nameError, setNameError] = useState('')
  const [companyError, setCompanyError] = useState('')

  const { validate: validateEmail } = useEmailValidation()

  const isStrongPassword = (value: string) =>
    value.length >= 8 && /[a-z]/.test(value) && /[A-Z]/.test(value) && /\d/.test(value)

  useEffect(() => {
    let cancelled = false
    if (!token) {
      setTokenLoading(false)
      showToast(t.errors.serverError, 'error')
      return
    }

    authApi.getSetupToken(token)
      .then(info => {
        if (cancelled) return
        setEmail(info.email)
        setName(info.name || '')
        setCompany(info.company || '')
        setRequiresPassword(info.requiresPassword)
      })
      .catch(err => {
        const msg = err instanceof Error ? err.message : ''
        showToast(msg || t.errors.serverError, 'error')
      })
      .finally(() => {
        if (!cancelled) setTokenLoading(false)
      })

    return () => { cancelled = true }
  }, [token, t.errors.serverError])

  const validate = (): boolean => {
    let valid = true

    if (!email.trim()) {
      setEmailError(t.setup.emailError)
      valid = false
    } else if (!validateEmail(email)) {
      setEmailError(t.setup.emailInvalid)
      valid = false
    } else {
      setEmailError('')
    }

    if (requiresPassword && !isStrongPassword(password)) {
      setPasswordError(t.setup.passwordError)
      valid = false
    } else {
      setPasswordError('')
    }

    if (!name.trim()) {
      setNameError(t.setup.nameError)
      valid = false
    } else {
      setNameError('')
    }

    if (!company.trim()) {
      setCompanyError(t.setup.companyError)
      valid = false
    } else {
      setCompanyError('')
    }

    return valid
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    setIsLoading(true)
    try {
      const response = await authApi.setup({
        token,
        email,
        password: requiresPassword ? password : undefined,
        name,
        company,
        newsletter,
        locale: language === 'zh' ? 'zh-CN' : 'en-US',
      })
      setTokenAndUser(response.token, response.user)
      navigate('/brand/overview')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      showToast(msg || t.errors.serverError, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  if (tokenLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-themed-page">
        <svg className="animate-spin w-7 h-7 text-themed-accent" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex">
      {/* Left decorative panel */}
      <div
        className="hidden lg:flex lg:w-2/5 xl:w-[45%] flex-col relative overflow-hidden"
        style={{ background: 'var(--color-auth-visual-bg)' }}
        aria-hidden="true"
      >
        <div className="flex-1 w-full">
          <ParticleArt />
        </div>
        <div className="absolute bottom-8 left-8 right-8">
          <p className="text-xs text-themed-muted" style={{ lineHeight: 1.6 }}>
            {language === 'zh'
              ? '完成设置后进入 GenPano 工作台'
              : 'Continue to your GenPano workspace after setup'}
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex flex-col bg-white">
        {/* Language switcher top right */}
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        {/* Scrollable form content — starts from top */}
        <div className="overflow-y-auto px-8 pt-12 pb-12">
          <div className="max-w-md mx-auto">
            {/* Title */}
            <div className="mb-8">
              <h1 className="text-[32px] font-brand font-semibold text-themed-primary">
                {t.setup.title}
              </h1>
            </div>

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              {/* Email field */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t.setup.emailLabel}
                  <span className="text-red-500 ml-0.5">★</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    <MailIcon />
                  </span>
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    readOnly
                    placeholder="email@company.com"
                    aria-invalid={!!emailError}
                    className={`w-full pl-10 pr-3.5 py-2.5 text-sm rounded-lg border transition-colors outline-none
                      ${emailError
                        ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                        : 'border-gray-200 bg-gray-50'
                      } placeholder:text-gray-400 text-gray-700`}
                  />
                </div>
                {emailError && (
                  <p className="mt-1 text-xs text-red-500" role="alert">{emailError}</p>
                )}
              </div>

              {requiresPassword && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    {t.setup.passwordLabel}
                    <span className="text-red-500 ml-0.5">★</span>
                    <button
                      type="button"
                      title={t.setup.passwordInfo}
                      className="ml-1.5 text-gray-400 hover:text-gray-600 transition-colors inline-flex items-center"
                    >
                      <InfoIcon />
                    </button>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                      <LockIcon />
                    </span>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={password}
                      onChange={e => { setPassword(e.target.value); setPasswordError('') }}
                      placeholder={t.setup.passwordLabel}
                      aria-invalid={!!passwordError}
                      className={`w-full pl-10 pr-10 py-2.5 text-sm rounded-lg border transition-colors outline-none
                        ${passwordError
                          ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                          : 'border-gray-200 focus:border-accent-500 focus:ring-2 focus:ring-accent-500/10'
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
                </div>
              )}

              {/* Full name field */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t.setup.nameLabel}
                  <span className="text-red-500 ml-0.5">★</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    <PersonIcon />
                  </span>
                  <input
                    type="text"
                    autoComplete="name"
                    value={name}
                    onChange={e => { setName(e.target.value); setNameError('') }}
                    placeholder={t.setup.namePlaceholder}
                    aria-invalid={!!nameError}
                    className={`w-full pl-10 pr-3.5 py-2.5 text-sm rounded-lg border transition-colors outline-none
                      ${nameError
                        ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                        : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                      } placeholder:text-gray-400 text-gray-900`}
                  />
                </div>
                {nameError && (
                  <p className="mt-1 text-xs text-red-500" role="alert">{nameError}</p>
                )}
              </div>

              {/* Company name field */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  {t.setup.companyLabel}
                  <span className="text-red-500 ml-0.5">★</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    <BuildingIcon />
                  </span>
                  <input
                    type="text"
                    autoComplete="organization"
                    value={company}
                    onChange={e => { setCompany(e.target.value); setCompanyError('') }}
                    placeholder={t.setup.companyPlaceholder}
                    aria-invalid={!!companyError}
                    className={`w-full pl-10 pr-3.5 py-2.5 text-sm rounded-lg border transition-colors outline-none
                      ${companyError
                        ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                        : 'border-gray-200 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/10'
                      } placeholder:text-gray-400 text-gray-900`}
                  />
                </div>
                {companyError && (
                  <p className="mt-1 text-xs text-red-500" role="alert">{companyError}</p>
                )}
              </div>

              {/* Newsletter checkbox */}
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={newsletter}
                  onChange={e => setNewsletter(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-primary-500 focus:ring-primary-500 cursor-pointer"
                />
                <span className="text-sm text-gray-600">{t.setup.newsletter}</span>
              </label>

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
                ) : t.setup.submitButton}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

function MailIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  )
}

function PersonIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  )
}

function BuildingIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
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
