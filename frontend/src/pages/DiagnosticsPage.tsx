/*
 * DiagnosticsPage — PRD §4.7.0-a / §4.8.2 / §4.8.6 / §4.8.23 (AC-4.8-23)
 * ───────────────────────────────────────────────────
 * 全部诊断的列表视图. 每条诊断使用 <DiagnosticCard /> 渲染,
 * 严格遵守 洞察 Stack (L1 观察 / L2 解释 / L3 方向) × 三读者视角.
 *
 * Filters: severity (P0/P1/P2/P3) + type (brand/product/industry)
 * 不存在 "执行剧本" / "优化步骤" 字段, 任何剧本式建议属付费咨询业务边界 (PRD §4.8.6).
 *
 * Live vs mock semantics (AC-4.8-23, audit #1044 F4-2):
 *   - 真实项目 (liveProjectId 有效): 始终用 live data, 即便为空也渲染显式空态;
 *     绝不静默 fallback 到 mock 数据.
 *   - 无真实项目 (demo / 未登录): 用 mock 数据, 顶部显示 "示例" 徽章.
 */
import { useMemo, useState } from 'react';
import { Badge, Card } from '../components/ui';
import { DiagnosticCard, LeadFormModal } from '../components/diagnostics';
import { DIAGNOSTICS } from '../data/mock';
import { useLocale } from '../contexts/LocaleContext';
import { useProject } from '../contexts/ProjectContext';
import { useProjects } from '../hooks/useProjects';
import { useDiagnostics, toMockShape } from '../hooks/useDiagnostics';
import { isLiveProjectId, resolveLiveProjectId } from '../lib/liveProject';

const SEVERITY_IDS = ['P0', 'P1', 'P2', 'P3'] as const;
const TYPE_IDS = ['brand', 'product', 'industry'] as const;

