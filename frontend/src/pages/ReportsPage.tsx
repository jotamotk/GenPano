import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Card } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { useProjects } from '../hooks/useProjects';
import {
  isLiveProjectId,
  useReports,
  useCreateReport,
} from '../hooks/useReports';
import { reportsApi } from '../api/reports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 整页来自 GET/POST /v1/projects/:id/reports.
   Removes the 1440-LOC mock SECTION_MATRIX / DIAGNOSTICS-driven view. */
export default function ReportsPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const reportsQ = useReports(enabled ? liveProjectId : null, 50);
  const createReport = useCreateReport(enabled ? liveProjectId : null);
  const [showGenerate, setShowGenerate] = useState(false);

  if (!enabled)
    return (
      <NoProjectCard onStart={() => navigate('/onboarding')} title="报告" />
    );
  if (reportsQ.isLoading) return <LoadingCard />;
  if (reportsQ.error)
    return (
      <ErrorCard
        msg={reportsQ.error instanceof Error ? reportsQ.error.message : 'unknown'}
        onRetry={() => reportsQ.refetch()}
      />
    );

  const items = reportsQ.data?.items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h2 className="text-heading-2 font-bold text-themed-primary">报告</h2>
          <span className="text-xs text-themed-muted">共 {items.length}</span>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowGenerate(true)}
          disabled={createReport.isPending}
        >
          {createReport.isPending ? '生成中…' : '生成新报告'}
        </Button>
      </div>

      {items.length === 0 ? (
        <EmptyCard onRefresh={() => reportsQ.refetch()} title="报告" />
      ) : (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                  <th className="py-2 pl-5">类型</th>
                  <th className="py-2 px-3">Job ID</th>
                  <th className="py-2 px-3">状态</th>
                  <th className="py-2 px-3">创建时间</th>
                  <th className="py-2 px-3 text-right">下载</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle"
                  >
                    <td className="py-2 pl-5 pr-3">
                      <Badge variant="default" size="sm">
                        {r.type}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-themed-muted text-xs tabular-nums">
                      {r.id.slice(0, 8)}
                    </td>
                    <td className="py-2 px-3">
                      <Badge
                        variant={
                          r.status === 'done'
                            ? 'green'
                            : r.status === 'failed'
                              ? 'red'
                              : 'default'
                        }
                        size="sm"
                      >
                        {r.status}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-themed-muted text-xs">
                      {formatDate(r.created_at, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {r.status === 'done' ? (
                        <div className="flex items-center justify-end gap-2">
                          <a
                            href={reportsApi.downloadUrl(
                              liveProjectId as string,
                              r.id,
                              'markdown',
                            )}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-themed-accent hover:opacity-80"
                          >
                            MD
                          </a>
                          <a
                            href={reportsApi.downloadUrl(
                              liveProjectId as string,
                              r.id,
                              'json',
                            )}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-themed-accent hover:opacity-80"
                          >
                            JSON
                          </a>
                          <a
                            href={reportsApi.downloadUrl(
                              liveProjectId as string,
                              r.id,
                              'csv',
                            )}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-themed-accent hover:opacity-80"
                          >
                            CSV
                          </a>
                        </div>
                      ) : (
                        <span className="text-themed-muted text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {showGenerate && (
        <GenerateModal
          onClose={() => setShowGenerate(false)}
          createReport={createReport}
        />
      )}
    </div>
  );
}

function GenerateModal({
  onClose,
  createReport,
}: {
  onClose: () => void;
  createReport: ReturnType<typeof useCreateReport>;
}) {
  const [type, setType] = useState<'on_demand' | 'weekly' | 'monthly'>(
    'on_demand',
  );
  const [outputLocale, setOutputLocale] = useState<'zh-CN' | 'en-US'>('zh-CN');
  const [fromDate, setFromDate] = useState('2026-04-05');
  const [toDate, setToDate] = useState('2026-05-05');

  const handleSubmit = () => {
    createReport.mutate(
      {
        report_type: type,
        locale: outputLocale,
        from_date: type === 'on_demand' ? fromDate : null,
        to_date: type === 'on_demand' ? toDate : null,
      },
      {
        onSuccess: () => {
          window.setTimeout(onClose, 800);
        },
      },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: 'rgba(3, 2, 41, 0.55)' }}
    >
      <div className="bg-themed-card rounded-card-lg shadow-elevated p-6 w-[480px] max-w-full">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-heading-3 text-themed-primary">生成新报告</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-themed-muted hover:text-themed-primary text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-themed-secondary block mb-1.5">
              类型
            </label>
            <select
              className="t-input w-full"
              value={type}
              onChange={(e) =>
                setType(e.target.value as 'on_demand' | 'weekly' | 'monthly')
              }
            >
              <option value="on_demand">按需报告 (自定义时间窗)</option>
              <option value="weekly">周报</option>
              <option value="monthly">月报</option>
            </select>
          </div>

          {type === 'on_demand' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-themed-secondary block mb-1.5">
                  开始
                </label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="t-input w-full"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-themed-secondary block mb-1.5">
                  结束
                </label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="t-input w-full"
                />
              </div>
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-themed-secondary block mb-1.5">
              输出语言
            </label>
            <select
              className="t-input w-full"
              value={outputLocale}
              onChange={(e) =>
                setOutputLocale(e.target.value as 'zh-CN' | 'en-US')
              }
            >
              <option value="zh-CN">中文 (zh-CN)</option>
              <option value="en-US">English (en-US)</option>
            </select>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <Button
            variant="primary"
            size="md"
            className="flex-1"
            onClick={handleSubmit}
            disabled={createReport.isPending}
          >
            {createReport.isPending ? '生成中…' : '生成'}
          </Button>
          <Button variant="outline" size="md" onClick={onClose}>
            取消
          </Button>
        </div>

        {createReport.isSuccess && (
          <p className="text-[11px] text-themed-accent mt-3 text-center">
            ✓ 报告已生成 (job {createReport.data?.id?.slice(0, 8)})
          </p>
        )}
        {createReport.isError && (
          <p className="text-[11px] text-themed-muted mt-3 text-center">
            生成失败: {createReport.error.message}
          </p>
        )}
      </div>
    </div>
  );
}
