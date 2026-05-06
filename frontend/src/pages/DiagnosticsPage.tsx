/*
 * DiagnosticsPage — PRD §4.7.0-a / §4.8.2 / §4.8.6
 * ───────────────────────────────────────────────────
 * 全部诊断的列表视图. 每条诊断使用 <DiagnosticCard /> 渲染,
 * 严格遵守 洞察 Stack (L1 观察 / L2 解释 / L3 方向) × 三读者视角.
 *
 * Filters: severity (P0/P1/P2/P3) + type (brand/product/industry)
 * 不存在 "执行剧本" / "优化步骤" 字段, 任何剧本式建议属付费咨询业务边界 (PRD §4.8.6).
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card } from '../components/ui';
import { DiagnosticCard, LeadFormModal } from '../components/diagnostics';
import { useProjects } from '../hooks/useProjects';
import { useDiagnostics, toMockShape } from '../hooks/useDiagnostics';
import { isLiveProjectId } from '../hooks/useReports';

const SEVERITY_META = [
  { id: 'P0', label: '紧急', borderClass: 'border-l-red-500', textClass: 'text-themed-danger' },
  { id: 'P1', label: '重要', borderClass: 'border-l-amber-500', textClass: 'text-themed-warning' },
  { id: 'P2', label: '关注', borderClass: '', textClass: 'text-themed-accent' },
  { id: 'P3', label: '信息', borderClass: 'border-l-gray-300', textClass: 'text-themed-muted' },
];

const TYPE_META = [
  { id: 'brand', label: '品牌' },
  { id: 'product', label: '产品' },
  { id: 'industry', label: '行业' },
];

export default function DiagnosticsPage() {
  const navigate = useNavigate();
  const [expandedId, setExpandedId] = useState(null);
  const [filterSev, setFilterSev] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadDiagId, setLeadDiagId] = useState(null);

  // Phase 5 §"mock 退役" — diagnostics 100% from backend.
  const { data: liveProjects, isLoading: projLoading } = useProjects();
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const enabled = isLiveProjectId(liveProjectId);
  const { data: liveDiag, isLoading: diagLoading, refetch } = useDiagnostics(
    enabled ? liveProjectId : null,
    { limit: 200 },
  );
  const allItems: any[] = (liveDiag?.items ?? []).map(toMockShape);

  if (projLoading || (enabled && diagLoading)) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载…</div>
      </Card>
    );
  }

  if (!enabled) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">🩺</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          先创建 Project
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          诊断引擎需要 Project 上下文才能工作.
        </p>
        <Button variant="primary" size="sm" onClick={() => navigate('/onboarding')}>
          开始引导
        </Button>
      </Card>
    );
  }

  if (allItems.length === 0) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">✨</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          暂无诊断
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          诊断引擎在每日 cron 触发. 也可以手动触发刷新.
        </p>
        <Button variant="primary" size="sm" onClick={() => refetch()}>
          刷新
        </Button>
      </Card>
    );
  }

  const openLeadForm = (diagId) => {
    setLeadDiagId(diagId);
    setShowLeadForm(true);
  };

  const counts = useMemo(() => {
    const c = {};
    SEVERITY_META.forEach((s) => {
      c[s.id] = allItems.filter((d) => d.severity === s.id).length;
    });
    return c;
  }, [allItems]);

  const typeCounts = useMemo(() => {
    const c = {};
    TYPE_META.forEach((t) => {
      c[t.id] = allItems.filter((d) => d.type === t.id).length;
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
      {/* Severity Summary Bar */}
      <div className="grid grid-cols-4 gap-4">
        {SEVERITY_META.map((item) => {
          const isActive = filterSev === item.id;
          const accentColor =
            item.id === 'P0'
              ? 'var(--color-danger)'
              : item.id === 'P1'
              ? 'var(--color-warning)'
              : item.id === 'P2'
              ? 'var(--color-accent)'
              : 'var(--color-border)';
          return (
            <Card
              key={item.id}
              className={`border-l-4 cursor-pointer transition-all ${
                isActive ? 'ring-2' : 'hover:shadow-md'
              }`}
              style={{
                borderLeftColor: accentColor,
                ...(isActive ? { boxShadow: `0 0 0 2px ${accentColor}` } : {}),
              }}
              onClick={() => setFilterSev(isActive ? 'all' : item.id)}
            >
              <div className="text-themed-muted text-xs font-medium mb-2">{item.label}</div>
              <div className="text-4xl font-bold text-themed-primary tabular-nums">{counts[item.id]}</div>
            </Card>
          );
        })}
      </div>

      {/* Type Filter Chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] text-themed-muted mr-1">类型:</span>
        <button
          type="button"
          onClick={() => setFilterType('all')}
          className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
            filterType === 'all'
              ? 'border-themed-strong text-themed-primary bg-themed-badge'
              : 'border-themed-card text-themed-muted hover:text-themed-primary'
          }`}
        >
          全部 ({allItems.length})
        </button>
        {TYPE_META.map((t) => {
          const active = filterType === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setFilterType(active ? 'all' : t.id)}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
                active
                  ? 'border-themed-strong text-themed-primary bg-themed-badge'
                  : 'border-themed-card text-themed-muted hover:text-themed-primary'
              }`}
            >
              {t.label} ({typeCounts[t.id] || 0})
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
            清除全部筛选 ×
          </button>
        )}
      </div>

      {/* Diagnostic Cards */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <Card>
            <div className="text-center py-8 text-themed-muted text-sm">当前筛选条件下无诊断</div>
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
