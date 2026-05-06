import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Card } from '../components/ui';
import { useProjects } from '../hooks/useProjects';
import { useBrandTopics } from '../hooks/useBrandMetrics';
import { isLiveProjectId } from '../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/topics. */
export default function TopicsPage() {
  const navigate = useNavigate();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useBrandTopics(
    enabled ? liveProjectId : null,
  );
  const [stateFilter, setStateFilter] = useState<
    'all' | 'tracked' | 'ignored' | 'unpinned'
  >('all');

  if (!enabled)
    return <NoProjectCard onStart={() => navigate('/onboarding')} title="主题" />;
  if (isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.items.length === 0)
    return <EmptyCard onRefresh={() => refetch()} title="主题" />;

  const items =
    stateFilter === 'all'
      ? data.items
      : data.items.filter((it) => it.state === stateFilter);

  const counts = {
    all: data.items.length,
    tracked: data.items.filter((i) => i.state === 'tracked').length,
    ignored: data.items.filter((i) => i.state === 'ignored').length,
    unpinned: data.items.filter((i) => i.state === 'unpinned').length,
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">主题</h2>
        <span className="text-xs text-themed-muted">共 {data.total}</span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {(['all', 'tracked', 'unpinned', 'ignored'] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStateFilter(s)}
            className={`text-[11px] px-3 py-1 rounded-pill border transition-colors ${
              stateFilter === s
                ? 'border-themed-strong text-themed-primary bg-themed-badge'
                : 'border-themed-card text-themed-muted hover:text-themed-primary'
            }`}
          >
            {s === 'all'
              ? '全部'
              : s === 'tracked'
                ? '已订阅'
                : s === 'unpinned'
                  ? '未订阅'
                  : '已忽略'}{' '}
            ({counts[s]})
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-2 pl-5">主题</th>
                <th className="py-2 px-3">状态</th>
                <th className="py-2 px-3 text-right">提及</th>
                <th className="py-2 px-3 text-right">情感</th>
                <th className="py-2 px-3 text-right">平均位置</th>
                <th className="py-2 px-3 text-right">最近</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.topic_id}
                  className="border-t border-themed-subtle hover:bg-themed-subtle"
                >
                  <td className="py-2 pl-5 pr-3 text-themed-primary font-medium">
                    {t.topic_name}
                  </td>
                  <td className="py-2 px-3">
                    <Badge
                      size="sm"
                      variant={
                        t.state === 'tracked'
                          ? 'accent'
                          : t.state === 'ignored'
                            ? 'red'
                            : 'default'
                      }
                    >
                      {t.state}
                    </Badge>
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {t.mention_count}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {t.avg_sentiment != null ? t.avg_sentiment.toFixed(2) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                    {t.avg_position_rank != null
                      ? `#${t.avg_position_rank.toFixed(1)}`
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-muted text-xs">
                    {t.last_seen_at
                      ? new Date(t.last_seen_at).toLocaleDateString('zh-CN')
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
