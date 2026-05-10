import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLocale } from '../contexts/LocaleContext'
import { useAuth } from '../contexts/AuthContext'
import { useCreateProject } from '../hooks/useProjects'
import { useBrandSearch } from '../hooks/useBrandSearch'
import type { BrandSearchHit } from '../api/brands'

/* ══════════════════════════════════════════════════════════════
   Onboarding Page — 软门槛品牌选择
   First-time users land here right after login; choosing a brand
   creates a Project (primary_brand_id) and unblocks the dashboard.
   Skipping is allowed — the user can revisit /onboarding later
   from the dashboard "未设置品牌" banner.
   ══════════════════════════════════════════════════════════════ */

export default function OnboardingPage() {
  const navigate = useNavigate()
  const { t } = useLocale()
  const { refreshUser } = useAuth()
  const [query, setQuery] = useState('')
  const [submitError, setSubmitError] = useState<string | null>(null)
  const { data: hits = [], isFetching, isError } = useBrandSearch(query)
  const createProject = useCreateProject()

  const handleSelect = async (hit: BrandSearchHit) => {
    setSubmitError(null)
    if (
      hit.isAlreadyMonitoring &&
      typeof window !== 'undefined' &&
      // eslint-disable-next-line no-alert
      !window.confirm(t('onboarding.brand.duplicate_confirm', { brand: hit.brandName }))
    ) {
      return
    }
    try {
      await createProject.mutateAsync({
        name: `${hit.brandName} 监测`,
        primary_brand_id: hit.brandId,
      })
      // Belt-and-braces: arm the skip flag so the dashboard route is
      // reachable even if the follow-up /me call fails silently and
      // `needsOnboarding` stays stale in local state.
      try {
        window.sessionStorage?.setItem('genpano_onboarding_skipped', '1')
      } catch {
        /* ignore — non-critical */
      }
      await refreshUser()
      navigate('/brand/overview')
    } catch {
      setSubmitError(t('onboarding.brand.create_failed'))
    }
  }

  const handleSkip = () => {
    // Soft-skip: bypass RequireOnboarded for this tab so the user can poke
    // around the dashboard. The dashboard banner reminds them to come back.
    try {
      window.sessionStorage?.setItem('genpano_onboarding_skipped', '1')
    } catch {
      /* ignore — non-critical */
    }
    navigate('/brand/overview')
  }

  const showEmptyState =
    query.trim().length >= 1 && !isFetching && !isError && hits.length === 0
  const isCreating = createProject.isPending

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--color-bg-page, #f8fafc)' }}
    >
      <div className="w-full max-w-xl mx-auto px-6 py-12">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-6">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #635bff, #8b5cf6)' }}
            >
              <span className="text-white font-bold text-lg">G</span>
            </div>
            <span className="text-xl font-bold text-themed-primary tracking-tight">GENPANO</span>
          </div>
          <h1 className="text-2xl font-semibold text-themed-primary">
            {t('onboarding.brand.title')}
          </h1>
          <p className="text-themed-secondary text-sm mt-2 max-w-md mx-auto">
            {t('onboarding.brand.subtitle')}
          </p>
        </div>

        <div className="rounded-xl border bg-themed-card p-5" style={{ borderColor: 'var(--color-border, #e2e8f0)' }}>
          <label className="block">
            <span className="sr-only">{t('onboarding.brand.search.placeholder')}</span>
            <input
              type="text"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('onboarding.brand.search.placeholder')}
              className="w-full px-4 py-3 rounded-lg border text-base outline-none focus:ring-2 focus:ring-[#635bff]/40 focus:border-[#635bff]"
              style={{ borderColor: 'var(--color-border, #e2e8f0)', background: 'var(--color-bg-card, #fff)' }}
              data-testid="brand-search-input"
            />
          </label>

          {/* Result list */}
          <ul className="mt-3 divide-y" style={{ borderColor: 'var(--color-border, #e2e8f0)' }} data-testid="brand-search-results">
            {hits.map((hit) => (
              <li key={hit.brandId}>
                <button
                  type="button"
                  disabled={isCreating}
                  onClick={() => handleSelect(hit)}
                  className="w-full flex items-center justify-between py-3 px-2 hover:bg-themed-hover rounded-md text-left disabled:opacity-50"
                  data-testid={`brand-search-hit-${hit.brandId}`}
                >
                  <div>
                    <div className="text-sm font-medium text-themed-primary">{hit.brandName}</div>
                    {hit.industry && (
                      <div className="text-xs text-themed-faint mt-0.5">{hit.industry}</div>
                    )}
                  </div>
                  {hit.isAlreadyMonitoring && (
                    <span
                      className="text-[11px] px-2 py-0.5 rounded-full"
                      style={{ background: 'rgba(99, 91, 255, 0.1)', color: '#635bff' }}
                      data-testid="already-monitoring-badge"
                    >
                      ✓ {t('onboarding.brand.already_monitoring')}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>

          {isFetching && query.trim().length >= 1 && (
            <p className="text-xs text-themed-faint mt-3 px-2" data-testid="brand-search-loading">
              {t('onboarding.brand.loading')}
            </p>
          )}
          {showEmptyState && (
            <div className="mt-3 px-2 py-4 text-center" data-testid="brand-search-empty">
              <p className="text-sm text-themed-secondary">
                {t('onboarding.brand.not_found')}
              </p>
            </div>
          )}
          {isError && (
            <p className="text-xs text-red-500 mt-3 px-2" data-testid="brand-search-error">
              {t('onboarding.brand.search_failed')}
            </p>
          )}
          {submitError && (
            <p className="text-xs text-red-500 mt-3 px-2" data-testid="brand-create-error">
              {submitError}
            </p>
          )}
        </div>

        {/* CTAs */}
        <div className="flex flex-col items-center gap-2 mt-8">
          <button
            type="button"
            onClick={handleSkip}
            disabled={isCreating}
            className="text-sm font-medium transition-colors disabled:opacity-50"
            style={{ color: 'var(--color-text-muted, #64748b)' }}
            data-testid="onboarding-skip"
          >
            {t('onboarding.skip.cta')} →
          </button>
          <p className="text-[11px] text-themed-faint">{t('onboarding.skip.hint')}</p>
        </div>
      </div>
    </div>
  )
}
