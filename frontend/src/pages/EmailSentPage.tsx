import { useSearchParams, useNavigate } from 'react-router-dom'
import { useLanguage } from '../context/LanguageContext'
import { authApi } from '../api/auth'
import { showToast } from '../components/Toast'
import ParticleArt from '../components/ParticleArt'
import LanguageSwitcher from '../components/LanguageSwitcher'

export default function EmailSentPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const email = searchParams.get('email') || ''
  const type = searchParams.get('type') as 'verify' | 'reset' | null

  const isReset = type === 'reset'

  const title = isReset ? t.emailSent.resetTitle : t.emailSent.verifyTitle
  const subtitle = isReset ? t.emailSent.resetSubtitle : t.emailSent.verifySubtitle
  const step1 = isReset ? t.emailSent.step1Reset : t.emailSent.step1Verify
  const step2 = isReset ? t.emailSent.step2Reset : t.emailSent.step2Verify
  const nextStepsLabel = isReset ? t.emailSent.nextStepsReset : t.emailSent.nextSteps

  const handleResend = async () => {
    if (!email) return
    try {
      if (isReset) {
        await authApi.forgotPassword(email)
      } else {
        await authApi.resendVerification(email)
      }
      showToast(t.emailSent.resendButton, 'success')
    } catch {
      showToast(t.errors.serverError, 'error')
    }
  }

  const handleEditEmail = () => {
    if (isReset) {
      navigate('/forgot-password')
    } else {
      navigate('/register')
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left decorative panel */}
      <div
        className="hidden lg:flex lg:w-2/5 xl:w-[45%] flex-col relative overflow-hidden"
        style={{ backgroundColor: '#F5EDE5' }}
        aria-hidden="true"
      >
        <div className="flex-1 w-full">
          <ParticleArt />
        </div>
        <div className="absolute bottom-8 left-8 right-8">
          <p className="text-xs" style={{ color: '#A0845C', lineHeight: 1.6 }}>
            Monitor your brand's presence<br />
            across AI-generated content
          </p>
        </div>
      </div>

      {/* Right panel — light gray background */}
      <div className="flex-1 flex flex-col" style={{ backgroundColor: '#F9FAFB' }}>
        {/* Language switcher top right */}
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        {/* Centered card */}
        <div className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="bg-white border border-gray-200 rounded-2xl px-10 py-10 max-w-[420px] w-full mx-auto">

            {/* Green checkmark icon */}
            <div className="flex justify-center mb-6">
              <GreenCheckIcon />
            </div>

            {/* Title */}
            <h1 className="text-xl font-semibold text-gray-900 text-center mb-2">
              {title}
            </h1>

            {/* Subtitle */}
            <p className="text-sm text-gray-500 text-center mb-6 leading-relaxed">
              {subtitle}
            </p>

            {/* Email display box */}
            {email && (
              <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 mb-6">
                <MailIcon />
                <span className="flex-1 text-sm text-gray-700 truncate">{email}</span>
                <button
                  type="button"
                  onClick={handleEditEmail}
                  className="text-gray-400 hover:text-indigo-600 transition-colors flex-shrink-0"
                  title="修改邮箱"
                >
                  <PencilIcon />
                </button>
              </div>
            )}

            {/* Next steps */}
            <p className="text-sm font-medium text-gray-700 mb-3">{nextStepsLabel}</p>
            <div className="space-y-3 mb-6">
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  1
                </span>
                <span className="text-sm text-gray-600">{step1}</span>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  2
                </span>
                <span className="text-sm text-gray-600">{step2}</span>
              </div>
            </div>

            {/* Resend button */}
            <button
              type="button"
              onClick={handleResend}
              className="w-full py-2.5 px-4 text-sm font-semibold text-white rounded-lg transition-colors
                bg-indigo-500 hover:bg-indigo-600 focus:ring-2 focus:ring-indigo-300 focus:outline-none"
            >
              {t.emailSent.resendButton}
            </button>

            {/* No email hint */}
            <p className="text-xs text-gray-400 text-center mt-3">
              {t.emailSent.noEmailHint}
            </p>

            {/* View email link */}
            <div className="text-center mt-3">
              <a
                href={email ? `mailto:${email}` : '#'}
                className="text-sm text-indigo-600 hover:text-indigo-700 transition-colors"
              >
                {t.emailSent.viewEmail} 👉
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function GreenCheckIcon() {
  return (
    <svg className="w-16 h-16" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" stroke="#22c55e" strokeWidth="2.5" fill="none" />
      <path
        d="M20 32l8 8 16-16"
        stroke="#22c55e"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MailIcon() {
  return (
    <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
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
