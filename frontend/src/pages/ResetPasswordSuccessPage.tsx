import { useNavigate } from 'react-router-dom'
import { useLanguage } from '../context/LanguageContext'
import AuthVisualPanel from '../components/AuthVisualPanel'
import LanguageSwitcher from '../components/LanguageSwitcher'

export default function ResetPasswordSuccessPage() {
  const { t } = useLanguage()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex">
      <AuthVisualPanel />

      {/* Right panel — light gray background */}
      <div className="w-full lg:w-[520px] lg:shrink-0 flex flex-col bg-themed-page">
        {/* Language switcher top right */}
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        {/* Centered card */}
        <div className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="bg-white border border-gray-200 rounded-2xl px-10 py-10 max-w-[420px] w-full mx-auto text-center animate-fade-in">

            {/* Green checkmark icon */}
            <div className="flex justify-center mb-6 animate-scale-in">
              <GreenCheckIcon />
            </div>

            {/* Title */}
            <h1 className="text-xl font-semibold text-gray-900 mb-3">
              {t.resetSuccess.title}
            </h1>

            {/* Description */}
            <p className="text-sm text-gray-500 mb-8 leading-relaxed">
              {t.resetSuccess.description}
            </p>

            {/* Back button */}
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="w-full h-12 px-4 text-base font-semibold text-white rounded-[10px] transition-all duration-200 bg-primary-500 hover:bg-primary-600 hover:-translate-y-[1px] hover:shadow-lg hover:shadow-purple-500/25 active:bg-primary-700 active:translate-y-0 focus:ring-2 focus:ring-primary-100 focus:outline-none"
            >
              {t.resetSuccess.backButton}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function GreenCheckIcon() {
  return (
    <svg className="w-16 h-16" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" stroke="#10B981" strokeWidth="2.5" fill="none" />
      <path
        d="M20 32l8 8 16-16"
        stroke="#10B981"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
