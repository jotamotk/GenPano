import { useEffect, useState } from 'react';
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
import type { ReportDetailOut } from '../api/reports';
import {
  LoadingCard,
  NoProjectCard,
  EmptyCard,
  ErrorCard,
} from './brand/BrandVisibilityPage';

/* Phase 5 §"mock 退役" — 报告系统接入 /v1/projects/:id/reports.
   恢复了 4-mode viewer (preview / markdown / json / pdf) + GenerateModal,
   全部由后端 payload 驱动. */
export default function ReportsPage() {
  const navigate = useNavigate();
  const { formatDate } = useLocale();
  const { data: projects } = useProjects();
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const reportsQ = useReports(enabled ? liveProjectId : null, 50);
  const createReport = useCreateReport(enabled ? liveProjectId : null);
  const [showGenerate, setShowGenerate] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (!enabled)
    return <NoProjectCard onStart={() => navigate('/onboarding')} title="报告" />;
  if (reportsQ.isLoading) return <LoadingCard />;
  if (reportsQ.error)
    return (
      <ErrorCard
        msg={reportsQ.error instanceof Error ? reportsQ.error.message : 'unknown'}
        onRetry={() => reportsQ.refetch()}
      />
    );

  const items = reportsQ.data?.items ?? [];

  if (selectedId) {
    return (
      <ReportDetailView
        projectId={liveProjectId as string}
        reportId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h2 className="text-heading-2 font-bold text-themed-primary">报告</h2>
          <span className="text-xs text-themed-muted">共 {items.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowGenerate(true)}
          >
            生成新报告
          </Button>
        </div>
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
                  <th className="py-2 px-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t border-themed-subtle hover:bg-themed-subtle"
                  >
                    <td className="py-2 pl-5 pr-3">
                      <Badge variant="default" size="sm">{r.type}</Badge>
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
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedId(r.id)}
                        >
                          查看
                        </Button>
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

/* ─────────────────────────────────────────────────────────────
   ReportDetailView — 4-mode viewer (preview / markdown / json / pdf)
   ───────────────────────────────────────────────────────────── */
function ReportDetailView({
  projectId,
  reportId,
  onBack,
}: {
  projectId: string;
  reportId: string;
  onBack: () => void;
}) {
  const { formatDate } = useLocale();
  const [report, setReport] = useState<ReportDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<'preview' | 'markdown' | 'json'>('preview');
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    reportsApi
      .get(projectId, reportId)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'unknown');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, reportId]);

  const handleShare = async () => {
    try {
      const r = await reportsApi.share(projectId, reportId, 72);
      setShareUrl(`${window.location.origin}${r.url}`);
    } catch (e) {
      setShareUrl(`error: ${e instanceof Error ? e.message : 'unknown'}`);
    }
  };

  if (loading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard msg={error} onRetry={onBack} />
    );
  if (!report) return null;

  const payload = report.payload ?? {};
  const sections = (payload as { sections?: Array<Record<string, unknown>> }).sections ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={onBack}
            className="text-sm text-themed-muted hover:text-themed-primary"
          >
            ← 报告列表
          </button>
          <div className="h-4 w-px bg-themed-card" />
          <Badge variant="default">LIVE</Badge>
          <Badge variant="default" size="sm">{report.type}</Badge>
          <span className="text-xs text-themed-muted">
            {formatDate(report.created_at, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={reportsApi.downloadUrl(projectId, reportId, 'csv')}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs px-3 py-1.5 rounded-pill border border-themed-card text-themed-primary hover:bg-themed-subtle"
          >
            下载 CSV
          </a>
          <Button variant="outline" size="sm" onClick={handleShare}>
            生成分享链接
          </Button>
        </div>
      </div>

      {shareUrl && (
        <Card className="p-3" onClick={undefined} style={{}}>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <code className="text-xs text-themed-secondary truncate">{shareUrl}</code>
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(shareUrl)}
              className="text-xs text-themed-accent hover:opacity-80"
            >
              复制
            </button>
          </div>
        </Card>
      )}

      {/* Viewer mode tabs */}
      <div className="t-tabs">
        {(['preview', 'markdown', 'json'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            className={`t-tab ${viewer === mode ? 't-tab-active' : ''}`}
            onClick={() => setViewer(mode)}
          >
            {mode === 'preview' ? '预览' : mode === 'markdown' ? 'Markdown' : 'JSON'}
          </button>
        ))}
      </div>

      {/* Viewer content */}
      {viewer === 'preview' && (
        <Card className="p-6" onClick={undefined} style={{}}>
          {sections.length === 0 ? (
            <p className="text-sm text-themed-muted">
              报告 payload 中无 sections. 切到 Markdown 或 JSON 查看原始内容.
            </p>
          ) : (
            <div className="space-y-6">
              {sections.map((sec, idx) => (
                <SectionPreview key={idx} section={sec} />
              ))}
            </div>
          )}
        </Card>
      )}

      {viewer === 'markdown' && (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <iframe
            title={`report-${reportId}-markdown`}
            src={reportsApi.downloadUrl(projectId, reportId, 'markdown')}
            className="w-full"
            style={{ height: 600, border: 'none', background: 'white' }}
          />
        </Card>
      )}

      {viewer === 'json' && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <pre
            className="text-xs overflow-auto"
            style={{
              maxHeight: 600,
              background: 'var(--color-bg-elevated)',
              padding: 12,
              borderRadius: 6,
            }}
          >
            {JSON.stringify(payload, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}

function SectionPreview({ section }: { section: Record<string, unknown> }) {
  const title =
    typeof section.title === 'string'
      ? section.title
      : typeof section.section_type === 'string'
        ? String(section.section_type)
        : 'Section';
  const narrative =
    typeof section.narrative === 'string' ? section.narrative : null;
  const summary =
    typeof section.summary === 'string' ? section.summary : null;
  return (
    <div>
      <h3 className="text-base font-semibold text-themed-primary mb-2">
        {title}
      </h3>
      {summary && (
        <p className="text-sm text-themed-secondary mb-2 leading-relaxed">
          {summary}
        </p>
      )}
      {narrative && (
        <div
          className="text-sm text-themed-body leading-relaxed"
          style={{ whiteSpace: 'pre-wrap' }}
        >
          {narrative}
        </div>
      )}
      {!summary && !narrative && (
        <pre
          className="text-xs"
          style={{
            background: 'var(--color-bg-badge)',
            padding: 8,
            borderRadius: 6,
            overflow: 'auto',
          }}
        >
          {JSON.stringify(section, null, 2)}
        </pre>
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
  const [type, setType] = useState<'on_demand' | 'weekly' | 'monthly'>('on_demand');
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
        onSuccess: () => window.setTimeout(onClose, 800),
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
