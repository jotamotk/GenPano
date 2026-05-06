import { useNavigate } from 'react-router-dom';
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { useBrandProducts } from '../../hooks/useBrandMetrics';
import { isLiveProjectId } from '../../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/products. */
export default function BrandProductsPage() {
  const navigate = useNavigate();
  const { formatNumber } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useBrandProducts(
    enabled ? liveProjectId : null,
  );

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="产品" />
    );
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.items.length === 0)
    return <EmptyCard onRefresh={() => refetch()} title="产品" />;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">产品</h2>
        <span className="text-xs text-themed-muted">
          共 {data.total} 个产品
        </span>
      </div>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-2 pl-5">产品</th>
                <th className="py-2 px-3">SKU / 类目</th>
                <th className="py-2 px-3 text-right">提及</th>
                <th className="py-2 px-3 text-right">平均位置</th>
                <th className="py-2 px-3 text-right">GEO 分</th>
                <th className="py-2 px-3 text-right">胜率</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr
                  key={p.product_id}
                  className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer"
                  onClick={() =>
                    navigate(`/brand/products/${p.product_id}`)
                  }
                >
                  <td className="py-2 pl-5 pr-3">
                    <div className="text-themed-primary font-medium">
                      {p.product_name}
                    </div>
                    <div className="text-[11px] text-themed-muted">
                      Brand #{p.brand_id ?? '?'}
                    </div>
                  </td>
                  <td className="py-2 px-3 text-themed-muted text-xs">
                    {p.sku ?? '—'} {p.category ? `· ${p.category}` : ''}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {p.mention_count}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {p.avg_position_rank != null
                      ? `#${p.avg_position_rank.toFixed(1)}`
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-primary font-semibold">
                    {p.avg_geo_score != null ? p.avg_geo_score.toFixed(1) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {p.win_rate != null
                      ? formatNumber(p.win_rate * 100, {
                          maximumFractionDigits: 1,
                        }) + '%'
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
