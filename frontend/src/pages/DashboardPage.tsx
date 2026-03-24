import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { authApi } from '../api/auth'

export default function DashboardPage() {
  const { user, logout, setTokenAndUser } = useAuth()
  const { language } = useLanguage()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Handle Google OAuth redirect: /dashboard?token=xxx
  useEffect(() => {
    const oauthToken = searchParams.get('token')
    if (oauthToken) {
      // Remove token from URL immediately
      setSearchParams({}, { replace: true })
      // Fetch user info and store the token
      authApi.getMe(oauthToken)
        .then(u => {
          setTokenAndUser(oauthToken, { id: u.id, email: u.email, name: u.name, company: u.company })
        })
        .catch(() => {
          navigate('/login?error=oauth_failed', { replace: true })
        })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #C9A96E, #8B6914)' }}>
              <span className="text-white text-xs font-bold">GP</span>
            </div>
            <span className="text-sm font-semibold text-gray-800">GenPano</span>
          </div>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center">
                <span className="text-xs font-semibold text-indigo-600">
                  {user?.email?.[0]?.toUpperCase() ?? 'U'}
                </span>
              </div>
              <span className="text-sm text-gray-600">{user?.email}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              {language === 'zh' ? '退出登录' : 'Logout'}
            </button>
          </div>
        </div>
      </header>

      {/* Main content — placeholder dashboard */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-gray-900">
            {language === 'zh' ? '欢迎使用 GenPano' : 'Welcome to GenPano'}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {language === 'zh'
              ? 'GEO 监测仪表盘 — 追踪您的品牌在 AI 生成内容中的曝光情况'
              : 'GEO Monitoring Dashboard — Track your brand\'s presence in AI-generated content'}
          </p>
        </div>

        {/* Stats cards placeholder */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {[
            { label: language === 'zh' ? 'AI 引用次数' : 'AI Citations', value: '—', sub: language === 'zh' ? '本月' : 'This month' },
            { label: language === 'zh' ? '监测平台' : 'Monitored Platforms', value: '4', sub: 'ChatGPT · Gemini · Perplexity · Claude' },
            { label: language === 'zh' ? '情感分析' : 'Sentiment Score', value: '—', sub: language === 'zh' ? '待配置' : 'Configure tracking' },
          ].map((card, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 p-6">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">{card.label}</p>
              <p className="mt-2 text-3xl font-semibold text-gray-900">{card.value}</p>
              <p className="mt-1 text-xs text-gray-400">{card.sub}</p>
            </div>
          ))}
        </div>

        {/* Getting started */}
        <div className="bg-white rounded-xl border border-gray-100 p-8 text-center">
          <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #EEE5D8, #F5EDE5)' }}>
            <svg className="w-8 h-8" style={{ color: '#8B6914' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            {language === 'zh' ? '开始设置您的监测项目' : 'Set up your first monitoring project'}
          </h2>
          <p className="text-sm text-gray-500 mb-6 max-w-md mx-auto">
            {language === 'zh'
              ? '添加您的品牌关键词，GenPano 将自动追踪 AI 生成引擎中的相关引用'
              : 'Add your brand keywords and GenPano will automatically track citations across AI engines'}
          </p>
          <button className="px-6 py-2.5 text-sm font-semibold text-white rounded-lg bg-indigo-500 hover:bg-indigo-600 transition-colors">
            {language === 'zh' ? '创建监测项目' : 'Create Monitoring Project'}
          </button>
        </div>
      </main>
    </div>
  )
}
