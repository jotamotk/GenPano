import { useNavigate, useParams } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from 'recharts';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import {
  useBrandProducts,
  useBrandSentiment,
  useBrandCitations,
} from '../hooks/useBrandMetrics';
import { isLiveProjectId } from '../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
} from './brand/BrandVisibilityPage';

const CONTEXT_COLORS = ['#635bff', '#16a34a', '#f59e0b', '#dc2626', '#0ea5e9', '#a855f7'];

/* Phase 5 §"mock 退役" — 整页来自 /v1/projects/:id/products + sentiment + citations.
   恢复了原版可视化: KPI hero + 推荐语境柱状图 + 引用域分布 + 关联 prompt. */
export default function BrandProductDetailPage() {
  const { productId } = useParams();
  const navigate = useNavigate();
  const { formatDate, formatNumber } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const productsQ = useBrandProducts(enabled ? liveProjectId : null);
  const sentimentQ = useBrandSentiment(enabled ? liveProjectId : null);
  const citationsQ = useBrandCitations(enabled ? liveProjectId : null, 30);

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="产品详情" />
    );
  if (productsQ.isLoading) return <LoadingCard />;

  const numericId = productId && /^\d+$/.test(productId) ? Number(productId) : null;
  const product = productsQ.data?.items.find((p) => p.product_id === numericId) ?? null;

  if (!product) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🛍️</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          找不到此产品
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          产品 #{productId} 不在当前 Project 的 product list 里. 它可能尚未被
          analyzer 分类入库.
        </p>
        <Button variant="secondary" size="sm" onClick={() => navigate('/brand/products')}>
          ← 返回产品列表
        </Button>
      </Card>
    );
  }

  // Sibling products in the same brand for context
  const siblings = (productsQ.data?.items ?? [])
    .filter((p) => p.brand_id === product.brand_id && p.product_id !== product.product_id)
    .slice(0, 6);
  const siblingChart = siblings
    .filter((p) => p.avg_geo_score != null)
    .map((p) => ({
      name: p.product_name,
      value: p.avg_geo_score ?? 0,
    }));

  // Top sentiment drivers as recommended contexts (proxy)
  const drivers = (sentimentQ.data?.top_drivers ?? [])
    .filter((d) => d.polarity === 'positive')
    .slice(0, 6)
    .map((d) => ({
      name: d.driver_text,
      value: d.count,
    }));

  // Top citation domains
  const topDomains = citationsQ.data?.by_domain_top ?? [];

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
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

      {/* Hero */}
      <Card className="p-5" onClick={undefined} style={{}}>
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <p className="text-xs text-themed-muted">所属品牌</p>
            <button
              type="button"
              onClick={() =>
                product.brand_id != null &&
                navigate(`/brands/${product.brand_id}?tab=overview`)
              }
              className="text-base text-themed-accent hover:underline mt-1"
              disabled={product.brand_id == null}
            >
              Brand #{product.brand_id ?? '?'}
            </button>
            {product.sku && (
              <>
                <p className="text-xs text-themed-muted mt-3">SKU</p>
                <p className="text-sm text-themed-secondary mt-1">{product.sku}</p>
              </>
            )}
            {product.category && (
              <>
                <p className="text-xs text-themed-muted mt-3">类目</p>
                <p className="text-sm text-themed-secondary mt-1">
                  {product.category}
                </p>
              </>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiBox
              label="GEO 分"
              value={
                product.avg_geo_score != null
                  ? product.avg_geo_score.toFixed(1)
                  : '—'
              }
              tone={product.avg_geo_score != null && product.avg_geo_score >= 70 ? 'good' : undefined}
            />
            <KpiBox label="提及次数" value={product.mention_count.toString()} />
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
              tone={product.win_rate != null && product.win_rate > 0.5 ? 'good' : undefined}
            />
          </div>
        </div>
      </Card>

      {/* Recommended contexts (positive sentiment drivers as proxy) */}
      {drivers.length > 0 && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-1">
            推荐语境 (Top {drivers.length} 正面驱动因子)
          </h3>
          <p className="text-xs text-themed-muted mb-3">
            来自 sentiment_drivers (polarity=positive) 在该品牌产品提及中
          </p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={drivers}
              layout="vertical"
              margin={{ top: 4, right: 16, bottom: 4, left: 16 }}
            >
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis
                dataKey="name"
                type="category"
                tick={{ fontSize: 11 }}
                width={120}
              />
              <Tooltip />
              <Bar dataKey="value" radius={[4, 4, 4, 4]}>
                {drivers.map((_, i) => (
                  <Cell key={i} fill={CONTEXT_COLORS[i % CONTEXT_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Sibling products in same brand */}
      {siblingChart.length > 0 && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            同品牌产品 GEO 分对比
          </h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={siblingChart}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#635bff" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Top citation domains */}
      {topDomains.length > 0 && (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <div className="px-5 py-3 border-b border-themed-subtle">
            <h3 className="text-sm font-semibold text-themed-primary">
              引用域 Top {topDomains.length}
            </h3>
          </div>
          <ul className="divide-y divide-themed">
            {topDomains.map((d) => (
              <li
                key={d.domain}
                className="flex items-center justify-between px-5 py-2 text-sm"
              >
                <span className="text-themed-primary truncate">{d.domain}</span>
                <span className="tabular-nums text-themed-muted text-xs">
                  {d.count} 次
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function KpiBox({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'good' | 'bad';
}) {
  const color =
    tone === 'good' ? '#16a34a' : tone === 'bad' ? '#dc2626' : undefined;
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
      <p
        className="mt-1 text-xl font-bold tabular-nums"
        style={{ color: color ?? 'var(--color-text-primary)' }}
      >
        {value}
      </p>
    </div>
  );
}
