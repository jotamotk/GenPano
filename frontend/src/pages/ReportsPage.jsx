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
import { Badge, Button, Card, Tabs } from '../components/ui';
import { useLocale } from '../contexts/LocaleContext';
import { DIAGNOSTICS } from '../data/mock';

/* ─────────────────────────────────────────────────────────────
 * 1. 报告类型 × Section 矩阵 (PRD 4.7.2 + 2026-04-16 升级)
 *
 *   每格的值是对象 (null 表示不含此章节, PRD 矩阵中的 ❌):
 *     • variant            — 'full' / 'simple' / 'focus' / 'optional' / 'p01_only' / 'all' / 'top3' / 'strengthened' / 'all_highlight'
 *     • primaryReader      — 'operator' / 'manager' / 'branding' (PRD §4.7.0-a 三读者视角)
 *     • insightStackLayers — [1,2,3] 子集 (L1 观察 / L2 解释 / L3 方向)
 *
 *   两个新 Section 类型 (PRD §4.7.2 2026-04-16):
 *     • branding_narrative — Branding 读者主章节 (monthly / lead_diagnostic 必带)
 *     • anchor_actions     — Operator 读者纯 L3 锚点问题集 (代替旧的"建议"剧本)
 *
 *   ⚠️ lead_diagnostic 走独立 4 层渲染 (PRD §4.7.4a):
 *      Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators
 *      — 不再使用本矩阵, 见 LeadDiagnosticView
 * ─────────────────────────────────────────────────────────── */