export default function DiagnosticsPage() {
  const { t } = useLocale();
  const [expandedId, setExpandedId] = useState(null);
  const [filterSev, setFilterSev] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadDiagId, setLeadDiagId] = useState(null);
  const { activeProject } = useProject();

  // Live vs mock — see AC-4.8-23 / audit #1044 F4-2.
  //   • If liveProjectId is a real UUID → always use live data (even when
  //     empty); render distinct loading / error / empty states.
  //   • Else (demo / pre-auth) → mock with explicit "示例" badge.
  const { data: liveProjects } = useProjects();
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject);
  const hasLiveProject = isLiveProjectId(liveProjectId);
  const {
    data: liveDiag,
    isLoading: liveLoading,
    isError: liveError,
  } = useDiagnostics(liveProjectId, { limit: 200 });
  const liveItems = liveDiag?.items ?? [];
  const allItems: any[] = hasLiveProject
    ? liveItems.map(toMockShape)
    : DIAGNOSTICS;

  const openLeadForm = (diagId) => {
    setLeadDiagId(diagId);
    setShowLeadForm(true);
  };

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    SEVERITY_IDS.forEach((id) => {
      c[id] = allItems.filter((d) => d.severity === id).length;
    });
    return c;
  }, [allItems]);

  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    TYPE_IDS.forEach((id) => {
      c[id] = allItems.filter((d) => d.type === id).length;
    });
    return c;
  }, [allItems]);

  const filtered = useMemo(() => {
    return allItems.filter(
      (d) =>
        (filterSev === 'all' || d.severity === filterSev) &&
        (filterType === 'all' || d.type === filterType)
    );
  }, [allItems, filterSev, filterType]);

  const leadDiag = leadDiagId ? allItems.find((d) => d.id === leadDiagId) : null;

  return (
    <div className="space-y-6">
      {!hasLiveProject && (
        <div className="flex items-center gap-2 text-[11px] text-themed-muted">
          <Badge variant="default" size="sm">{t('diagnostics.example_badge')}</Badge>
          <span>{t('diagnostics.example_body')}</span>
        </div>
      )}
      {/* Severity Summary Bar — 2 cols on mobile, 4 on sm+ */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        {SEVERITY_IDS.map((id) => {
          const isActive = filterSev === id;
          const accentColor =
            id === 'P0'
              ? 'var(--color-danger)'
              : id === 'P1'
              ? 'var(--color-warning)'
              : id === 'P2'
              ? 'var(--color-accent)'
              : 'var(--color-border)';
          return (
            <Card
              key={id}
              className={`border-l-4 cursor-pointer transition-all ${
                isActive ? 'ring-2' : 'hover:shadow-md'
              }`}
              style={{
                borderLeftColor: accentColor,
                ...(isActive ? { boxShadow: `0 0 0 2px ${accentColor}` } : {}),
              }}
              onClick={() => setFilterSev(isActive ? 'all' : id)}
            >
              <div className="text-themed-muted text-xs font-medium mb-2">
                {t(`diagnostics.severity.${id}`)}
              </div>
              <div className="text-3xl sm:text-4xl font-bold text-themed-primary tabular-nums">
                {counts[id]}
              </div>
            </Card>
          );
        })}
      </div>

      {/* Type Filter Chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] text-themed-muted mr-1">{t('diagnostics.filter.type_label')}:</span>
        <button
          type="button"
          onClick={() => setFilterType('all')}
          className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
            filterType === 'all'
              ? 'border-themed-strong text-themed-primary bg-themed-badge'
              : 'border-themed-card text-themed-muted hover:text-themed-primary'
          }`}
        >
          {t('diagnostics.filter.all')} ({allItems.length})
        </button>
        {TYPE_IDS.map((id) => {
          const active = filterType === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setFilterType(active ? 'all' : id)}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
                active
                  ? 'border-themed-strong text-themed-primary bg-themed-badge'
                  : 'border-themed-card text-themed-muted hover:text-themed-primary'
              }`}
            >
              {t(`diagnostics.type.${id}`)} ({typeCounts[id] || 0})
            </button>
          );
        })}
        {(filterSev !== 'all' || filterType !== 'all') && (
          <button
            type="button"
            onClick={() => {
              setFilterSev('all');
              setFilterType('all');
            }}
            className="text-[11px] text-themed-accent font-medium hover:opacity-80 ml-auto"
          >
            {t('diagnostics.filter.clear_all')}
          </button>
        )}
      </div>

      {/* Diagnostic Cards. Live-data states (loading / error / empty)
          are surfaced explicitly so a real project never shows mock
          (AC-4.8-23, audit #1044 F4-2). */}
      <div className="space-y-3">
        {hasLiveProject && liveLoading ? (
          <Card>
            <div className="text-center py-8 text-themed-muted text-sm">
              {t('diagnostics.state.loading')}
            </div>
          </Card>
        ) : hasLiveProject && liveError ? (
          <Card>
            <div className="text-center py-8 text-themed-muted text-sm">
              {t('diagnostics.state.error')}
            </div>
          </Card>
        ) : hasLiveProject && allItems.length === 0 ? (
          <Card>
            <div className="text-center py-8 text-themed-muted text-sm">
              {t('diagnostics.state.empty_live')}
            </div>
          </Card>
        ) : filtered.length === 0 ? (
          <Card>
            <div className="text-center py-8 text-themed-muted text-sm">
              {t('diagnostics.state.empty_filtered')}
            </div>
          </Card>
        ) : (
          filtered.map((diag) => (
            <DiagnosticCard
              key={diag.id}
              diag={diag}
              expanded={expandedId === diag.id}
              onToggle={() => setExpandedId(expandedId === diag.id ? null : diag.id)}
              onContactConsultant={openLeadForm}
            />
          ))
        )}
      </div>

      {/* Lead Form Modal */}
      <LeadFormModal
        open={showLeadForm}
        onClose={() => setShowLeadForm(false)}
        diagnostic={leadDiag}
        defaultEmail="frankwangfj@gmail.com"
      />
    </div>
  );
}
