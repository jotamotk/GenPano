import { useLanguage } from '../context/LanguageContext'

export default function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="flex items-center gap-1 text-sm font-medium">
      <button
        onClick={() => setLanguage('en')}
        className={`px-2 py-1 rounded transition-colors ${
          language === 'en'
            ? 'text-indigo-600 font-semibold'
            : 'text-gray-400 hover:text-gray-600'
        }`}
        aria-label="Switch to English"
      >
        EN
      </button>
      <span className="text-gray-300 select-none">|</span>
      <button
        onClick={() => setLanguage('zh')}
        className={`px-2 py-1 rounded transition-colors ${
          language === 'zh'
            ? 'text-indigo-600 font-semibold'
            : 'text-gray-400 hover:text-gray-600'
        }`}
        aria-label="切换到中文"
      >
        中文
      </button>
    </div>
  )
}
