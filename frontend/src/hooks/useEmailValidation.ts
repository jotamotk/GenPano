import { useState, useCallback } from 'react'
import { useLanguage } from '../contexts/LanguageContext'

const EMAIL_REGEX = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/

export function validateEmailFormat(email: string): 'valid' | 'invalid_format' | 'empty' {
  if (!email.trim()) return 'empty'
  if (!EMAIL_REGEX.test(email)) return 'invalid_format'
  return 'valid'
}

export function useEmailValidation() {
  const { t } = useLanguage()
  const [error, setError] = useState<string>('')
  const [touched, setTouched] = useState(false)

  const validate = useCallback(
    (email: string): boolean => {
      const result = validateEmailFormat(email)
      if (result === 'empty') {
        setError(t.validation.emailRequired)
        return false
      }
      if (result === 'invalid_format') {
        setError(t.validation.emailInvalid)
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
