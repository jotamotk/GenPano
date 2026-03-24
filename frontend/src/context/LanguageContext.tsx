import React, { createContext, useContext, useState, useCallback } from 'react'
import { zh, en } from '../i18n'
import type { Translations } from '../i18n'

type Language = 'zh' | 'en'

interface LanguageContextValue {
  language: Language
  t: Translations
  toggleLanguage: () => void
  setLanguage: (lang: Language) => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

const translations: Record<Language, Translations> = { zh, en }

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLangState] = useState<Language>(() => {
    const stored = localStorage.getItem('genpano_lang')
    return (stored === 'en' || stored === 'zh') ? stored : 'zh'
  })

  const setLanguage = useCallback((lang: Language) => {
    setLangState(lang)
    localStorage.setItem('genpano_lang', lang)
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [])

  const toggleLanguage = useCallback(() => {
    setLanguage(language === 'zh' ? 'en' : 'zh')
  }, [language, setLanguage])

  return (
    <LanguageContext.Provider
      value={{ language, t: translations[language], toggleLanguage, setLanguage }}
    >
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
