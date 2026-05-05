/**
 * ProductDetailLiveBanner — surfaces a single live product row on
 * BrandProductDetailPage when the URL :productId matches a real
 * product_id (number) returned by GET /v1/projects/:id/products.
 *
 * Returns null otherwise — mock-only sessions / non-numeric productIds
 * see no banner.
 */
import { Badge, Card } from '../ui'
import { useProjects } from '../../hooks/useProjects'
import { useBrandProducts } from '../../hooks/useBrandMetrics'
import { isLiveProjectId } from '../../hooks/useBrandOverview'

export default function ProductDetailLiveBanner({
  productId,
}: {
  productId: string | null | undefined
}) {
  const { data: projects } = useProjects()
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null
  const { data, isLoading } = useBrandProducts(
    isLiveProjectId(liveProjectId) ? liveProjectId : null,
  )

  if (!isLiveProjectId(liveProjectId)) return null
  const numericId = productId && /^\d+$/.test(productId) ? Number(productId) : null
  if (numericId == null) return null

  const product = data?.items.find((p) => p.product_id === numericId) ?? null

  if (isLoading) {
    return (
      <Card
        className="p-3"
        style={{ background: 'var(--color-accent-bg-light)' }}
        onClick={undefined}
      >
        <span className="text-[11px] text-themed-muted">加载产品实时数据…</span>
      </Card>
    )
  }
  if (!product) return null

  return (
    <Card
      className="p-4"
      style={{ background: 'var(--color-accent-bg-light)' }}
      onClick={undefined}
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <span className="text-sm font-medium text-themed-primary">
            {product.product_name}
          </span>
          <span className="text-[11px] text-themed-muted">
            #{product.product_id} · 来自 GET /v1/projects/:id/products
          </span>
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          <KpiCell
            label="GEO 分"
            value={
              product.avg_geo_score != null
                ? product.avg_geo_score.toFixed(1)
                : '—'
            }
          />
          <KpiCell
            label="提及"
            value={product.mention_count.toString()}
          />
          <KpiCell
            label="平均排名"
            value={
              product.avg_position_rank != null
                ? `#${product.avg_position_rank.toFixed(1)}`
                : '—'
            }
          />
          <KpiCell
            label="胜率"
            value={
              product.win_rate != null
                ? `${(product.win_rate * 100).toFixed(1)}%`
                : '—'
            }
          />
        </div>
      </div>
    </Card>
  )
}

function KpiCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <p className="text-[10px] uppercase tracking-wider text-themed-muted">
        {label}
      </p>
      <p className="text-sm font-semibold tabular-nums text-themed-primary">
        {value}
      </p>
    </div>
  )
}
