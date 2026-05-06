import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Button, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useIndustries, useIndustryOverview } from '../../hooks/useIndustries';
import {
  LoadingCard,
  EmptyCard,
  ErrorCard,
} from '../brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/industries/:id/overview. */
export default function IndustryOverviewPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const [params, setParams] = useSearchParams();
  const industriesQ = useIndustries();
  const list = industriesQ.data?.items ?? [];
  const industryParam = params.get('industryId');
  const industryId = industryParam
    ? Number(industryParam)
    : list.length > 0
      ? list[0].industry_id
      : null;
  const { data, isLoading, error, refetch } = useIndustryOverview(industryId);

  if (industriesQ.isLoading) return <LoadingCard />;
  if (industriesQ.isError)
    return (
      <ErrorCard
        msg={
          industriesQ.error instanceof Error
            ? industriesQ.error.message
            : 'unknown'
        }
        onRetry={() => industriesQ.refetch()}
      />
    );
  if (list.length === 0) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🏭</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          还没有行业数据
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          后端的 `industries` 表为空. 请管理员通过 `/admin` 添加行业 +
          关联品牌.
        </p>
      </Card>
    );
  }
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty')
    return <EmptyCard onRefresh={() => refetch()} title="行业总览" />;

  const setIndustry = (id: number) => {
    const next = new URLSearchParams(params);
    next.set('industryId', String(id));
    setParams(next);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h2 className="text-heading-2 font-bold text-themed-primary">
            {data.industry_name ?? `Industry #${data.industry_id}`}
          </h2>
          <span className="text-sm text-themed-muted">
            {formatDate(data.period.from)} – {formatDate(data.period.to)}
          </span>
        </div>
        <select
          className="t-input text-sm"
          value={industryId ?? ''}
          onChange={(e) => setIndustry(Number(e.target.value))}
        >
          {list.map((it) => (
            <option key={it.industry_id} value={it.industry_id}>
              {it.name} ({it.brand_count} 品牌)
            </option>
          ))}
        </select>
      </div>

      {data.kpi_cards && data.kpi_cards.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {data.kpi_cards.map((kpi, idx) => (
            <Card key={idx} className="p-4" onClick={undefined} style={{}}>
              <p className="text-[11px] text-themed-muted uppercase tracking-wider">
                {kpi.label_zh}
              </p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-themed-primary">
                {kpi.value.toLocaleString(undefined, {
                  maximumFractionDigits: 1,
                })}
                {kpi.unit ? (
                  <span className="text-sm font-normal ml-0.5">{kpi.unit}</span>
                ) : null}
              </p>
              {kpi.delta_30d_pct != null && (
                <p
                  className="mt-1 text-xs tabular-nums"
                  style={{
                    color:
                      kpi.delta_30d_pct > 0
                        ? '#16a34a'
                        : kpi.delta_30d_pct < 0
                          ? '#dc2626'
                          : '#64748b',
                  }}
                >
                  {kpi.delta_30d_pct > 0 ? '↑' : kpi.delta_30d_pct < 0 ? '↓' : '→'}{' '}
                  {kpi.delta_30d_pct.toFixed(1)}% (30d)
                </p>
              )}
            </Card>
          ))}
        </div>
      )}

      {data.top_brands && data.top_brands.length > 0 && (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <div className="px-5 py-3 border-b border-themed-subtle">
            <h3 className="text-sm font-semibold text-themed-primary">
              Top {data.top_brands.length} 品牌
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                  <th className="py-2 pl-5">排名</th>
                  <th className="py-2 px-3">品牌</th>
                  <th className="py-2 px-3 text-right">GEO 分</th>
                </tr>
              </thead>
              <tbody>
                {data.top_brands.map((b) => (
                  <tr
                    key={b.brand_id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer"
                    onClick={() => navigate(`/brands/${b.brand_id}?tab=overview`)}
                  >
                    <td className="py-2 pl-5 pr-3 text-themed-muted tabular-nums">
                      #{b.rank}
                    </td>
                    <td className="py-2 px-3 text-themed-primary">
                      {b.brand_name ?? `Brand #${b.brand_id}`}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-primary font-semibold">
                      {b.avg_geo_score != null
                        ? b.avg_geo_score.toFixed(1)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {data.events_30d && data.events_30d.length > 0 && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            近期事件 (30d)
          </h3>
          <ul className="space-y-2">
            {data.events_30d.map((ev, idx) => (
              <li
                key={idx}
                className="flex items-start gap-3 text-sm border-b border-themed-subtle pb-2"
              >
                <span className="text-[11px] text-themed-muted tabular-nums shrink-0 w-20">
                  {formatDate(ev.date, { month: 'short', day: 'numeric' })}
                </span>
                <Badge variant="default" size="sm">
                  {ev.event_type}
                </Badge>
                <span className="text-themed-secondary flex-1">
                  {ev.description}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex gap-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            navigate(`/industry/ranking?industryId=${data.industry_id}`)
          }
        >
          看完整排名 →
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            navigate(`/industry/topics?industryId=${data.industry_id}`)
          }
        >
          看主题热度 →
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            navigate(`/industry/knowledge-graph?industryId=${data.industry_id}`)
          }
        >
          看知识图谱 →
        </Button>
      </div>
    </div>
  );
}
