import { useState, useCallback } from 'react'
import { useLanguage } from '../context/LanguageContext'

// Blocked personal email domains
const PERSONAL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com',
  'hotmail.com', 'hotmail.cn', 'hotmail.co.uk',
  'outlook.com', 'outlook.cn',
  'yahoo.com', 'yahoo.cn', 'yahoo.com.cn',
  'qq.com', 'foxmail.com',
  '163.com', '126.com', '139.com',
  'sina.com', 'sina.cn',
  'sohu.com',
  'icloud.com', 'me.com', 'mac.com',
  'live.com', 'msn.com',
  'protonmail.com', 'proton.me',
  'yandex.com', 'yandex.ru',
  'mail.com', 'email.com',
  '21cn.com',
  'aliyun.com',
  'tom.com',
])

const EMAIL_REGEX = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/

export function validateWorkEmail(email: string): 'valid' | 'invalid_format' | 'personal_domain' | 'empty' {
  if (!email.trim()) return 'empty'
  if (!EMAIL_REGEX.test(email)) return 'invalid_format'
  const domain = email.split('@')[1]?.toLowerCase()
  if (!domain) return 'invalid_format'
  if (PERSONAL_DOMAINS.has(domain)) return 'personal_domain'
  return 'valid'
}

export function useEmailValidation() {
  const { t } = useLanguage()
  const [error, setError] = useState<string>('')
  const [touched, setTouched] = useState(false)

  const validate = useCallback(
    (email: string): boolean => {
      const result = validateWorkEmail(email)
      if (result === 'empty') {
        setError(t.validation.emailRequired)
        return false
      }
      if (result === 'invalid_format') {
        setError(t.validation.emailInvalid)
        return false
      }
      if (result === 'personal_domain') {
        setError(t.validation.emailPersonal)
        return false
      }
      setError('')
      return true
    },
    [t]
  )

  const handleBlur = useCallback(
    (email: string) => {
      setTouched(true)
      validate(email)
    },
    [validate]
  )

  const handleChange = useCallback(
    (email: string) => {
      if (touched) validate(email)
    },
    [touched, validate]
  )

  const reset = useCallback(() => {
    setError('')
    setTouched(false)
  }, [])

  return { error, validate, handleBlur, handleChange, reset, touched }
}
