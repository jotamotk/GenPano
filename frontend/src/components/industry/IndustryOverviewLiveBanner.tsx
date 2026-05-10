/**
 * IndustryOverviewLiveBanner — same non-invasive overlay pattern as
 * BrandOverviewLiveBanner but for /industry/overview.
 *
 * Renders a 4-card live KPI strip + Top 3 brands when the
 * industryId is numeric (real backend industry), null for mock-only
 * users (industryId='beauty' etc.).
 */

import { useIndustryOverview } from '../../hooks/useIndustries'
import { MetricLabel } from '../ui'

export default function IndustryOverviewLiveBanner({
  industryId,
}: {
  industryId: number | null | undefined
}) {
  const { data: overview, isLoading } = useIndustryOverview(industryId)

  if (
    typeof industryId !== 'number' ||
    industryId <= 0 ||
    isLoading ||
    !overview
  ) {
    return null
  }

  return (
    <div
      className="rounded-card border p-4 mb-4"
      style={{
        background:
          'linear-gradient(135deg, rgba(99, 91, 255, 0.06), rgba(139, 92, 246, 0.04))',
        borderColor: 'var(--color-accent, #635bff)',
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="px-2 py-0.5 rounded-pill text-[10px] font-bold tabular-nums"
            style={{ background: 'var(--color-accent, #635bff)', color: 'white' }}
          >
            LIVE
          </span>
          <span className="text-sm font-semibold text-themed-primary">
            {overview.industry_name || `行业 ${overview.industry_id}`}
          </span>
          <span className="text-[11px] text-themed-faint">
            {overview.period.from} → {overview.period.to}
          </span>
        </div>
        <span className="text-[10px] uppercase font-bold tracking-wider text-themed-muted">
          /v1/industries/{overview.industry_id}/overview
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        {overview.kpi_cards.map((card, i) => (
          <div
            key={i}
            className="rounded-card p-3"
            style={{ background: 'var(--color-bg-card, #fff)' }}
          >
            <div className="text-[11px] uppercase tracking-wider text-themed-muted mb-1">
              <MetricLabel helpText={getIndustryKpiHelpText(card.label_zh)}>
                {card.label_zh}
              </MetricLabel>
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-xl font-bold tabular-nums text-themed-primary">
                {card.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
              {card.unit && (
                <span className="text-xs text-themed-muted">{card.unit}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {overview.top_brands.length > 0 && (
        <div className="border-t border-themed pt-3">
          <div className="text-[10px] font-semibold text-themed-muted uppercase tracking-wider mb-2">
            <MetricLabel helpText="按最近 30 天平均 GEO 分排序的行业品牌榜单。">
              Top 10 品牌（30d 平均 GEO 分）
            </MetricLabel>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {overview.top_brands.slice(0, 10).map((b) => (
              <div
                key={b.brand_id}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-themed-primary">
                  #{b.rank} {b.brand_name ?? `brand-${b.brand_id}`}
                </span>
                <span
                  className="font-bold tabular-nums"
                  style={{ color: '#635bff' }}
                >
                  {b.avg_geo_score == null ? '—' : b.avg_geo_score.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {overview.state === 'empty' && (
        <p className="text-[11px] text-themed-faint mt-2">
          暂无 30 天聚合数据 — 数据采集 pipeline 跑过后会自动填充。
        </p>
      )}
    </div>
  )
}

function getIndustryKpiHelpText(label: string): string {
  if (label.includes('品牌')) {
    return '当前行业样本中覆盖到的品牌数量。'
  }
  if (label.includes('PANO') || label.includes('GEO')) {
    return '行业品牌在 AI 回答中的综合可见度得分。'
  }
  if (label.includes('提及')) {
    return '基于品类通用问题计算，排除直接询问品牌的问题（non-brand 口径）。'
  }
  if (label.includes('SoV')) {
    return '已提到任一品牌的回答中，各品牌占有的声量份额。'
  }
  return '当前行业 30 天窗口内的实时指标。'
}
