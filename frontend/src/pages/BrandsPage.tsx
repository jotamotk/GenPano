import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import { useCompetitorMetrics } from '../hooks/useBrandMetrics';
import { isLiveProjectId } from '../hooks/useReports';

/* ─────────────────────────────────────────────────────────────
   BrandsPage — PRD §4.6.1b 列表入口
   ─────────────────────────────────────────────────────────────
   Phase 5 §"mock 退役" — 列表数据 100% 来自
   GET /v1/projects/:id/competitors/metrics (Phase 2.2). 不再 import
   mock; 用户没有 Project 时跳引导, 有 Project 但 0 竞品时显示空态.
*/
export default function BrandsPage() {
  const navigate = useNavigate();
  const { t, formatNumber } = useLocale();
  const { data: liveProjects, isLoading: projLoading } = useProjects();
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useCompetitorMetrics(
    enabled ? liveProjectId : null,
  );

  if (projLoading || (enabled && isLoading)) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  if (!enabled) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🏷️</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          还没有 Project
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          创建 Project 后, 这里会列出你的主品牌 + 选择的竞品矩阵.
        </p>
        <Button variant="primary" size="sm" onClick={() => navigate('/onboarding')}>
          开始引导
        </Button>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted mb-3">
          加载失败: {error instanceof Error ? error.message : 'unknown'}
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          重试
        </Button>
      </Card>
    );
  }

  const primary = data?.primary ?? null;
  const competitors = data?.competitors ?? [];
  const rows = primary ? [primary, ...competitors] : competitors;

  if (rows.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            {t('brand.list_title')}
          </h2>
          <p className="text-sm text-themed-muted mt-1">{t('brand.list_subtitle')}</p>
        </div>
        <Card className="p-12 text-center" onClick={undefined} style={{}}>
          <div className="text-3xl mb-3">📡</div>
          <h3 className="text-base font-semibold text-themed-primary mb-2">
            首批数据采集中
          </h3>
          <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
            Project 已创建, 后端正在采集. 通常首批数据在 24h 内入库.
          </p>
          <Button variant="primary" size="sm" onClick={() => refetch()}>
            刷新
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">
            {t('brand.list_title')}
          </h2>
          <p className="text-sm text-themed-muted mt-1">{t('brand.list_subtitle')}</p>
        </div>
        <Badge variant="default">LIVE</Badge>
      </div>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="overflow-x-auto">
          <table className="w-full t-table">
            <thead>
              <tr>
                <th className="text-left py-3 px-5 font-medium text-themed-muted text-xs">
                  品牌
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  GEO 分
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  提及率
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  SoV
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  情感
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  共现
                </th>
                <th className="text-right py-3 px-4 font-medium text-themed-muted text-xs">
                  30d Δ%
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isPrimary = primary != null && row.brand_id === primary.brand_id;
                const delta = row.delta_30d_pct;
                const deltaTone =
                  delta == null
                    ? 'text-themed-muted'
                    : delta > 0
                      ? 'text-themed-success'
                      : delta < 0
                        ? 'text-themed-danger'
                        : 'text-themed-muted';
                return (
                  <tr
                    key={row.brand_id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer transition-colors"
                    onClick={() =>
                      navigate(`/brands/${row.brand_id}?tab=overview`)
                    }
                    style={
                      isPrimary
                        ? { background: 'var(--color-accent-subtle)' }
                        : undefined
                    }
                  >
                    <td className="py-3 px-5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-themed-primary">
                          {row.brand_name ?? `Brand #${row.brand_id}`}
                        </span>
                        <span className="text-[11px] text-themed-muted">
                          #{row.brand_id}
                        </span>
                        {isPrimary ? (
                          <Badge variant="accent" size="sm">主品牌</Badge>
                        ) : (
                          <Badge variant="default" size="sm">竞品</Badge>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right text-sm font-semibold tabular-nums text-themed-primary">
                      {row.avg_geo_score != null ? row.avg_geo_score.toFixed(1) : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {row.avg_mention_rate != null
                        ? formatNumber(row.avg_mention_rate * 100, {
                            maximumFractionDigits: 1,
                          }) + '%'
                        : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {row.avg_sov != null
                        ? formatNumber(row.avg_sov * 100, {
                            maximumFractionDigits: 1,
                          }) + '%'
                        : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {row.avg_sentiment != null
                        ? row.avg_sentiment.toFixed(2)
                        : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {row.co_mention_count}
                    </td>
                    <td
                      className={`py-3 px-4 text-right text-sm tabular-nums ${deltaTone}`}
                    >
                      {delta != null
                        ? `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%`
                        : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
