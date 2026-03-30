import React from 'react'
import ParticleArt from './ParticleArt'
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
            <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-gradient-to-br from-primary-500 to-primary-700">
              <span className="text-white text-xs font-bold">GP</span>
            </div>
            <span className="text-sm font-semibold text-gray-800">
              GenPano
            </span>
          </div>
        </div>

        {/* 3D particle art — fills the panel */}
        <div className="flex-1 w-full">
          <ParticleArt />
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