const SECTION_MATRIX = {
  weekly: {
    executive_summary:       { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    pano_score:              { variant: 'simple',   primaryReader: 'operator', insightStackLayers: [1] },
    industry_landscape:      { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    brand_performance:       { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2] },
    product_competitiveness: null,
    competitor_comparison:   { variant: 'simple',   primaryReader: 'manager',  insightStackLayers: [1, 2] },
    diagnostic_summary:      { variant: 'p01_only', primaryReader: 'operator', insightStackLayers: [1, 2, 3] },
    anchor_actions:          { variant: 'p01_only', primaryReader: 'operator', insightStackLayers: [3] },
    branding_narrative:      null,
    cta:                     { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [3] },
  },
  monthly: {
    executive_summary:       { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    pano_score:              { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2] },
    industry_landscape:      { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    brand_performance:       { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2, 3] },
    product_competitiveness: { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2] },
    competitor_comparison:   { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    diagnostic_summary:      { variant: 'all',      primaryReader: 'operator', insightStackLayers: [1, 2, 3] },
    anchor_actions:          { variant: 'all',      primaryReader: 'operator', insightStackLayers: [3] },
    branding_narrative:      { variant: 'full',     primaryReader: 'branding', insightStackLayers: [2, 3] },
    cta:                     { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [3] },
  },
  on_demand: {
    executive_summary:       { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    pano_score:              { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2] },
    industry_landscape:      { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    brand_performance:       { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2, 3] },
    product_competitiveness: { variant: 'optional', primaryReader: 'operator', insightStackLayers: [1, 2] },
    competitor_comparison:   { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [1, 2] },
    diagnostic_summary:      { variant: 'full',     primaryReader: 'operator', insightStackLayers: [1, 2, 3] },
    anchor_actions:          { variant: 'full',     primaryReader: 'operator', insightStackLayers: [3] },
    branding_narrative:      null,
    cta:                     { variant: 'full',     primaryReader: 'manager',  insightStackLayers: [3] },
  },
  // lead_diagnostic 独立走 4 层视图, 此处保留入口元数据
  lead_diagnostic: { __useLeadView: true },
};

const SECTION_ORDER = [
  'executive_summary',
  'pano_score',
  'industry_landscape',
  'brand_performance',
  'product_competitiveness',
  'competitor_comparison',
  'diagnostic_summary',
  'anchor_actions',
  'branding_narrative',
  'cta',
];

/* ─────────────────────────────────────────────────────────────
 * 2. Mock 报告数据
 *   - Brand 按 PRD 4.10.2 多语言名称建模 (nameZh / nameEn)
 *   - executiveSummary / narratives 两种语言各写一份
 *   - 字段对齐 PRD 4.7.1 数据模型 (Report 接口)
 * ─────────────────────────────────────────────────────────── */
const BRAND = {
  id: 'brand-estee-lauder',
  primaryName: 'Estée Lauder',
  nameZh: '雅诗兰黛',
  nameEn: 'Estée Lauder',
};
const COMPETITOR_LANCOME = { nameZh: '兰蔻', nameEn: 'Lancôme' };
const COMPETITOR_SKII     = { nameZh: 'SK-II',  nameEn: 'SK-II' };
const COMPETITOR_LAMER    = { nameZh: '海蓝之谜', nameEn: 'La Mer' };

const REPORTS = [
  {
    id: 'rpt-2026-w16',
    type: 'weekly',
    status: 'completed',
    brand: BRAND,
    periodStart: '2026-04-07',
    periodEnd:   '2026-04-13',
    generatedAt: '2026-04-14T08:00:00+08:00',
    panoScore: 82,
    panoPrev:  79,
    subdim: { V: { current: 85, delta: +4 }, S: { current: 78, delta: +2 }, R: { current: 80, delta: +1 }, A: { current: 84, delta: +5 } },
    sovRank: 2,
    prevSovRank: 3,
    diagnostics: { p0: 1, p1: 2, p2: 3, p3: 4, topTitleZh: '豆包中"小棕瓶"推荐语境占比骤降 35%', topTitleEn: 'Doubao recommendation context for ANR serum dropped 35%' },
    engines: { top: 'ChatGPT', topRate: 34.1, weak: 'DeepSeek', weakRate: 18.6, negKeywordZh: '使用门槛高', negKeywordEn: 'steep learning curve' },
    topProduct: { nameZh: '小棕瓶精华', nameEn: 'Advanced Night Repair', rank: 1, topic: '抗初老精华', contextZh: '熬夜修护', contextEn: 'overnight recovery' },
    newCompetitor: { nameZh: '毛戈平', nameEn: 'MaoGePing', pct: 28 },
    wordCount: 1850,
  },
  {
    id: 'rpt-2026-w15',
    type: 'weekly',
    status: 'completed',
    brand: BRAND,
    periodStart: '2026-03-31',
    periodEnd:   '2026-04-06',
    generatedAt: '2026-04-07T08:00:00+08:00',
    panoScore: 79,
    panoPrev:  81,
    subdim: { V: { current: 82, delta: -2 }, S: { current: 77, delta: -1 }, R: { current: 78, delta: -2 }, A: { current: 80, delta: -1 } },
    sovRank: 3,
    prevSovRank: 2,
    diagnostics: { p0: 0, p1: 3, p2: 5, p3: 2, topTitleZh: '兰蔻在"修护类精华"Topic 中反超排名', topTitleEn: 'Lancôme overtook on the "repair serum" topic' },
    engines: { top: 'ChatGPT', topRate: 31.0, weak: '豆包', weakRate: 16.4, negKeywordZh: '价格偏高', negKeywordEn: 'pricing concerns' },
    topProduct: { nameZh: '小棕瓶精华', nameEn: 'Advanced Night Repair', rank: 2, topic: '熬夜修护', contextZh: '效果显著', contextEn: 'visible results' },
    newCompetitor: { nameZh: 'Paula\'s Choice', nameEn: "Paula's Choice", pct: 14 },
    wordCount: 1720,
  },
  {
    id: 'rpt-2026-03',
    type: 'monthly',
    status: 'completed',
    brand: BRAND,
    periodStart: '2026-03-01',
    periodEnd:   '2026-03-31',
    generatedAt: '2026-04-01T08:00:00+08:00',
    panoScore: 80,
    panoPrev:  77,
    subdim: { V: { current: 83, delta: +6 }, S: { current: 76, delta: +3 }, R: { current: 79, delta: +2 }, A: { current: 82, delta: +4 } },
    sovRank: 2,
    prevSovRank: 2,
    diagnostics: { p0: 2, p1: 5, p2: 8, p3: 6, topTitleZh: 'ChatGPT 中海蓝之谜引用份额超越雅诗兰黛', topTitleEn: 'La Mer citation share on ChatGPT overtook Estée Lauder' },
    engines: { top: 'ChatGPT', topRate: 33.2, weak: 'DeepSeek', weakRate: 19.1, negKeywordZh: '粘腻感', negKeywordEn: 'greasy texture' },
    topProduct: { nameZh: '小棕瓶精华', nameEn: 'Advanced Night Repair', rank: 1, topic: '抗初老精华', contextZh: '官方代言', contextEn: 'official endorsement' },
    newCompetitor: { nameZh: '谷雨', nameEn: 'Proya', pct: 42 },
    wordCount: 3680,
  },
  {
    id: 'rpt-ondemand-0331',
    type: 'on_demand',
    status: 'completed',
    brand: BRAND,
    periodStart: '2026-03-15',
    periodEnd:   '2026-03-31',
    generatedAt: '2026-03-31T14:22:00+08:00',
    panoScore: 78,
    panoPrev:  82,
    subdim: { V: { current: 76, delta: -6 }, S: { current: 79, delta: 0 }, R: { current: 77, delta: -3 }, A: { current: 82, delta: -1 } },
    sovRank: 4,
    prevSovRank: 2,
    diagnostics: { p0: 1, p1: 1, p2: 2, p3: 0, topTitleZh: 'ChatGPT 可见度显著下降, 新版模型改变推荐倾向', topTitleEn: 'ChatGPT visibility sharp drop after model update shifted recommendation bias' },
    engines: { top: '豆包', topRate: 29.4, weak: 'ChatGPT', weakRate: 14.2, negKeywordZh: '成分陈旧', negKeywordEn: 'outdated formulation' },
    topProduct: { nameZh: '白金级奢宠精华', nameEn: 'Re-Nutriv Ultimate Diamond', rank: 3, topic: '高端抗老', contextZh: '礼品首选', contextEn: 'gift of choice' },
    newCompetitor: { nameZh: '赫莲娜', nameEn: 'Helena Rubinstein', pct: 18 },
    wordCount: 1450,
  },
  {
    id: 'rpt-lead-2026-0412',
    type: 'lead_diagnostic',
    status: 'completed',
    brand: BRAND,
    periodStart: '2026-03-14',
    periodEnd:   '2026-04-12',
    generatedAt: '2026-04-12T15:40:00+08:00',
    panoScore: 76,
    panoPrev:  81,
    subdim: { V: { current: 72, delta: -9 }, S: { current: 74, delta: -3 }, R: { current: 78, delta: -2 }, A: { current: 80, delta: -1 } },
    sovRank: 4,
    prevSovRank: 2,
    diagnostics: { p0: 3, p1: 4, p2: 4, p3: 1, topTitleZh: 'ChatGPT 中品牌词召回率下降 42%, 影响购买转化', topTitleEn: 'Brand-term recall on ChatGPT fell 42%, hurting purchase intent' },
    engines: { top: '豆包', topRate: 27.8, weak: 'ChatGPT', weakRate: 11.8, negKeywordZh: '定位模糊', negKeywordEn: 'blurred positioning' },
    topProduct: { nameZh: '小棕瓶精华', nameEn: 'Advanced Night Repair', rank: 2, topic: '熬夜修护', contextZh: '日常回购', contextEn: 'daily replenishment' },
    newCompetitor: { nameZh: '赫莲娜', nameEn: 'Helena Rubinstein', pct: 22 },
    wordCount: 1500,
  },
];

/* ─────────────────────────────────────────────────────────────
 * 3. 辅助: 等级换算 (PRD 4.6.3 色码 + PANO 评分口径)
 * ─────────────────────────────────────────────────────────── */
function panoGrade(score) {
  if (score >= 90) return 'S';
  if (score >= 80) return 'A';
  if (score >= 70) return 'B';
  if (score >= 60) return 'C';
  return 'D';
}
function panoGradeToneClass(score) {
  if (score >= 80) return 'text-themed-accent';
  if (score >= 70) return 'text-themed-primary';
  return 'text-themed-body';
}
function deltaToneClass(delta) {
  if (delta > 0) return 'text-themed-accent'; // 上升用 accent (品牌色)
  if (delta < 0) return 'text-themed-body';   // 下降保持 body (避免红绿误导)
  return 'text-themed-muted';
}
function deltaSign(delta) {
  if (delta > 0) return '+';
  if (delta < 0) return '';
  return '±';
}

/* ─────────────────────────────────────────────────────────────
 * 4. 生成 Report.executiveSummary 等"LLM 叙述"模拟文案
 *    用 t(...) 的模板 key 渲染, 保证 locale 切换时内容同步切换
 * ─────────────────────────────────────────────────────────── */
function buildNarratives(report, t, locale, formatBrand, formatDateRange) {
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
function buildMarkdown(report, sections, narratives, t, formatBrand, formatDateRange) {
  const brand = formatBrand(report.brand);
  const period = formatDateRange(report.periodStart, report.periodEnd);
  const lines = [];
  lines.push(`# ${brand} · ${t(`reports.type_label.${report.type}`)}`);
  lines.push('');
  lines.push(`**${t('reports.kpis.period')}**: ${period}`);
  lines.push(`**${t('reports.kpis.pano_score')}**: ${report.panoScore} (${panoGrade(report.panoScore)}) · Δ ${report.panoScore - report.panoPrev}`);
  lines.push(`**${t('reports.kpis.p0')} / ${t('reports.kpis.p1')}**: ${report.diagnostics.p0} / ${report.diagnostics.p1}`);
  lines.push('');
  sections.forEach((s, idx) => {
    lines.push(`## ${idx + 1}. ${t(`reports.sections.${s.type}`)}`);
    lines.push(`> reader: ${s.primaryReader || '—'} · L${(s.insightStackLayers || []).join('/')}`);
    lines.push('');
    lines.push(narratives[s.type] || '');
    lines.push('');
  });
  return lines.join('\n');
}

function buildJson(report, sections, narratives, formatBrand) {
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
    sections: sections.map((s, idx) => ({
      order: idx + 1,
      type: s.type,
      variant: s.variant,
      primaryReader: s.primaryReader,
      insightStackLayers: s.insightStackLayers,
      narrative: narratives[s.type] || '',
    })),
  };
}

/* ─────────────────────────────────────────────────────────────
 * 6. Section body 渲染器 — 每个 Section 有自己的可视化片段
 *    (真实图表由 Recharts 驱动, 此处为保持 MVP 轻量, 以语义化
 *     的 data-card / 条形 / 徽章网格 呈现数据结构, 正式接入时
 *     替换为 components/charts/* 下的组件即可)
 * ─────────────────────────────────────────────────────────── */
/* PRD §4.7.0-a 三读者视角 颜色 / 标签映射 */
const READER_COLORS = {
  operator: { bg: 'rgba(96,91,255,0.10)', text: 'var(--color-accent)' },
  manager:  { bg: 'rgba(245,166,35,0.12)', text: 'var(--color-warning-text)' },
  branding: { bg: 'rgba(10,187,135,0.10)', text: 'var(--color-success-text)' },
};

function ReaderBadge({ reader, t }) {
  if (!reader) return null;
  const palette = READER_COLORS[reader] || READER_COLORS.operator;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
      style={{ background: palette.bg, color: palette.text }}
      title={t(`reports.reader.${reader}_full`)}
    >
      {t(`reports.reader.${reader}`)}
    </span>
  );
}

