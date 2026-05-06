import { useNavigate } from 'react-router-dom';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { useCompetitorMetrics } from '../../hooks/useBrandMetrics';
import { isLiveProjectId } from '../../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 /v1/projects/:id/competitors/metrics. */
export default function BrandCompetitorsPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useCompetitorMetrics(
    enabled ? liveProjectId : null,
  );

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="竞品" />
    );
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || (!data.primary && data.competitors.length === 0))
    return <EmptyCard onRefresh={() => refetch()} title="竞品" />;

  const rows = [
    ...(data.primary ? [data.primary] : []),
    ...data.competitors,
  ];

  // Radar data: each metric scaled 0-100 for fair comparison
  const radarMetrics = ['avg_geo_score', 'avg_mention_rate', 'avg_sov', 'avg_sentiment'] as const;
  const radarLabels: Record<string, string> = {
    avg_geo_score: 'GEO 分',
    avg_mention_rate: '提及率',
    avg_sov: 'SoV',
    avg_sentiment: '情感',
  };
  const radarData = radarMetrics.map((metric) => {
    const point: Record<string, number | string> = { metric: radarLabels[metric] };
    for (const r of rows) {
      const raw = r[metric];
      let scaled = 0;
      if (raw != null) {
        if (metric === 'avg_geo_score') scaled = raw;
        else if (metric === 'avg_sentiment') scaled = (raw + 1) * 50;
        else scaled = raw * 100;
      }
      point[`brand_${r.brand_id}`] = scaled;
    }
    return point;
  });
  const radarColors = [
    '#635bff',
    '#16a34a',
    '#f59e0b',
    '#dc2626',
    '#0ea5e9',
    '#a855f7',
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">竞品</h2>
        <span className="text-sm text-themed-muted">
          {formatDate(data.period.from)} – {formatDate(data.period.to)}
        </span>
      </div>

      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          四维雷达
        </h3>
        <ResponsiveContainer width="100%" height={360}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="var(--color-chart-line-grid)" />
            <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
            <PolarRadiusAxis tick={{ fontSize: 9 }} angle={90} />
            <Legend />
            {rows.map((r, idx) => (
              <Radar
                key={r.brand_id}
                name={r.brand_name ?? `Brand #${r.brand_id}`}
                dataKey={`brand_${r.brand_id}`}
                stroke={radarColors[idx % radarColors.length]}
                fill={radarColors[idx % radarColors.length]}
                fillOpacity={0.15}
              />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </Card>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-2 pl-5">品牌</th>
                <th className="py-2 px-3 text-right">GEO 分</th>
                <th className="py-2 px-3 text-right">提及率</th>
                <th className="py-2 px-3 text-right">SoV</th>
                <th className="py-2 px-3 text-right">情感</th>
                <th className="py-2 px-3 text-right">共现</th>
                <th className="py-2 px-3 text-right">30d Δ%</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isPrimary = data.primary?.brand_id === r.brand_id;
                const delta = r.delta_30d_pct;
                const tone =
                  delta == null
                    ? 'text-themed-muted'
                    : delta > 0
                      ? 'text-themed-success'
                      : delta < 0
                        ? 'text-themed-danger'
                        : 'text-themed-muted';
                return (
                  <tr
                    key={r.brand_id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle cursor-pointer"
                    onClick={() => navigate(`/brands/${r.brand_id}?tab=overview`)}
                  >
                    <td className="py-2 pl-5 pr-3">
                      <div className="flex items-center gap-2">
                        <span className="text-themed-primary font-medium">
                          {r.brand_name ?? `Brand #${r.brand_id}`}
                        </span>
                        {isPrimary && <Badge variant="accent" size="sm">主品牌</Badge>}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-primary font-semibold">
                      {r.avg_geo_score != null ? r.avg_geo_score.toFixed(1) : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {r.avg_mention_rate != null
                        ? `${(r.avg_mention_rate * 100).toFixed(1)}%`
                        : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {r.avg_sov != null ? `${(r.avg_sov * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {r.avg_sentiment != null ? r.avg_sentiment.toFixed(2) : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {r.co_mention_count}
                    </td>
                    <td className={`py-2 px-3 text-right tabular-nums ${tone}`}>
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
