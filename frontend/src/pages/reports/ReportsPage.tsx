/*
 * ReportsPage — PRD 4.7 报告系统
 * ─────────────────────────────────────────────────────────────────
 * 本页是"面板 / 品牌 / 产品"三视角之外的**运营域**页面, 位置:
 *   侧栏分组「运营」→ 报告  (DashboardLayout.jsx navGroups[2])
 *
 * 覆盖 PRD 4.7 的全部内容:
 *   • 4.7.0 报告类型总览     (4 种: weekly / monthly / on_demand / lead_diagnostic)
 *   • 4.7.2 报告内容模板     (8 种 ReportSectionType, 按 type × section 矩阵)
 *   • 4.7.3 报告生成逻辑     (5 步 Pipeline, LLM 叙述 + 数据聚合 + 诊断关联)
 *   • 4.7.5 输出格式         (Markdown / JSON / PDF 三视图切换)
 *   • 4.7.6 商业衔接         (线索诊断报告强化版 CTA)
 *
 * 覆盖 PRD 4.10 国际化:
 *   • UI 文案通过 useLocale().t(...) 驱动
 *   • 品牌名按 locale 显示 (formatBrand: nameZh vs nameEn)
 *   • 日期/数字用 Intl.* 按 locale 格式化
 *   • 报告 generate modal 提供"输出语言"下拉 (对应 User.locale → LLM 注入)
 *   • Executive Summary / LLM 叙述按 locale 生成两份 Mock 文案
 *
 * 覆盖 PRD 4.6.1 层级调整:
 *   • 顶部面包屑标注位置 (侧栏分组/运营/报告)
 *   • Tab 结构不再用"按年份过滤", 改为 4 种报告类型 + 全部, 与 ReportType 枚举一致
 *
 * 样式契约:
 *   • 所有颜色走 .text-themed-* / .bg-themed-* / var(--color-*), 禁止 inline hex
 *   • 组件复用 Badge / Button / Card / Tabs, 不重复造轮子
 */
import { useMemo, useState } from 'react';
import { Badge, Button, Card, Tabs } from '../../components/ui';
import ReportsLiveBanner from '../../components/reports/ReportsLiveBanner';
import { useLocale } from '../../contexts/LocaleContext';
import { useProjects } from '../../hooks/useProjects';
import { isLiveProjectId } from '../../hooks/useReports';
import { GenerateModal } from './components/GenerateModal';
import { LiveReportDetail } from './components/LiveReportDetail';
import { ReportDetail } from './components/ReportDetail';
import { REPORTS, SECTION_MATRIX, SECTION_ORDER } from './lib/data';
import { deltaSign, deltaToneClass, panoGrade, panoGradeToneClass } from './lib/exporters';

/* ─────────────────────────────────────────────────────────────
 * 9. Report List View + Page shell
 * ─────────────────────────────────────────────────────────── */