function StackLayerBadges({ layers }) {
  if (!layers || layers.length === 0) return null;
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3].map((n) => {
        const active = layers.includes(n);
        return (
          <span
            key={n}
            className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold tabular-nums"
            style={{
              background: active ? 'var(--color-accent-subtle)' : 'var(--color-bg-subtle)',
              color: active ? 'var(--color-accent)' : 'var(--color-text-faint)',
            }}
            title={`L${n} ${['Observation', 'Explanation', 'Direction'][n - 1]}`}
          >
            L{n}
          </span>
        );
      })}
    </span>
  );
}

function SectionShell({ order, title, variantLabel, narrative, children, emphasized, primaryReader, insightStackLayers, t }) {
  return (
    <Card
      className={`p-6 ${emphasized ? 'border border-themed-strong' : ''}`}
      style={emphasized ? { background: 'var(--color-accent-subtle)' } : undefined}
    >
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-themed-inverse bg-themed-gradient-accent"
        >
          {order}
        </span>
        <h3 className="text-sm font-semibold text-themed-primary flex-1">{title}</h3>
        <ReaderBadge reader={primaryReader} t={t} />
        <StackLayerBadges layers={insightStackLayers} />
        {variantLabel && <Badge variant="accent" size="sm">{variantLabel}</Badge>}
      </div>
      {children && <div className="mb-4">{children}</div>}
      {narrative && (
        <div className="pt-4 border-t border-themed-subtle">
          <p className="text-[11px] uppercase tracking-wider text-themed-muted mb-1.5">LLM</p>
          <p className="text-sm text-themed-body leading-relaxed">{narrative}</p>
        </div>
      )}
    </Card>
  );
}

