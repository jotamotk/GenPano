import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import { useLocale } from '../contexts/LocaleContext';
import { INDUSTRIES, BRANDS } from '../data/mock';
import { useIndustriesWithTopBrands } from '../hooks/useIndustries';

/* ══════════════════════════════════════════════════════════════
   Onboarding Page — PRD 4.1.1b Single-Path Flow

   设计原则: Data-First — 用户选完行业立刻看到真实数据，
   在数据中自然产生创建 Project 的动机。
   不设分流问卷、不在用户理解价值之前要求决策。

   流程: 注册/登录完成 → 选择行业(唯一必选步骤) → 直接进入行业探索视图

   Data source: GET /v1/industries/ + per-industry /top-brands.
   When backend returns 0 industries (fresh deployment) we fall back
   to the static INDUSTRIES + BRANDS mock so the page is never blank.
   ══════════════════════════════════════════════════════════════ */

// Get top 3 brands by PanoScore for an industry — mock fallback
function getTopBrandsMock(industryId: string | number, count = 3) {
  return (BRANDS as any[])
    .filter(b => b.industryId === industryId)
    .sort((a, b) => (b.panoScore || 0) - (a.panoScore || 0))
    .slice(0, count);
}

// Rank badge colors
const RANK_COLORS = ['#f5a623', '#94a3b8', '#cd7f32']; // gold, silver, bronze

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useLocale();
  const [hoveredIndustry, setHoveredIndustry] = useState<string | number | null>(null);

  // Live backend data (with overlays for icon / nameEn)
  const { data: liveIndustries, isLoading, isError } = useIndustriesWithTopBrands();

  // Fallback: when backend returns nothing (or errors), show the static
  // mock so onboarding is never blank pre-seeded.
  const useLive = !isLoading && !isError && liveIndustries.length > 0;

  /* ── PRD §4.1.2a flow continuation ──
     If the user arrived here from /register?monitor_brand=X&return_to=Y,
     remember to bounce them back to Y once they've picked an industry —
     so the WatchBrand intent is never lost across the auth wizard. */
  const monitorBrand = searchParams.get('monitor_brand') || '';
  const returnTo = searchParams.get('return_to') || '';

  /* ── PRD §4.1.1b: industry selection is SKIPPABLE ──
     Per PRD §4.1.1d, if the user skips here they land on /dashboard in the
     zero-Project state and are guided by <DashboardEmptyState /> (E1). We
     do NOT block them — the whole point of Data-Before-Auth is that the
     product works without up-front decisions. */
  const handleSkip = () => {
    // entry_source=empty_state_dashboard — they will see E1 on /dashboard
    navigate('/dashboard');
  };

  const handleSelectIndustry = (industryKey: string | number) => {
    // PRD: 选完即走 — 点击卡片后零延迟进入行业探索视图
    // industryKey is either the live industry_id (number) or the mock slug.
    localStorage?.setItem?.('genpano_industry', String(industryKey));
    // monitorBrand intent is preserved through the URL so the destination
    // page (Brand Detail) can re-evaluate WatchBrandButton state once the
    // ProjectContext is bootstrapped post-onboarding.
    if (returnTo) {
      const tail = monitorBrand ? `${returnTo.includes('?') ? '&' : '?'}monitor_brand=${monitorBrand}` : '';
      navigate(`${returnTo}${tail}`);
    } else if (monitorBrand) {
      navigate(`/brands/${monitorBrand}?from=industry`);
    } else {
      navigate('/dashboard');
    }
  };

  // Normalise to a single render shape regardless of source.
  const cards = useLive
    ? liveIndustries.map(it => ({
        key: it.industry_id,
        nameZh: it.nameZh,
        nameEn: it.nameEn,
        icon: it.icon,
        brandCount: it.brandCount,
        topBrands: it.topBrands.map(b => ({
          id: String(b.brand_id),
          name: b.brand_name ?? `brand-${b.brand_id}`,
          panoScore: b.avg_geo_score == null ? null : Math.round(b.avg_geo_score),
        })),
      }))
    : INDUSTRIES.map(it => ({
        key: it.id,
        nameZh: it.name,
        nameEn: it.nameEn,
        icon: it.icon,
        brandCount: it.brandCount,
        topBrands: getTopBrandsMock(it.id).map(b => ({
          id: b.id,
          name: b.name,
          panoScore: b.panoScore ?? null,
        })),
      }));

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--color-bg-page, #f8fafc)' }}>
      <div className="w-full max-w-3xl mx-auto px-6 py-12">
        {/* Logo & Welcome */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-6">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #635bff, #8b5cf6)' }}>
              <span className="text-white font-bold text-lg">G</span>
            </div>
            <span className="text-xl font-bold text-themed-primary tracking-tight">GENPANO</span>
          </div>
          <h1 className="text-2xl font-semibold text-themed-primary">选择你感兴趣的行业</h1>
          <p className="text-themed-secondary text-sm mt-2 max-w-md mx-auto">
            平台已为每个行业完成全量数据采集，选择后即刻查看品牌排名、竞争格局和 AI 可见度数据
          </p>
          {isLoading && (
            <p className="text-[11px] text-themed-faint mt-3">加载行业数据…</p>
          )}
        </div>

        {/* Industry Cards with Data Hooks — PRD 4.1.1b */}
        <div className="grid grid-cols-2 gap-5">
          {cards.map(industry => {
            const isHovered = hoveredIndustry === industry.key;

            return (
              <div
                key={industry.key}
                onClick={() => handleSelectIndustry(industry.key)}
                onMouseEnter={() => setHoveredIndustry(industry.key)}
                onMouseLeave={() => setHoveredIndustry(null)}
                className="group relative rounded-xl border cursor-pointer transition-all duration-200 overflow-hidden"
                style={{
                  background: 'var(--color-bg-card, #fff)',
                  borderColor: isHovered ? 'var(--color-accent, #635bff)' : 'var(--color-border, #e2e8f0)',
                  boxShadow: isHovered
                    ? '0 8px 30px rgba(99, 91, 255, 0.12), 0 0 0 1px rgba(99, 91, 255, 0.2)'
                    : '0 1px 3px rgba(0,0,0,0.04)',
                  transform: isHovered ? 'translateY(-2px)' : 'none',
                }}
              >
                <div className="p-6">
                  {/* Industry header */}
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="text-3xl mb-2">{industry.icon}</div>
                      <h3 className="text-lg font-semibold text-themed-primary">{industry.nameZh}</h3>
                      <p className="text-xs text-themed-faint mt-0.5">{industry.nameEn}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-themed-faint">监测中</div>
                      <div className="text-lg font-bold tabular-nums text-themed-primary">{industry.brandCount}</div>
                      <div className="text-[10px] text-themed-faint">个品牌</div>
                    </div>
                  </div>

                  {/* Divider */}
                  <div className="border-t border-themed-subtle my-3" />

                  {/* Top 3 brands — PRD: 今日 AI 热度 Top 3 */}
                  <div className="mb-3">
                    <div className="text-[10px] font-semibold text-themed-muted uppercase tracking-wider mb-2">
                      今日 AI 热度 Top 3
                    </div>
                    <div className="space-y-1.5">
                      {industry.topBrands.map((brand, i) => (
                        <div key={brand.id} className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0"
                              style={{ background: RANK_COLORS[i] || '#94a3b8' }}
                            >
                              {i + 1}
                            </span>
                            <span className="text-sm font-medium text-themed-primary">{brand.name}</span>
                          </div>
                          <span className="text-sm font-bold tabular-nums" style={{ color: '#635bff' }}>
                            {brand.panoScore ?? '—'}
                          </span>
                        </div>
                      ))}
                      {industry.topBrands.length === 0 && (
                        <div className="text-xs text-themed-faint py-2">数据加载中...</div>
                      )}
                    </div>
                  </div>

                  {/* CTA hint */}
                  <div
                    className="flex items-center justify-center gap-1 py-2 rounded-lg text-xs font-medium transition-all"
                    style={{
                      background: isHovered ? 'rgba(99, 91, 255, 0.08)' : 'var(--color-bg-badge, #f1f5f9)',
                      color: isHovered ? '#635bff' : 'var(--color-text-secondary, #64748b)',
                    }}
                  >
                    进入查看
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M5 12h14M12 5l7 7-7 7"/>
                    </svg>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Skip CTA — PRD §4.1.1b 2026-04-17: industry selection is optional */}
        <div className="flex flex-col items-center gap-2 mt-8">
          <button
            type="button"
            onClick={handleSkip}
            className="text-sm font-medium transition-colors"
            style={{ color: 'var(--color-text-muted, #64748b)' }}
          >
            {t('onboarding.skip.cta')} →
          </button>
          <p className="text-[11px] text-themed-faint">
            {t('onboarding.skip.hint')}
          </p>
        </div>

        {/* Footer note */}
        <p className="text-center text-[11px] text-themed-faint mt-4">
          所有行业数据每日自动更新 · 选择后可随时在设置中切换行业
        </p>
      </div>
    </div>
  );
}
