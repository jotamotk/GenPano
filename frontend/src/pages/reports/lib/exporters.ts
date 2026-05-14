import { COMPETITOR_LANCOME, COMPETITOR_SKII, COMPETITOR_LAMER } from './data';
import type { ReportData, ReportSection, TFn, FormatBrandFn, FormatDateRangeFn } from './types';

/* ─────────────────────────────────────────────────────────────
 * 3. 辅助: 等级换算 (PRD 4.6.3 色码 + PANO 评分口径)
 * ─────────────────────────────────────────────────────────── */
export function panoGrade(score: number) {
  if (score >= 90) return 'S';
  if (score >= 80) return 'A';
  if (score >= 70) return 'B';
  if (score >= 60) return 'C';
  return 'D';
}
export function panoGradeToneClass(score: number) {
  if (score >= 80) return 'text-themed-accent';
  if (score >= 70) return 'text-themed-primary';
  return 'text-themed-body';
}
export function deltaToneClass(delta: number) {
  if (delta > 0) return 'text-themed-accent'; // 上升用 accent (品牌色)
  if (delta < 0) return 'text-themed-body';   // 下降保持 body (避免红绿误导)
  return 'text-themed-muted';
}
export function deltaSign(delta: number) {
  if (delta > 0) return '+';
  if (delta < 0) return '';
  return '±';
}

/* ─────────────────────────────────────────────────────────────
 * 4. 生成 Report.executiveSummary 等"LLM 叙述"模拟文案
 *    用 t(...) 的模板 key 渲染, 保证 locale 切换时内容同步切换
 * ─────────────────────────────────────────────────────────── */
export function buildNarratives(
  report: ReportData,
  t: TFn,
  locale: string,
  formatBrand: FormatBrandFn,
  formatDateRange: FormatDateRangeFn,
) {
  const isEn      = locale === 'en-US';
  const period    = formatDateRange(report.periodStart, report.periodEnd);
  const brand     = formatBrand(report.brand);
  const diagHas   = report.diagnostics.p0 > 0 || report.diagnostics.p1 > 0;
  const topDiag   = isEn ? report.diagnostics.topTitleEn : report.diagnostics.topTitleZh;
  const deltaVal  = report.panoScore - report.panoPrev;
  const deltaStr  = deltaVal > 0
    ? t('reports.narratives.executive_delta_up',   { v: deltaVal })
    : deltaVal < 0
      ? t('reports.narratives.executive_delta_down', { v: Math.abs(deltaVal) })
      : t('reports.narratives.executive_delta_flat');
  const diagLine  = diagHas
    ? t('reports.narratives.executive_diag_has',   { p0: report.diagnostics.p0, p1: report.diagnostics.p1 })
    : t('reports.narratives.executive_diag_none',  { p2: report.diagnostics.p2 });
  const competitorsStr = [COMPETITOR_LANCOME, COMPETITOR_SKII, COMPETITOR_LAMER]
    .map(c => formatBrand(c)).join(', ');
  const topProductName = formatBrand(report.topProduct);
  const newCompetitor  = formatBrand(report.newCompetitor);
  const negKeyword     = isEn ? report.engines.negKeywordEn : report.engines.negKeywordZh;
  const topContext     = isEn ? report.topProduct.contextEn : report.topProduct.contextZh;

  return {
    executive_summary: t('reports.narratives.executive_summary', {
      period, brand,
      score: report.panoScore,
      grade: panoGrade(report.panoScore),
      delta: deltaStr,
      sovRank: report.sovRank,
      diagLine,
      topDiagnostic: topDiag,
    }),
    pano_score: t('reports.narratives.pano_score', {
      vDelta: `${deltaSign(report.subdim.V.delta)}${report.subdim.V.delta}`,
      sDelta: `${deltaSign(report.subdim.S.delta)}${report.subdim.S.delta}`,
      rDelta: `${deltaSign(report.subdim.R.delta)}${report.subdim.R.delta}`,
      aDelta: `${deltaSign(report.subdim.A.delta)}${report.subdim.A.delta}`,
      topProduct: topProductName,
    }),
    industry_landscape: t('reports.narratives.industry_landscape', {
      topBrands: competitorsStr,
      newCompetitor,
      newPct: report.newCompetitor.pct,
    }),
    brand_performance: t('reports.narratives.brand_performance', {
      brand,
      topEngine: report.engines.top,
      topRate: report.engines.topRate,
      weakEngine: report.engines.weak,
      weakRate: report.engines.weakRate,
      negKeyword,
    }),
    product_competitiveness: t('reports.narratives.product_competitiveness', {
      topProduct: topProductName,
      topTopic: report.topProduct.topic,
      topRank: report.topProduct.rank,
      context: topContext,
    }),
    competitor_comparison: t('reports.narratives.competitor_comparison', {
      sLead: 3.2,
      vLag: 2.1,
    }),
    diagnostic_summary: t('reports.narratives.diagnostic_summary', {
      total: report.diagnostics.p0 + report.diagnostics.p1 + report.diagnostics.p2 + report.diagnostics.p3,
      p0: report.diagnostics.p0,
      p0New: Math.max(0, report.diagnostics.p0 - 1),
      p1: report.diagnostics.p1,
      p1Imp: Math.floor(report.diagnostics.p1 / 2),
      topDiagnostic: topDiag,
    }),
    // PRD §4.7.2 新增: anchor_actions (operator 读者纯 L3, 锚点问题集)
    anchor_actions: t('reports.narratives.anchor_actions', {
      p0: report.diagnostics.p0,
      p1: report.diagnostics.p1,
    }),
    // PRD §4.7.2 新增: branding_narrative (Branding 读者, 叙事弧线变化)
    branding_narrative: t('reports.narratives.branding_narrative', {
      brand,
      topDiagnostic: topDiag,
    }),
  };
}