function DataRow({ label, value, delta }) {
  const deltaCls = deltaToneClass(delta ?? 0);
  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-themed-subtle last:border-b-0">
      <span className="text-xs text-themed-muted">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tabular-nums text-themed-primary">{value}</span>
        {delta !== undefined && (
          <span className={`text-[11px] tabular-nums ${deltaCls}`}>
            {deltaSign(delta)}{delta}
          </span>
        )}
      </span>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
 * 7-pre. LeadDiagnosticView — PRD §4.7.4a 4 层架构
 *
 *   1. Quick Wins              (Operator · 短期可做, 低成本)
 *   2. Strategic Bets          (Manager · 跨季度, 需资源决策)
 *   3. Branding Risks          (Branding · 叙事/人设级风险)
 *   4. Consulting Accelerators (转化 · 适合付费咨询的复杂场景)
 *
 *   ⚠️ 严禁渲染具体执行剧本 (PRD §4.8.6) —
 *      每层只展示: 焦点区 + 锚点问题 + 建议参与团队 + 评估窗口
 *      具体动作清单留给付费咨询业务
 * ─────────────────────────────────────────────────────────── */
function classifyDiagnosticsForLead(diags) {
  const quickWins = [];
  const strategicBets = [];
  const brandingRisks = [];
  const consultingAccelerators = [];

  diags.forEach((d) => {
    const ease = d.priorityScore?.ease ?? 5;
    const impact = d.priorityScore?.impact ?? 5;
    const isHighSev = d.severity === 'P0' || d.severity === 'P1';
    const isBranding =
      (d.readerHints || []).includes('branding') || d.category === 'narrative_drift';
    const isComplex =
      (d.causalChain?.alternativeHypotheses || []).length > 0 ||
      d.causalChain?.confidenceLevel === 'low';

    // Branding 优先 (避免 narrative_drift 被分到其他层)
    if (isBranding && isHighSev) {
      brandingRisks.push(d);
      return;
    }
    // Consulting accelerators: 高严重度 + 复杂/低置信
    if (isHighSev && isComplex && impact >= 7) {
      consultingAccelerators.push(d);
      return;
    }
    // Quick wins: 高 ease + 中等以上影响
    if (ease >= 7 && impact >= 5) {
      quickWins.push(d);
      return;
    }
    // Strategic bets: 高影响, 低/中 ease
    if (impact >= 7 || isHighSev) {
      strategicBets.push(d);
      return;
    }
    quickWins.push(d);
  });

  return { quickWins, strategicBets, brandingRisks, consultingAccelerators };
}

const LEAD_LAYER_META = {
  quickWins: {
    color: 'var(--color-success)',
    bg: 'rgba(10,187,135,0.05)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-success)',
  },
  strategicBets: {
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-subtle)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-accent)',
  },
  brandingRisks: {
    color: 'var(--color-warning-text)',
    bg: 'rgba(245,166,35,0.06)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-warning)',
  },
  consultingAccelerators: {
    color: 'var(--color-danger-text)',
    bg: 'rgba(219,55,63,0.05)',
    borderClass: 'border-l-4',
    borderColor: 'var(--color-danger)',
  },
};

