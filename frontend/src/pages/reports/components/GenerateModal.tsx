import { useState } from 'react';
import { Button } from '../../../components/ui';
import { useLocale } from '../../../contexts/LocaleContext';
import { useProjects } from '../../../hooks/useProjects';
import { isLiveProjectId, useCreateReport } from '../../../hooks/useReports';

/* ─────────────────────────────────────────────────────────────
 * 8. Generate Modal
 * ─────────────────────────────────────────────────────────── */
export function GenerateModal({ onClose }: { onClose: () => void }) {
  const { t, locale } = useLocale();
  const [type, setType] = useState('on_demand');
  const [outputLocale, setOutputLocale] = useState(locale);
  const [fromDate, setFromDate] = useState('2026-04-05');
  const [toDate, setToDate] = useState('2026-05-05');

  // Live wiring: when the user has a real backend project, the submit
  // button POSTs to /v1/projects/:id/reports and renders job state.
  const { data: liveProjects } = useProjects();
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null;
  const liveCanGenerate = isLiveProjectId(liveProjectId);
  const createReport = useCreateReport(liveProjectId);

  const handleSubmit = () => {
    if (!liveCanGenerate) {
      onClose();
      return;
    }
    createReport.mutate(
      {
        report_type: type as 'weekly' | 'monthly' | 'on_demand',
        locale: outputLocale as 'zh-CN' | 'en-US',
        from_date: type === 'on_demand' ? fromDate : null,
        to_date: type === 'on_demand' ? toDate : null,
      },
      {
        onSuccess: () => {
          window.setTimeout(onClose, 1200);
        },
      },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: 'rgba(3, 2, 41, 0.55)' }}
    >
      <div className="bg-themed-card rounded-card-lg shadow-elevated p-6 w-[520px] max-w-full">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-heading-3 text-themed-primary">{t('reports.generate_modal.title')}</h3>
          <button onClick={onClose} className="text-themed-muted hover:text-themed-primary text-xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-themed-secondary block mb-1.5">
              {t('reports.generate_modal.type_label')}
            </label>
            <select
              className="t-input w-full"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="on_demand">{t('reports.generate_modal.type_on_demand')}</option>
              <option value="weekly">{t('reports.generate_modal.type_weekly')}</option>
              <option value="monthly">{t('reports.generate_modal.type_monthly')}</option>
            </select>
            <p className="text-[11px] text-themed-muted mt-1.5">
              {t(`reports.definitions.${type}`)}
            </p>
          </div>

          {type === 'on_demand' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-themed-secondary block mb-1.5">
                  {t('reports.generate_modal.start')}
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
                  {t('reports.generate_modal.end')}
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
              {t('reports.generate_modal.language')}
            </label>
            <select
              className="t-input w-full"
              value={outputLocale}
              onChange={(e) => setOutputLocale(e.target.value)}
            >
              <option value="zh-CN">中文 (zh-CN)</option>
              <option value="en-US">English (en-US)</option>
            </select>
          </div>

          <div>
            <p className="text-xs font-medium text-themed-secondary mb-1.5">
              {t('reports.generate_modal.format')}
            </p>
            <div className="flex gap-4">
              <label className="inline-flex items-center gap-1.5 text-sm text-themed-body">
                <input type="checkbox" defaultChecked /> Markdown
              </label>
              <label className="inline-flex items-center gap-1.5 text-sm text-themed-body">
                <input type="checkbox" defaultChecked /> PDF
              </label>
              <label className="inline-flex items-center gap-1.5 text-sm text-themed-body">
                <input type="checkbox" /> JSON
              </label>
            </div>
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
            {createReport.isPending
              ? '生成中…'
              : liveCanGenerate
              ? '生成真实报告'
              : t('reports.generate_modal.submit')}
          </Button>
          <Button variant="outline" size="md" onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
        {liveCanGenerate && createReport.isSuccess && (
          <p className="text-[11px] text-themed-accent mt-3 text-center">
            报告已生成 (job {createReport.data?.id?.slice(0, 8)}) — 见上方 LIVE 列表
          </p>
        )}
        {liveCanGenerate && createReport.isError && (
          <p className="text-[11px] text-themed-muted mt-3 text-center">
            生成失败：{createReport.error.message}
          </p>
        )}
        {!liveCanGenerate && (
          <p
            className="text-[11px] text-themed-faint mt-3 text-center"
            dangerouslySetInnerHTML={{ __html: t('reports.generate_modal.eta') }}
          />
        )}
      </div>
    </div>
  );
}
