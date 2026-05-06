import { useSearchParams } from 'react-router-dom';
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useIndustries, useIndustryTopics } from '../../hooks/useIndustries';
import {
  LoadingCard,
  EmptyCard,
  ErrorCard,
} from '../brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/industries/:id/topics. */
export default function IndustryTopicsPage() {
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
  const { data, isLoading, error, refetch } = useIndustryTopics(industryId);

  if (industriesQ.isLoading || isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.items.length === 0)
    return <EmptyCard onRefresh={() => refetch()} title="行业主题" />;

  const setIndustry = (id: number) => {
    const next = new URLSearchParams(params);
    next.set('industryId', String(id));
    setParams(next);
  };

  const maxHot = Math.max(...data.items.map((t) => t.hot_score ?? 0));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h2 className="text-heading-2 font-bold text-themed-primary">
            行业主题热度
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
                <th className="py-2 pl-5">主题</th>
                <th className="py-2 px-3 text-right">提及次数</th>
                <th className="py-2 px-3 text-right">独立品牌数</th>
                <th className="py-2 px-3">热度</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((t) => {
                const hot = t.hot_score ?? 0;
                const pct = maxHot > 0 ? (hot / maxHot) * 100 : 0;
                return (
                  <tr
                    key={`${t.topic_id ?? t.topic_name}`}
                    className="border-t border-themed-subtle"
                  >
                    <td className="py-2 pl-5 pr-3 text-themed-primary font-medium">
                      {t.topic_name}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {t.mention_count}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {t.unique_brand_count}
                    </td>
                    <td className="py-2 px-3 w-1/3">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            width: `${pct.toFixed(1)}%`,
                            background: 'linear-gradient(90deg, #635bff, #f59e0b)',
                          }}
                        />
                        <span className="text-[11px] text-themed-muted tabular-nums">
                          {hot.toFixed(1)}
                        </span>
                      </div>
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
