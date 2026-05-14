import { useMemo, useState } from 'react';
import { Badge, Button, Card } from '../../../components/ui';
import { useLocale } from '../../../contexts/LocaleContext';
import { COMPETITOR_LAMER, COMPETITOR_LANCOME, COMPETITOR_SKII, SECTION_MATRIX, SECTION_ORDER } from '../lib/data';
import {
  buildJson,
  buildMarkdown,
  buildNarratives,
  deltaSign,
  deltaToneClass,
  panoGrade,
  panoGradeToneClass,
} from '../lib/exporters';
import type { ReportData } from '../lib/types';
import { DataRow } from './DataRow';
import { LeadDiagnosticView } from './LeadDiagnosticView';
import { ReaderBadge } from './ReaderBadge';
import { SectionShell } from './SectionShell';
import { StackLayerBadges } from './StackLayerBadges';

/* ─────────────────────────────────────────────────────────────
 * 7. Report Detail View
 * ─────────────────────────────────────────────────────────── */
export function ReportDetail({ report, onBack }: { report: ReportData; onBack: () => void }) {
  const { t, locale, formatDate, formatDateRange, formatBrand, formatNumber } = useLocale();
  const [viewer, setViewer] = useState('preview');

  const narrativesResolved: Record<string, string> = useMemo(
    () => buildNarratives(report, t, locale, formatBrand, formatDateRange),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report, locale]
  );

  const matrixForType = (SECTION_MATRIX as Record<string, Record<string, any>>)[report.type];
  const sections = SECTION_ORDER
    .filter((type) => matrixForType && matrixForType[type])
    .map((type) => {
      const cell = matrixForType[type];
      return {
        type,
        variant: cell.variant,
        primaryReader: cell.primaryReader,
        insightStackLayers: cell.insightStackLayers || [],
      };
    });

  const markdown = useMemo(
    () => buildMarkdown(report, sections, narrativesResolved, t, formatBrand, formatDateRange),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report, locale, sections]
  );
  const jsonOutput = useMemo(
    () => buildJson(report, sections, narrativesResolved, formatBrand),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report, locale, sections]
  );

  const panoDelta = report.panoScore - report.panoPrev;
  const brandName = formatBrand(report.brand);
  const isLead = report.type === 'lead_diagnostic';

  /* ── Section bodies (mini-visuals) ── */
  const sectionBodies: Record<string, JSX.Element> = {
    executive_summary: (
      <div className="grid grid-cols-3 gap-3">
        <DataRow label={t('reports.kpis.pano_score')} value={report.panoScore} delta={panoDelta} />
        <DataRow label="SoV Rank" value={`#${report.sovRank}`} delta={report.prevSovRank - report.sovRank} />
        <DataRow label="P0 / P1" value={`${report.diagnostics.p0} / ${report.diagnostics.p1}`} />
      </div>
    ),
    pano_score: (
      <div className="grid grid-cols-4 gap-3">
        {['V', 'S', 'R', 'A'].map((k) => (
          <div key={k} className="bg-themed-subtle rounded-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-themed-muted">{k}</p>
            <p className="text-data-lg text-themed-primary tabular-nums">{report.subdim[k].current}</p>
            <p className={`text-[11px] tabular-nums ${deltaToneClass(report.subdim[k].delta)}`}>
              {deltaSign(report.subdim[k].delta)}{report.subdim[k].delta}
            </p>
          </div>
        ))}
      </div>
    ),
    industry_landscape: (
      <div className="space-y-2">
        <DataRow label={`SoV Rank · ${brandName}`} value={`#${report.sovRank}`} delta={report.prevSovRank - report.sovRank} />
        <DataRow label={`New entrant · ${formatBrand(report.newCompetitor)}`} value={`+${report.newCompetitor.pct}%`} />
        <DataRow label={`Top 3 ${locale === 'en-US' ? 'competitors' : '竞品'}`} value={[COMPETITOR_LANCOME, COMPETITOR_SKII, COMPETITOR_LAMER].map(c => formatBrand(c)).join(' · ')} />
      </div>
    ),
    brand_performance: (
      <div className="space-y-2">
        <DataRow label={`${report.engines.top} · mention rate`} value={`${report.engines.topRate}%`} />
        <DataRow label={`${report.engines.weak} · mention rate`} value={`${report.engines.weakRate}%`} />
        <DataRow
          label={locale === 'en-US' ? 'Negative keyword cluster' : '负面关键词簇'}
          value={locale === 'en-US' ? report.engines.negKeywordEn : report.engines.negKeywordZh}
        />
      </div>
    ),
    product_competitiveness: (
      <div className="space-y-2">
        <DataRow label={`Top product · ${formatBrand(report.topProduct)}`} value={`#${report.topProduct.rank}`} />
        <DataRow
          label={locale === 'en-US' ? 'Top topic' : '核心 Topic'}
          value={report.topProduct.topic}
        />
        <DataRow
          label={locale === 'en-US' ? 'Recommendation context' : '推荐语境'}
          value={locale === 'en-US' ? report.topProduct.contextEn : report.topProduct.contextZh}
        />
      </div>
    ),
    competitor_comparison: (
      <div className="grid grid-cols-3 gap-3">
        {[COMPETITOR_LANCOME, COMPETITOR_SKII, COMPETITOR_LAMER].map((c, i) => (
          <div key={i} className="bg-themed-subtle rounded-card p-3">
            <p className="text-xs font-medium text-themed-primary">{formatBrand(c)}</p>
            <p className="text-[11px] text-themed-muted mt-0.5">PANO {80 - i * 2}</p>
            <p className={`text-[11px] tabular-nums mt-1 ${deltaToneClass(i === 0 ? +2 : -1)}`}>
              {i === 0 ? '+2' : '-1'} vs. prev
            </p>
          </div>
        ))}
      </div>
    ),
    diagnostic_summary: (
      <div className="grid grid-cols-4 gap-3">
        {[
          { k: 'P0', v: report.diagnostics.p0, tone: 'danger' },
          { k: 'P1', v: report.diagnostics.p1, tone: 'warning' },
          { k: 'P2', v: report.diagnostics.p2, tone: 'info' },
          { k: 'P3', v: report.diagnostics.p3, tone: 'default' },
        ].map((d) => (
          <div key={d.k} className="bg-themed-subtle rounded-card p-3 text-center">
            <p className="text-[10px] uppercase tracking-wider text-themed-muted">{d.k}</p>
            <p className="text-data-lg tabular-nums text-themed-primary">{d.v}</p>
            <Badge variant={d.tone} size="xs" className="mt-1">{d.k}</Badge>
          </div>
        ))}
      </div>
    ),
    cta: (
      <div className="space-y-3">
        <p className="text-sm text-themed-body leading-relaxed">
          {t('reports.cta.dynamic', {
            engine: report.engines.weak,
            pct: Math.round(((report.engines.topRate - report.engines.weakRate) / report.engines.topRate) * 100),
          })}
        </p>
      </div>
    ),
    /* PRD §4.7.2 新增: anchor_actions — 纯 L3, 锚点问题 + 焦点区, 不是执行剧本 */
    anchor_actions: (
      <div className="space-y-3">
        <div className="rounded-card border border-themed-card p-3" style={{ background: 'rgba(10,187,135,0.04)' }}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold rounded px-1.5 py-0.5" style={{ background: 'rgba(10,187,135,0.12)', color: 'var(--color-success-text)' }}>
              L3
            </span>
            <span className="text-[11px] font-semibold text-themed-primary">
              {t('reports.bodies.anchor_actions.focus_label')}
            </span>
          </div>
          <ol className="space-y-1.5">
            {[
              t('reports.bodies.anchor_actions.q1', { engine: report.engines.weak }),
              t('reports.bodies.anchor_actions.q2'),
              t('reports.bodies.anchor_actions.q3', { negKeyword: locale === 'en-US' ? report.engines.negKeywordEn : report.engines.negKeywordZh }),
              t('reports.bodies.anchor_actions.q4'),
            ].map((q, i) => (
              <li key={i} className="flex gap-2">
                <span
                  className="shrink-0 inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold mt-0.5"
                  style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
                >
                  {i + 1}
                </span>
                <p className="text-[12px] text-themed-secondary leading-relaxed">{q}</p>
              </li>
            ))}
          </ol>
        </div>
        <p className="text-[11px] text-themed-muted italic">
          {t('reports.bodies.anchor_actions.disclaimer')}
        </p>
      </div>
    ),
    /* PRD §4.7.2 新增: branding_narrative — Branding 读者主章节, 叙事弧线 */
    branding_narrative: (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-card p-3 bg-themed-subtle border border-themed-card">
            <div className="text-[10px] uppercase tracking-wider text-themed-muted mb-1">
              {t('reports.bodies.branding_narrative.before_label')}
            </div>
            <div className="text-xs font-medium text-themed-primary mb-1">
              {t('reports.bodies.branding_narrative.before_persona')}
            </div>
            <div className="text-[11px] text-themed-secondary">
              {t('reports.bodies.branding_narrative.before_keywords')}
            </div>
          </div>
          <div className="rounded-card p-3 border" style={{ background: 'rgba(245,166,35,0.06)', borderColor: 'var(--color-warning)' }}>
            <div className="text-[10px] uppercase tracking-wider text-themed-warning mb-1">
              {t('reports.bodies.branding_narrative.after_label')}
            </div>
            <div className="text-xs font-medium text-themed-primary mb-1">
              {t('reports.bodies.branding_narrative.after_persona')}
            </div>
            <div className="text-[11px] text-themed-secondary">
              {t('reports.bodies.branding_narrative.after_keywords')}
            </div>
          </div>
        </div>
        <div className="rounded-card border border-themed-card p-3">
          <div className="text-[11px] font-semibold text-themed-primary mb-1.5">
            {t('reports.bodies.branding_narrative.competitor_label')}
          </div>
          <div className="text-[12px] text-themed-secondary leading-relaxed">
            {t('reports.bodies.branding_narrative.competitor_desc', { brand: formatBrand(COMPETITOR_LANCOME) })}
          </div>
        </div>
      </div>
    ),
  };

  return (
    <div className="space-y-6">
      {/* Breadcrumb / back */}
      <button
        className="text-xs font-medium text-themed-accent hover:opacity-80 transition-opacity"
        onClick={onBack}
      >
        {t('reports.actions.back')}
      </button>

      {/* ═════════ Header card: meta + format actions ═════════ */}
      <Card className="p-6">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="accent">{t(`reports.type_label.${report.type}`)}</Badge>
              <span className="text-[11px] text-themed-faint">
                {t('common.generatedAt', { time: formatDate(report.generatedAt, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) })}
              </span>
              {isLead && <Badge variant="orange" size="sm">{t('reports.sections.variant.strengthened')}</Badge>}
            </div>
            <h2 className="text-heading-2 text-themed-primary">
              {brandName} · {t(`reports.type_label.${report.type}`)}
            </h2>
            <p className="text-sm text-themed-muted mt-1.5">
              {formatDateRange(report.periodStart, report.periodEnd)}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button variant="primary" size="sm">{t('reports.actions.download_pdf')}</Button>
            <Button variant="secondary" size="sm">{t('reports.actions.view_markdown')}</Button>
            <Button variant="secondary" size="sm">{t('reports.actions.view_json')}</Button>
          </div>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-5 gap-4 mt-6 pt-6 border-t border-themed-subtle">
          <div>
            <p className="text-xs text-themed-muted mb-1">{t('reports.kpis.pano_score')}</p>
            <p className={`text-data-lg font-bold tabular-nums ${panoGradeToneClass(report.panoScore)}`}>
              {report.panoScore}
              <span className="text-xs text-themed-faint font-normal ml-1.5">
                ({panoGrade(report.panoScore)})
              </span>
            </p>
            <p className={`text-xs tabular-nums mt-0.5 ${deltaToneClass(panoDelta)}`}>
              {deltaSign(panoDelta)}{panoDelta} · {t('reports.kpis.pano_delta')}
            </p>
          </div>
          <div>
            <p className="text-xs text-themed-muted mb-1">{t('reports.kpis.p0')}</p>
            <p className="text-data-lg font-bold tabular-nums text-themed-primary">
              {report.diagnostics.p0}
            </p>
          </div>
          <div>
            <p className="text-xs text-themed-muted mb-1">{t('reports.kpis.p1')}</p>
            <p className="text-data-lg font-bold tabular-nums text-themed-primary">
              {report.diagnostics.p1}
            </p>
          </div>
          <div>
            <p className="text-xs text-themed-muted mb-1">{t('reports.kpis.length')}</p>
            <p className="text-data-lg font-bold tabular-nums text-themed-primary">
              {formatNumber(report.wordCount)}
            </p>
            <p className="text-[11px] text-themed-faint mt-0.5">{t('common.chars')}</p>
          </div>
          <div>
            <p className="text-xs text-themed-muted mb-1">{t('reports.kpis.language')}</p>
            <p className="text-data-lg font-bold tabular-nums text-themed-primary">
              {locale === 'zh-CN' ? '中文' : 'EN'}
            </p>
            <p className="text-[11px] text-themed-faint mt-0.5">
              {locale === 'zh-CN' ? 'zh-CN' : 'en-US'}
            </p>
          </div>
        </div>

        {/* PRD §4.6.0a — sidebar location disclosure removed; sidebar nav highlight already
            tells the user where they are. No need for explanatory copy here. */}
      </Card>

      {/* ═════════ Viewer mode tabs ═════════ */}
      <div className="flex items-center gap-2">
        {['preview', 'markdown', 'json', 'pdf'].map((mode) => (
          <button
            key={mode}
            onClick={() => setViewer(mode)}
            className={`px-3 py-1.5 text-xs font-medium rounded-btn transition-colors ${
              viewer === mode
                ? 'bg-themed-gradient-accent text-themed-inverse'
                : 'bg-themed-subtle text-themed-muted hover:text-themed-primary'
            }`}
          >
            {t(`reports.viewer.tab_${mode}`)}
          </button>
        ))}
      </div>

      {/* ═════════ Viewer body ═════════ */}
      {viewer === 'preview' && isLead && (
        <LeadDiagnosticView
          report={report}
          brandName={brandName}
          t={t}
          onContactConsultant={() => {
            // 占位: 未来打开 LeadFormModal
            window.alert(t('reports.cta.lead_button'));
          }}
        />
      )}

      {viewer === 'preview' && !isLead && (
        <>
          {/* Section matrix pill legend */}
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-themed-primary mb-3">
              {t('reports.sections.heading', { count: sections.length })}
            </h3>
            <div className="flex flex-wrap gap-2">
              {sections.map((s, idx) => (
                <span
                  key={s.type}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-themed-subtle text-[11px] text-themed-body"
                >
                  <span className="w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold text-themed-inverse bg-themed-gradient-accent">
                    {idx + 1}
                  </span>
                  <span>{t(`reports.sections.${s.type}`)}</span>
                  <span className="text-themed-muted">·</span>
                  <ReaderBadge reader={s.primaryReader} t={t} />
                  <StackLayerBadges layers={s.insightStackLayers} />
                </span>
              ))}
            </div>
          </Card>

          {/* Render each applicable section */}
          {sections.map((s, idx) => (
            <SectionShell
              key={s.type}
              order={idx + 1}
              title={t(`reports.sections.${s.type}`)}
              variantLabel={t(`reports.sections.variant.${s.variant}`)}
              narrative={s.type === 'cta' ? null : narrativesResolved[s.type]}
              emphasized={false}
              primaryReader={s.primaryReader}
              insightStackLayers={s.insightStackLayers}
              t={t}
            >
              {sectionBodies[s.type]}
            </SectionShell>
          ))}
        </>
      )}

      {viewer === 'markdown' && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-themed-muted">report.md</span>
            <Button variant="secondary" size="sm">{t('reports.viewer.copy')}</Button>
          </div>
          <pre className="text-xs font-mono bg-themed-subtle p-4 rounded-card overflow-auto text-themed-body whitespace-pre-wrap leading-relaxed max-h-[640px]">
{markdown}
          </pre>
        </Card>
      )}

      {viewer === 'json' && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-themed-muted">report.json</span>
            <Button variant="secondary" size="sm">{t('reports.viewer.copy')}</Button>
          </div>
          <pre className="text-xs font-mono bg-themed-subtle p-4 rounded-card overflow-auto text-themed-body max-h-[640px]">
{JSON.stringify(jsonOutput, null, 2)}
          </pre>
        </Card>
      )}

      {viewer === 'pdf' && (
        <Card className="p-12 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-card-lg bg-themed-accent-soft mb-4">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-themed-accent">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <path d="M14 2v6h6" />
            </svg>
          </div>
          <p className="text-sm text-themed-body mb-4 max-w-md mx-auto">
            {t('reports.viewer.pdf_placeholder')}
          </p>
          <Button variant="primary" size="md">{t('reports.actions.download_pdf')}</Button>
        </Card>
      )}

      {/* ═════════ CTA (PRD 4.7.6 角色 2: 线索转化) ═════════ */}
      {isLead ? (
        <Card
          className="p-6"
          style={{ background: 'var(--color-accent-subtle)', border: '1px solid var(--color-accent)' }}
        >
          <div className="flex items-center justify-between gap-6">
            <div>
              <h3 className="text-heading-3 text-themed-accent mb-1.5">{t('reports.cta.lead_title')}</h3>
              <p className="text-sm text-themed-body">
                {t('reports.cta.lead_subtitle', {
                  p0Count: report.diagnostics.p0,
                  p1Count: report.diagnostics.p1,
                })}
              </p>
            </div>
            <Button variant="accent" size="lg">{t('reports.cta.lead_button')}</Button>
          </div>
        </Card>
      ) : (
        <Card className="p-6">
          <div className="flex items-center justify-between gap-6">
            <div>
              <h3 className="text-sm font-semibold text-themed-accent">{t('reports.cta.title')}</h3>
              <p className="text-xs text-themed-muted mt-1">{t('reports.cta.subtitle')}</p>
            </div>
            <Button variant="accent" size="md">{t('reports.cta.button')}</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
