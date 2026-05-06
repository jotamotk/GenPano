import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useIndustries, useIndustryRanking } from '../../hooks/useIndustries';
import {
  LoadingCard,
  EmptyCard,
  ErrorCard,
} from '../brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/industries/:id/ranking. */
export default function IndustryRankingPage() {
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
  const { data, isLoading, error, refetch } = useIndustryRanking(industryId);

  if (industriesQ.isLoading || isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.items.length === 0)
    return <EmptyCard onRefresh={() => refetch()} title="行业排名" />;

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
            行业排名
          </h2>
          <span className="text-sm text-themed-muted">
            {formatDate(data.period.from)} – {formatDate(data.period.to)}
          </span>
          <span className="text-xs text-themed-muted">共 {data.total}</span>
        </div>
        <select
          className="t-input text-sm"
          value={industryId ?? ''}
          onChange={(e) => setIndustry(Number(e.target.value))}
        >
          {list.map((it) => (
            <option key={it.industry_id} value={it.industry_id}>
              {it.name}
            </option>
          ))}
        </select>
      </div>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-2 pl-5">排名</th>
                <th className="py-2 px-3">品牌</th>
                <th className="py-2 px-3 text-right">GEO 分</th>
                <th className="py-2 px-3 text-right">提及率</th>
                <th className="py-2 px-3 text-right">SoV</th>
                <th className="py-2 px-3 text-right">情感</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr
                  key={row.brand_id}
                  className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer"
                  onClick={() => navigate(`/brands/${row.brand_id}?tab=overview`)}
                >
                  <td className="py-2 pl-5 pr-3 text-themed-muted tabular-nums">
                    #{row.rank}
                  </td>
                  <td className="py-2 px-3 text-themed-primary font-medium">
                    {row.brand_name ?? `Brand #${row.brand_id}`}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-primary font-semibold">
                    {row.avg_geo_score != null
                      ? row.avg_geo_score.toFixed(1)
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {row.avg_mention_rate != null
                      ? `${(row.avg_mention_rate * 100).toFixed(1)}%`
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {row.avg_sov != null
                      ? `${(row.avg_sov * 100).toFixed(1)}%`
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {row.avg_sentiment != null
                      ? row.avg_sentiment.toFixed(2)
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