/* ─────────────────────────────────────────────────────────────
 * 5. 构造 markdown / json 预览 (PRD 4.7.5 输出格式)
 * ─────────────────────────────────────────────────────────── */
export function buildMarkdown(
  report: ReportData,
  sections: ReportSection[],
  narratives: Record<string, string>,
  t: TFn,
  formatBrand: FormatBrandFn,
  formatDateRange: FormatDateRangeFn,
) {
  const brand = formatBrand(report.brand);
  const period = formatDateRange(report.periodStart, report.periodEnd);
  const lines: string[] = [];
  lines.push(`# ${brand} · ${t(`reports.type_label.${report.type}`)}`);
  lines.push('');
  lines.push(`**${t('reports.kpis.period')}**: ${period}`);
  lines.push(`**${t('reports.kpis.pano_score')}**: ${report.panoScore} (${panoGrade(report.panoScore)}) · Δ ${report.panoScore - report.panoPrev}`);
  lines.push(`**${t('reports.kpis.p0')} / ${t('reports.kpis.p1')}**: ${report.diagnostics.p0} / ${report.diagnostics.p1}`);
  lines.push('');
  sections.forEach((s: ReportSection, idx: number) => {
    lines.push(`## ${idx + 1}. ${t(`reports.sections.${s.type}`)}`);
    lines.push(`> reader: ${s.primaryReader || '—'} · L${(s.insightStackLayers || []).join('/')}`);
    lines.push('');
    lines.push(narratives[s.type] || '');
    lines.push('');
  });
  return lines.join('\n');
}

export function buildJson(
  report: ReportData,
  sections: ReportSection[],
  narratives: Record<string, string>,
  formatBrand: FormatBrandFn,
) {
  return {
    metadata: {
      reportId: report.id,
      type: report.type,
      period: { start: report.periodStart, end: report.periodEnd },
      generatedAt: report.generatedAt,
      brandName: formatBrand(report.brand),
      brandId: report.brand.id,
    },
    scores: {
      brandPano: { current: report.panoScore, previous: report.panoPrev, grade: panoGrade(report.panoScore) },
      subdim: report.subdim,
      industryPano: { sovRank: report.sovRank },
    },
    diagnostics: report.diagnostics,
    sections: sections.map((s: ReportSection, idx: number) => ({
      order: idx + 1,
      type: s.type,
      variant: s.variant,
      primaryReader: s.primaryReader,
      insightStackLayers: s.insightStackLayers,
      narrative: narratives[s.type] || '',
    })),
  };
}
