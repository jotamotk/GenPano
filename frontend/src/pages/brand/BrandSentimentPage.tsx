import { useNavigate } from 'react-router-dom';
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
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { useBrandSentiment } from '../../hooks/useBrandMetrics';
import { isLiveProjectId } from '../../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/sentiment. */
export default function BrandSentimentPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useBrandSentiment(
    enabled ? liveProjectId : null,
  );

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="情感" />
    );
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty')
    return <EmptyCard onRefresh={() => refetch()} title="情感" />;

  const dist = data.distribution;
  const distData = [
    { name: '正面', value: dist.positive_pct, color: '#16a34a' },
    { name: '中性', value: dist.neutral_pct, color: '#64748b' },
    { name: '负面', value: dist.negative_pct, color: '#dc2626' },
  ];
  const trend = data.trend_30d;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">情感</h2>
        <span className="text-sm text-themed-muted">
          {formatDate(data.period.from)} – {formatDate(data.period.to)}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            情感分布
          </h3>
          <p className="text-xs text-themed-muted mb-3">
            正面 {dist.positive_count} · 中性 {dist.neutral_count} · 负面{' '}
            {dist.negative_count} (avg = {dist.avg_sentiment_score.toFixed(2)})
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={distData}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} unit="%" />
              <Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {distData.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            情感趋势 (30 天)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={trend}>
              <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d) => formatDate(d, { month: 'short', day: 'numeric' })}
              />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                labelFormatter={(d) =>
                  formatDate(d, { year: 'numeric', month: 'short', day: 'numeric' })
                }
              />
              <Bar dataKey="positive_pct" name="正面%" fill="#16a34a" stackId="a" />
              <Bar dataKey="negative_pct" name="负面%" fill="#dc2626" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            Top 关键词
          </h3>
          {data.top_keywords.length === 0 ? (
            <p className="text-xs text-themed-muted">暂无</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.top_keywords.slice(0, 12).map((k) => (
                <li
                  key={`${k.keyword}-${k.polarity}`}
                  className="flex items-center justify-between border-b border-themed-subtle pb-1.5"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{
                        background: k.polarity === 'positive' ? '#16a34a' : '#dc2626',
                      }}
                    />
                    <span className="text-themed-primary">{k.keyword}</span>
                  </span>
                  <span className="tabular-nums text-themed-muted">{k.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-3">
            Top 情感驱动因子
          </h3>
          {data.top_drivers.length === 0 ? (
            <p className="text-xs text-themed-muted">暂无</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.top_drivers.slice(0, 12).map((d, idx) => (
                <li
                  key={idx}
                  className="flex items-center justify-between border-b border-themed-subtle pb-1.5"
                >
                  <span className="flex items-center gap-2 truncate max-w-md">
                    <span className="text-themed-primary">{d.driver_text}</span>
                    {d.category && (
                      <span className="text-[11px] text-themed-muted">
                        {d.category}
                      </span>
                    )}
                  </span>
                  <span className="tabular-nums text-themed-muted">{d.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
