/**
 * IndustrySubpageLiveBanner — generic LIVE strip for industry sub-pages.
 *
 * Variants:
 *   ranking → top brand + total count + period
 *   topics  → top topic + count + total mentions
 *   kg      → node count + edge count + brand-relation count
 *
 * Renders null when industryId is null or string-shaped (mock mode).
 */

import {
  useIndustryRanking,
  useIndustryTopics,
  useIndustryKg,
} from '../../hooks/useIndustries'
import { MetricLabel } from '../ui'

type Variant = 'ranking' | 'topics' | 'kg'

interface Card {
  label: string
  value: string | number
  unit?: string
  helpText?: string
}

export default function IndustrySubpageLiveBanner({
  variant,
  industryId,
}: {
  variant: Variant
  industryId: number | null | undefined
}) {
  const ranking = useIndustryRanking(variant === 'ranking' ? industryId : null)
  const topics = useIndustryTopics(variant === 'topics' ? industryId : null)
  const kg = useIndustryKg(variant === 'kg' ? industryId : null)

  if (typeof industryId !== 'number' || industryId <= 0) return null

  let title = ''
  let endpointLabel = ''
  let cards: Card[] = []
  let isLoading = false
  let isEmpty = false

  if (variant === 'ranking') {
    isLoading = ranking.isLoading
    if (!ranking.data) return null
    const r = ranking.data
    isEmpty = r.state === 'empty'
    title = `行业排行榜 — ${r.total} 个品牌`
    endpointLabel = `/v1/industries/${r.industry_id}/ranking`
    const top = r.items[0]
    const median = r.items[Math.floor(r.items.length / 2)]
    cards = [
      { label: '品牌总数', helpText: '当前行业样本中覆盖到的品牌数量。', value: r.total },
      {
        label: 'Top 1',
        value: top ? top.brand_name ?? `brand-${top.brand_id}` : '—',
      },
      {
        label: 'Top GEO',
        helpText: '行业榜单第一名品牌的综合 AI 可见度得分。',
        value: top?.avg_geo_score == null ? '—' : top.avg_geo_score.toFixed(1),
      },
      {
        label: '中位 GEO',
        helpText: '行业样本中处于中位位置品牌的综合 AI 可见度得分。',
        value:
          median?.avg_geo_score == null ? '—' : median.avg_geo_score.toFixed(1),
      },
    ]
  } else if (variant === 'topics') {
    isLoading = topics.isLoading
    if (!topics.data) return null
    const t = topics.data
    isEmpty = t.state === 'empty'
    title = `行业话题热度 — ${t.total} 个话题`
    endpointLabel = `/v1/industries/${t.industry_id}/topics`
    const top = t.items[0]
    const totalMentions = t.items.reduce((s, it) => s + (it.mention_count || 0), 0)
    cards = [
      { label: '话题总数', helpText: '当前行业话题集合中的话题数量。', value: t.total },
      { label: '总提及数', helpText: '当前行业话题集合内的总提及次数。', value: totalMentions },
      { label: 'Top 1', value: top ? top.topic_name : '—' },
      {
        label: 'Top 提及',
        helpText: '提及次数最高话题在当前窗口内的提及次数。',
        value: top ? top.mention_count : '—',
      },
    ]
  } else if (variant === 'kg') {
    isLoading = kg.isLoading
    if (!kg.data) return null
    const k = kg.data
    isEmpty = k.state === 'empty'
    const brandNodes = k.nodes.filter((n) => n.type === 'brand').length
    const productNodes = k.nodes.filter((n) => n.type === 'product').length
    const competeEdges = k.edges.filter((e) => e.type === 'COMPETES_WITH').length
    title = `知识图谱 — 行业 ${k.industry_id}`
    endpointLabel = `/v1/industries/${k.industry_id}/kg`
    cards = [
      { label: '节点数', helpText: '当前行业知识图谱中的节点总数。', value: k.nodes.length },
      { label: '边数', helpText: '当前行业知识图谱中的关系边总数。', value: k.edges.length },
      { label: '品牌节点', helpText: '知识图谱中类型为品牌的节点数量。', value: brandNodes },
      {
        label: productNodes > 0 ? '产品节点' : 'COMPETES_WITH',
        helpText: productNodes > 0 ? '知识图谱中类型为产品的节点数量。' : '品牌之间竞争关系的边数量。',
        value: productNodes > 0 ? productNodes : competeEdges,
      },
    ]
  }

  if (isLoading) return null

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
          <span className="text-sm font-semibold text-themed-primary">{title}</span>
        </div>
        <span className="text-[10px] uppercase font-bold tracking-wider text-themed-muted">
          {endpointLabel}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((card, i) => (
          <div
            key={i}
            className="rounded-card p-3"
            style={{ background: 'var(--color-bg-card, #fff)' }}
          >
            <div className="text-[11px] uppercase tracking-wider text-themed-muted mb-1">
              <MetricLabel helpText={card.helpText}>
                {card.label}
              </MetricLabel>
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-xl font-bold tabular-nums text-themed-primary">
                {card.value}
              </span>
              {card.unit && (
                <span className="text-xs text-themed-muted">{card.unit}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {isEmpty && (
        <p className="text-[11px] text-themed-faint mt-3">
          暂无 30 天聚合数据 — 数据采集 pipeline 跑过后会自动填充。
        </p>
      )}
    </div>
  )
}