function LeadLayerCard({ layerKey, items, t, onContactConsultant }) {
  const meta = LEAD_LAYER_META[layerKey];
  const titleKey = `reports.lead.layer.${layerKey}.title`;
  const descKey = `reports.lead.layer.${layerKey}.description`;
  const readerKey = `reports.lead.layer.${layerKey}.reader`;
  const isPaid = layerKey === 'consultingAccelerators';

  return (
    <Card
      className={`p-5 ${meta.borderClass}`}
      style={{ borderLeftColor: meta.borderColor, background: meta.bg }}
    >
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-1 flex-wrap">
            <h3 className="text-sm font-semibold text-themed-primary">{t(titleKey)}</h3>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
              style={{ background: 'rgba(255,255,255,0.6)', color: meta.color }}
            >
              {t(readerKey)}
            </span>
            <Badge variant={isPaid ? 'red' : 'default'} size="xs">
              {items.length} {t('reports.lead.items_label')}
            </Badge>
          </div>
          <p className="text-[12px] text-themed-secondary leading-relaxed">{t(descKey)}</p>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-[11px] text-themed-faint italic mt-2">
          {t('reports.lead.empty')}
        </p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 5).map((d) => (
            <div
              key={d.id}
              className="rounded-md p-3 bg-themed-card border border-themed-card"
            >
              <div className="flex items-start gap-2 mb-1.5 flex-wrap">
                <Badge
                  variant={
                    { P0: 'red', P1: 'orange', P2: 'accent', P3: 'default' }[d.severity] || 'default'
                  }
                  size="xs"
                >
                  {d.severity}
                </Badge>
                <span className="text-[12px] font-semibold text-themed-primary flex-1 min-w-0">{d.title}</span>
                {d.priorityScore?.composite != null && (
                  <span className="text-[10px] text-themed-muted shrink-0">
                    优先级 <span className="font-semibold tabular-nums text-themed-accent">{d.priorityScore.composite}</span>
                  </span>
                )}
              </div>
              {d.focusArea && (
                <div className="text-[11px] text-themed-secondary mb-1">
                  <span className="text-themed-muted">焦点: </span>
                  {d.focusArea}
                </div>
              )}
              {d.anchorQuestions?.length > 0 && (
                <details>
                  <summary className="text-[11px] font-medium text-themed-accent cursor-pointer hover:opacity-80">
                    {d.anchorQuestions.length} 个锚点问题
                  </summary>
                  <ol className="mt-2 space-y-1 pl-1">
                    {d.anchorQuestions.slice(0, 3).map((q, i) => (
                      <li key={i} className="text-[11px] text-themed-secondary leading-relaxed">
                        <span className="text-themed-faint mr-1.5 tabular-nums">{i + 1}.</span>
                        {q}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          ))}
          {items.length > 5 && (
            <p className="text-[11px] text-themed-faint italic">
              {t('reports.lead.more', { count: items.length - 5 })}
            </p>
          )}
        </div>
      )}

      {isPaid && items.length > 0 && (
        <div
          className="rounded-md p-3 mt-3 flex items-center justify-between border"
          style={{ borderColor: meta.borderColor, background: 'rgba(255,255,255,0.7)' }}
        >
          <div>
            <div className="text-[12px] font-semibold" style={{ color: meta.color }}>
              {t('reports.lead.paid_cta_title')}
            </div>
            <div className="text-[11px] text-themed-secondary mt-0.5">
              {t('reports.lead.paid_cta_subtitle')}
            </div>
          </div>
          <Button variant="accent" size="sm" onClick={onContactConsultant}>
            {t('reports.lead.paid_cta_button')}
          </Button>
        </div>
      )}
    </Card>
  );
}

function LeadDiagnosticView({ report, brandName, t, onContactConsultant }) {
  // 取该品牌相关诊断 (mock: 按 brandId 匹配 + industry 类全收)
  const relevantDiags = useMemo(() => {
    return DIAGNOSTICS.filter((d) => d.type === 'industry' || d.brandId === report.brand.id || true);
    // 当前 mock 数据全是雅诗兰黛, 简化为全选
  }, [report.brand.id]);

  const layers = useMemo(() => classifyDiagnosticsForLead(relevantDiags), [relevantDiags]);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-baseline gap-3 mb-2 flex-wrap">
          <h3 className="text-sm font-semibold text-themed-primary">
            {t('reports.lead.architecture_title')}
          </h3>
          <Badge variant="orange" size="sm">{t('reports.sections.variant.strengthened')}</Badge>
        </div>
        <p className="text-xs text-themed-muted leading-relaxed">
          {t('reports.lead.architecture_subtitle', { brand: brandName })}
        </p>
        <div className="mt-3 grid grid-cols-4 gap-2">
          {[
            { k: 'quickWins', n: layers.quickWins.length },
            { k: 'strategicBets', n: layers.strategicBets.length },
            { k: 'brandingRisks', n: layers.brandingRisks.length },
            { k: 'consultingAccelerators', n: layers.consultingAccelerators.length },
          ].map((row) => {
            const m = LEAD_LAYER_META[row.k];
            return (
              <div
                key={row.k}
                className="rounded-md p-2.5 border"
                style={{ borderColor: m.borderColor, background: m.bg }}
              >
                <div className="text-[10px] font-medium" style={{ color: m.color }}>
                  {t(`reports.lead.layer.${row.k}.title`)}
                </div>
                <div className="text-lg font-bold tabular-nums text-themed-primary mt-0.5">{row.n}</div>
              </div>
            );
          })}
        </div>
      </Card>

      <LeadLayerCard layerKey="quickWins" items={layers.quickWins} t={t} />
      <LeadLayerCard layerKey="strategicBets" items={layers.strategicBets} t={t} />
      <LeadLayerCard layerKey="brandingRisks" items={layers.brandingRisks} t={t} />
      <LeadLayerCard
        layerKey="consultingAccelerators"
        items={layers.consultingAccelerators}
        t={t}
        onContactConsultant={onContactConsultant}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
 * 7. Report Detail View
 * ─────────────────────────────────────────────────────────── */
function ReportDetail({ report, onBack }) {
  const { t, locale, formatDate, formatDateRange, formatBrand, formatNumber } = useLocale();
  const [viewer, setViewer] = useState('preview');

  const narrativesResolved = useMemo(
    () => buildNarratives(report, t, locale, formatBrand, formatDateRange),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report, locale]
  );

  const sections = SECTION_ORDER
    .filter((type) => SECTION_MATRIX[report.type] && SECTION_MATRIX[report.type][type])
    .map((type) => {
      const cell = SECTION_MATRIX[report.type][type];
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
  const sectionBodies = {
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

/* ─────────────────────────────────────────────────────────────
 * 8. Generate Modal
 * ─────────────────────────────────────────────────────────── */
function GenerateModal({ onClose }) {
  const { t, locale } = useLocale();
  const [type, setType] = useState('on_demand');
  const [outputLocale, setOutputLocale] = useState(locale);

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
                <input type="date" defaultValue="2026-03-15" className="t-input w-full" />
              </div>
              <div>
                <label className="text-xs font-medium text-themed-secondary block mb-1.5">
                  {t('reports.generate_modal.end')}
                </label>
                <input type="date" defaultValue="2026-04-14" className="t-input w-full" />
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
          <Button variant="primary" size="md" className="flex-1" onClick={onClose}>
            {t('reports.generate_modal.submit')}
          </Button>
          <Button variant="outline" size="md" onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
        <p
          className="text-[11px] text-themed-faint mt-3 text-center"
          dangerouslySetInnerHTML={{ __html: t('reports.generate_modal.eta') }}
        />
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
 * 9. Report List View + Page shell
 * ─────────────────────────────────────────────────────────── */
export default function ReportsPage() {
  const { t, locale, formatDate, formatBrand, formatNumber, formatDateRange } = useLocale();
  const [activeTab, setActiveTab] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [showGenerate, setShowGenerate] = useState(false);

  const tabs = [
    { id: 'all',             label: t('reports.tabs.all') },
    { id: 'weekly',          label: t('reports.tabs.weekly') },
    { id: 'monthly',         label: t('reports.tabs.monthly') },
    { id: 'on_demand',       label: t('reports.tabs.on_demand') },
    { id: 'lead_diagnostic', label: t('reports.tabs.lead_diagnostic') },
  ];

  const typeVariant = {
    weekly:          'default',
    monthly:         'purple',
    on_demand:       'blue',
    lead_diagnostic: 'orange',
  };

  const filtered = useMemo(
    () => (activeTab === 'all' ? REPORTS : REPORTS.filter((r) => r.type === activeTab)),
    [activeTab]
  );

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

      {/* Tabs */}
      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

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
            : SECTION_ORDER.filter((type) => SECTION_MATRIX[report.type][type]);

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
