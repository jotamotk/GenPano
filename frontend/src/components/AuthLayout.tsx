import React from 'react'
import AuthVisualPanel from './AuthVisualPanel'
import LanguageSwitcher from './LanguageSwitcher'

interface AuthLayoutProps {
  children: React.ReactNode
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex">
      <AuthVisualPanel />

      <div className="w-full lg:w-[520px] lg:shrink-0 flex flex-col bg-white">
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        <div className="flex-1 flex items-center justify-center px-6 sm:px-8 py-12">
          <div className="w-full max-w-[400px] animate-fade-in">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
