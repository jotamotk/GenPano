import { useNavigate, useParams } from 'react-router-dom';
import { Badge, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import { useBrandProducts } from '../hooks/useBrandMetrics';
import { isLiveProjectId } from '../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
} from './brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/products. */
export default function BrandProductDetailPage() {
  const { productId } = useParams();
  const navigate = useNavigate();
  const { formatNumber } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, refetch } = useBrandProducts(
    enabled ? liveProjectId : null,
  );

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="产品详情" />
    );
  if (isLoading) return <LoadingCard />;

  const numericId = productId && /^\d+$/.test(productId) ? Number(productId) : null;
  const product = data?.items.find((p) => p.product_id === numericId) ?? null;

  if (!product) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🛍️</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          找不到此产品
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          产品 #{productId} 不在当前 Project 的 product list 中. 它可能尚未
          被 analyzer 分类入库.
        </p>
        <button
          type="button"
          onClick={() => navigate('/brand/products')}
          className="text-sm text-themed-accent hover:opacity-80"
        >
          ← 返回产品列表
        </button>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => navigate('/brand/products')}
          className="text-sm text-themed-muted hover:text-themed-primary"
        >
          ← 产品列表
        </button>
        <div className="h-4 w-px bg-themed-card" />
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">
          {product.product_name}
        </h2>
      </div>

      <Card className="p-5" onClick={undefined} style={{}}>
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <p className="text-xs text-themed-muted">SKU / 类目</p>
            <p className="text-sm text-themed-secondary mt-1">
              {product.sku ?? '—'}{' '}
              {product.category ? `· ${product.category}` : ''}
            </p>
            <p className="text-xs text-themed-muted mt-3">所属品牌</p>
            <button
              type="button"
              onClick={() =>
                product.brand_id != null &&
                navigate(`/brands/${product.brand_id}?tab=overview`)
              }
              className="text-sm text-themed-accent hover:underline"
              disabled={product.brand_id == null}
            >
              Brand #{product.brand_id ?? '?'}
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiBox
              label="GEO 分"
              value={
                product.avg_geo_score != null
                  ? product.avg_geo_score.toFixed(1)
                  : '—'
              }
            />
            <KpiBox label="提及" value={product.mention_count.toString()} />
            <KpiBox
              label="平均位置"
              value={
                product.avg_position_rank != null
                  ? `#${product.avg_position_rank.toFixed(1)}`
                  : '—'
              }
            />
            <KpiBox
              label="胜率"
              value={
                product.win_rate != null
                  ? `${formatNumber(product.win_rate * 100, {
                      maximumFractionDigits: 1,
                    })}%`
                  : '—'
              }
            />
          </div>
        </div>
      </Card>

      <Card className="p-5" onClick={undefined} style={{}}>
        <p className="text-sm text-themed-muted">
          产品级深度 (推荐语境 / 关系视图 / Prompt 命中) 当前依赖 Phase A
          的 product feature 聚合管线. 数据可用后将在此处出现详细面板.
        </p>
        <button
          type="button"
          onClick={() => refetch()}
          className="mt-3 text-sm text-themed-accent hover:opacity-80"
        >
          刷新
        </button>
      </Card>
    </div>
  );
}

function KpiBox({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-card border p-3"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border-subtle)',
      }}
    >
      <p className="text-[11px] uppercase tracking-wider text-themed-muted">
        {label}
      </p>
      <p className="mt-1 text-xl font-bold tabular-nums text-themed-primary">
        {value}
      </p>
    </div>
  );
}
