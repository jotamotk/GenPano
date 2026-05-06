import { useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { Badge, Button, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { useBrandMetrics } from '../../hooks/useBrandMetrics';
import { isLiveProjectId } from '../../hooks/useReports';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/metrics. */
export default function BrandVisibilityPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects, isLoading: projLoading } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useBrandMetrics(
    enabled ? liveProjectId : null,
    ['mention_rate', 'sov', 'rank', 'sentiment'],
  );

  if (projLoading) return <LoadingCard />;
  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="可见度" />
    );
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.series.length === 0) {
    return <EmptyCard onRefresh={() => refetch()} title="可见度" />;
  }

  const series = data.series;
  const mention = series.find((s) => s.metric === 'mention_rate');
  const sov = series.find((s) => s.metric === 'sov');
  const rank = series.find((s) => s.metric === 'rank');
  const sentiment = series.find((s) => s.metric === 'sentiment');

  const merged = mergeSeries({ mention, sov, rank, sentiment });

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">可见度</h2>
        <span className="text-sm text-themed-muted">
          {formatDate(data.period.from)} – {formatDate(data.period.to)}
        </span>
      </div>

      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          提及率 / SoV (30 天)
        </h3>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={merged}>
            <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              tickFormatter={(d) =>
                formatDate(d, { month: 'short', day: 'numeric' })
              }
            />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              labelFormatter={(d) =>
                formatDate(d, { year: 'numeric', month: 'short', day: 'numeric' })
              }
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="mention_rate"
              name="提及率"
              stroke="#635bff"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="sov"
              name="SoV"
              stroke="#16a34a"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          排名 / 情感 (30 天)
        </h3>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={merged}>
            <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              tickFormatter={(d) =>
                formatDate(d, { month: 'short', day: 'numeric' })
              }
            />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              labelFormatter={(d) =>
                formatDate(d, { year: 'numeric', month: 'short', day: 'numeric' })
              }
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="rank"
              name="排名"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="sentiment"
              name="情感"
              stroke="#dc2626"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

interface SeriesPair {
  date: string;
  value: number;
}

function mergeSeries(s: {
  mention?: { points: SeriesPair[] } | undefined;
  sov?: { points: SeriesPair[] } | undefined;
  rank?: { points: SeriesPair[] } | undefined;
  sentiment?: { points: SeriesPair[] } | undefined;
}): Array<Record<string, string | number>> {
  const dates = new Set<string>();
  for (const ser of [s.mention, s.sov, s.rank, s.sentiment]) {
    if (ser) for (const p of ser.points) dates.add(p.date);
  }
  const sorted = Array.from(dates).sort();
  const lookup = (ser: { points: SeriesPair[] } | undefined, d: string) => {
    if (!ser) return null;
    const p = ser.points.find((q) => q.date === d);
    return p ? p.value : null;
  };
  return sorted.map((d) => ({
    date: d,
    mention_rate: (lookup(s.mention, d) ?? 0) * 100,
    sov: (lookup(s.sov, d) ?? 0) * 100,
    rank: lookup(s.rank, d) ?? 0,
    sentiment: lookup(s.sentiment, d) ?? 0,
  }));
}

export function LoadingCard() {
  return (
    <Card className="p-12 text-center" onClick={undefined} style={{}}>
      <div className="text-sm text-themed-muted">加载…</div>
    </Card>
  );
}

export function NoProjectCard({
  onStart,
  title,
}: {
  onStart: () => void;
  title: string;
}) {
  return (
    <Card className="p-12 text-center" onClick={undefined} style={{}}>
      <div className="text-3xl mb-3">📊</div>
      <h3 className="text-base font-semibold text-themed-primary mb-2">
        {title}
      </h3>
      <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
        先创建 Project (主品牌 + 行业 + 竞品), 之后这里会显示真实指标.
      </p>
      <Button variant="primary" size="sm" onClick={onStart}>
        开始引导
      </Button>
    </Card>
  );
}

export function EmptyCard({
  onRefresh,
  title,
}: {
  onRefresh: () => void;
  title: string;
}) {
  return (
    <Card className="p-12 text-center" onClick={undefined} style={{}}>
      <div className="text-3xl mb-3">📡</div>
      <h3 className="text-base font-semibold text-themed-primary mb-2">
        {title} — 数据采集中
      </h3>
      <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
        Project 已就绪, 后端正在采集首批 LLM 响应. 通常 24h 内入库.
      </p>
      <Button variant="primary" size="sm" onClick={onRefresh}>
        刷新
      </Button>
    </Card>
  );
}

export function ErrorCard({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <Card className="p-12 text-center" onClick={undefined} style={{}}>
      <div className="text-sm text-themed-muted mb-3">加载失败: {msg}</div>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        重试
      </Button>
    </Card>
  );
}