export default function ReportsPage() {
  const { t, locale, formatDate, formatBrand, formatNumber, formatDateRange } = useLocale();
  const [activeTab, setActiveTab] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [selectedLiveId, setSelectedLiveId] = useState<string | null>(null);
  const [showGenerate, setShowGenerate] = useState(false);
  const { data: liveProjects } = useProjects();
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const showSampleBadge = !isLiveProjectId(liveProjectId);

  const tabs = [
    { id: 'all',             label: t('reports.tabs.all') },
    { id: 'weekly',          label: t('reports.tabs.weekly') },
    { id: 'monthly',         label: t('reports.tabs.monthly') },
    { id: 'on_demand',       label: t('reports.tabs.on_demand') },
    { id: 'lead_diagnostic', label: t('reports.tabs.lead_diagnostic') },
  ];

  const typeVariant: Record<string, string> = {
    weekly:          'default',
    monthly:         'purple',
    on_demand:       'blue',
    lead_diagnostic: 'orange',
  };

  const filtered = useMemo(
    () => (activeTab === 'all' ? REPORTS : REPORTS.filter((r) => r.type === activeTab)),
    [activeTab]
  );

  if (selectedLiveId && isLiveProjectId(liveProjectId)) {
    return (
      <LiveReportDetail
        projectId={liveProjectId as string}
        reportId={selectedLiveId}
        onBack={() => setSelectedLiveId(null)}
      />
    );
  }

  if (selectedId) {
    const report = REPORTS.find((r) => r.id === selectedId);
    if (!report) return null;
    return <ReportDetail report={report} onBack={() => setSelectedId(null)} />;
  }

  return (
    <div className="space-y-6">
      {/* Page header: title + subtitle + location disclosure */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-heading-1 text-themed-primary">{t('reports.page_title')}</h1>
          <p className="text-sm text-themed-muted mt-1 max-w-3xl">
            {t('reports.page_subtitle')}
          </p>
          {/* PRD §4.6.0a — `reports.hierarchy_note` removed: sidebar nav highlight conveys
              the page's location; explanatory copy was developer-facing scope leak. */}
        </div>
        <Button variant="primary" size="md" onClick={() => setShowGenerate(true)}>
          {t('reports.actions.generate')}
        </Button>
      </div>

      {/* Live banner — real backend reports (Phase RP). Renders null
          when there's no live project, so demo sessions are unaffected.
          Clicking 查看 opens LiveReportDetail (audit #1044 F4-3). */}
      <ReportsLiveBanner onSelect={setSelectedLiveId} />

      {/* Tabs */}
      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {showSampleBadge && (
        <div className="flex items-center gap-2 text-[11px] text-themed-muted">
          <Badge variant="default" size="sm">示例</Badge>
          <span>
            以下为示例报告。创建项目并生成真实报告后,可在上方 LIVE 区查看。
          </span>
        </div>
      )}

      {/* Schedule / delivery strip */}
      <Card
        className="p-4 flex items-center justify-between flex-wrap gap-3"
        style={{ background: 'var(--color-accent-bg-light)' }}
      >
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-themed-gradient-accent" />
            <span className="text-xs text-themed-body">{t('reports.schedule.weekly')}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-themed-gradient-accent" />
            <span className="text-xs text-themed-body">{t('reports.schedule.monthly')}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-themed-muted">
              {t('reports.schedule.delivery', { email: 'frankwangfj@gmail.com' })}
            </span>
          </div>
        </div>
        <button className="text-xs font-medium text-themed-accent hover:opacity-80">
          {t('reports.schedule.settings')} →
        </button>
      </Card>

      {/* Report rows */}
      <div className="grid grid-cols-1 gap-4">
        {filtered.map((report) => {
          const brandName = formatBrand(report.brand);
          const panoDelta = report.panoScore - report.panoPrev;
          // lead_diagnostic 走 4 层独立视图, 列表上以 4 表示 (Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators)
          const sections = report.type === 'lead_diagnostic'
            ? [1, 2, 3, 4]
            : SECTION_ORDER.filter((type) => (SECTION_MATRIX as Record<string, Record<string, any>>)[report.type][type]);

          return (
            <Card
              key={report.id}
              className="p-5 cursor-pointer"
              onClick={() => setSelectedId(report.id)}
            >
              <div className="flex items-center justify-between gap-4">
                {/* Left: meta + highlight */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center flex-wrap gap-2.5 mb-2">
                    <Badge variant={typeVariant[report.type]}>
                      {t(`reports.type_label.${report.type}`)}
                    </Badge>
                    <span className="text-sm font-medium text-themed-primary">
                      {brandName}
                    </span>
                    <span className="text-themed-faint">·</span>
                    <span className="text-sm text-themed-muted">
                      {formatDateRange(report.periodStart, report.periodEnd)}
                    </span>
                    {report.diagnostics.p0 > 0 && (
                      <Badge variant="red" size="sm">
                        {t('reports.card.p0_badge', { count: report.diagnostics.p0 })}
                      </Badge>
                    )}
                    {report.diagnostics.p1 > 0 && (
                      <Badge variant="orange" size="sm">
                        {t('reports.card.p1_badge', { count: report.diagnostics.p1 })}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-themed-body leading-relaxed">
                    {locale === 'en-US' ? report.diagnostics.topTitleEn : report.diagnostics.topTitleZh}
                  </p>
                  <p className="text-[11px] text-themed-faint mt-1.5">
                    {t('reports.card.meta', {
                      words: formatNumber(report.wordCount),
                      sections: sections.length,
                      time: formatDate(report.generatedAt, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
                    })}
                  </p>
                </div>

                {/* Right: pano + actions */}
                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-right">
                    <p className={`text-heading-2 tabular-nums ${panoGradeToneClass(report.panoScore)}`}>
                      {report.panoScore}
                    </p>
                    <p className={`text-[11px] tabular-nums ${deltaToneClass(panoDelta)}`}>
                      {deltaSign(panoDelta)}{panoDelta} · {panoGrade(report.panoScore)}
                    </p>
                    <p className="text-[10px] text-themed-faint uppercase tracking-wider">
                      {t('reports.card.pano_short')}
                    </p>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); setSelectedId(report.id); }}
                    >
                      {t('reports.actions.view')}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      PDF
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {showGenerate && <GenerateModal onClose={() => setShowGenerate(false)} />}
    </div>
  );
}
