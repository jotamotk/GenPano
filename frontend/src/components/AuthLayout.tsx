import React from 'react'
import ParticleArt from './ParticleArt'
import LanguageSwitcher from './LanguageSwitcher'

interface AuthLayoutProps {
  children: React.ReactNode
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex">
      {/* Left decorative panel */}
      <div
        className="hidden lg:flex lg:w-2/5 xl:w-[45%] flex-col relative overflow-hidden"
        style={{ backgroundColor: '#F5EDE5' }}
        aria-hidden="true"
      >
        {/* Logo top-left */}
        <div className="absolute top-8 left-8 z-10">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #C9A96E, #8B6914)' }}>
              <span className="text-white text-xs font-bold">GP</span>
            </div>
            <span className="text-sm font-semibold" style={{ color: '#5C4200' }}>
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
          <p className="text-xs" style={{ color: '#A0845C', lineHeight: 1.6 }}>
            Monitor your brand's presence<br />
            across AI-generated content
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex flex-col bg-white">
        {/* Language switcher — top right */}
        <div className="flex justify-end px-8 pt-6">
          <LanguageSwitcher />
        </div>

        {/* Form content — vertically centered */}
        <div className="flex-1 flex items-center justify-center px-8 py-12">
          <div className="w-full max-w-sm">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
