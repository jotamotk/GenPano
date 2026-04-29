import React from 'react'
import LanguageSwitcher from './LanguageSwitcher'

interface AuthLayoutProps {
  children: React.ReactNode
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex">
      {/* Left decorative panel — 50% */}
      <div
        className="hidden md:flex md:w-[40%] lg:w-1/2 flex-col relative overflow-hidden bg-brand-beige"
        aria-hidden="true"
      >
        {/* Logo top-left */}
        <div className="absolute top-8 left-8 z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-gradient-accent">
              <span className="text-white text-xs font-bold">GP</span>
            </div>
            <span className="text-sm font-semibold text-gray-800">
              GenPano
            </span>
          </div>
        </div>

        <div className="flex-1 w-full flex items-center justify-center px-10">
          <div className="relative w-full max-w-[360px] aspect-square">
            <div className="absolute inset-8 rounded-full border border-accent-500/20" />
            <div className="absolute inset-20 rounded-full border border-accent-500/30" />
            <div className="absolute left-8 top-16 w-24 h-16 rounded-card bg-white border border-card shadow-card" />
            <div className="absolute right-10 top-28 w-28 h-20 rounded-card bg-white border border-card shadow-card" />
            <div className="absolute left-20 bottom-14 w-32 h-20 rounded-card bg-white border border-card shadow-card" />
            <div className="absolute left-1/2 top-1/2 w-20 h-20 -translate-x-1/2 -translate-y-1/2 rounded-card bg-gradient-accent shadow-card-hover flex items-center justify-center text-white font-semibold">
              AI
            </div>
          </div>
        </div>

        {/* Bottom tagline */}
        <div className="absolute bottom-8 left-8 right-8">
          <p className="text-xs text-gray-500" style={{ lineHeight: 1.6 }}>
            Monitor your brand's presence<br />
            across AI-generated content
          </p>
        </div>
      </div>

      {/* Right form panel — 50% */}
      <div className="flex-1 flex flex-col bg-white">
        {/* Language switcher — top right */}
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        {/* Form content — vertically centered */}
        <div className="flex-1 flex items-center justify-center px-6 sm:px-8 py-12">
          <div className="w-full max-w-[400px] animate-fade-in">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
