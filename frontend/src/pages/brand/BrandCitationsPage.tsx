import { useNavigate } from 'react-router-dom';
import { Badge, Card } from '../../components/ui';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { useBrandCitations } from '../../hooks/useBrandMetrics';
import { isLiveProjectId } from '../../hooks/useReports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/projects/:id/citations. */
export default function BrandCitationsPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data, isLoading, error, refetch } = useBrandCitations(
    enabled ? liveProjectId : null,
    100,
  );

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="引用" />
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
    return <EmptyCard onRefresh={() => refetch()} title="引用" />;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="default">LIVE</Badge>
        <h2 className="text-heading-2 font-bold text-themed-primary">引用</h2>
        <span className="text-sm text-themed-muted">
          {formatDate(data.period.from)} – {formatDate(data.period.to)}
        </span>
        <span className="text-xs text-themed-muted">
          共 {data.total} 条 (展示前 {data.items.length})
        </span>
      </div>

      <Card className="p-5" onClick={undefined} style={{}}>
        <h3 className="text-sm font-semibold text-themed-primary mb-3">
          Top 引用域
        </h3>
        {data.by_domain_top.length === 0 ? (
          <p className="text-xs text-themed-muted">暂无</p>
        ) : (
          <ul className="space-y-2">
            {data.by_domain_top.map((row) => (
              <li
                key={row.domain}
                className="flex items-center justify-between text-sm border-b border-themed-subtle pb-1.5"
              >
                <span className="text-themed-primary truncate">{row.domain}</span>
                <span className="text-themed-muted text-xs tabular-nums">
                  {row.count} 次
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div className="px-5 py-3 border-b border-themed-subtle">
          <h3 className="text-sm font-semibold text-themed-primary">
            最近引用 ({data.items.length})
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-2 pl-5">域名</th>
                <th className="py-2 px-3">标题 / URL</th>
                <th className="py-2 px-3">类型</th>
                <th className="py-2 px-3 text-right">时间</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr
                  key={c.citation_id}
                  className="border-t border-themed-subtle hover:bg-themed-subtle"
                >
                  <td className="py-2 pl-5 pr-3 text-themed-primary">
                    {c.domain ?? '—'}
                  </td>
                  <td className="py-2 px-3 text-themed-secondary truncate max-w-md">
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-themed-accent"
                    >
                      {c.title || c.url}
                    </a>
                  </td>
                  <td className="py-2 px-3 text-themed-muted text-xs">
                    {c.source_type ?? '—'}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-themed-muted text-xs">
                    {c.occurred_at ? formatDate(c.occurred_at, {
                      month: 'short',
                      day: 'numeric',
                    }) : '—'}
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
