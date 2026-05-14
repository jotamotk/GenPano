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
export const SECTION_MATRIX = {
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

export const SECTION_ORDER = [
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
export const BRAND = {
  id: 'brand-estee-lauder',
  primaryName: 'Estée Lauder',
  nameZh: '雅诗兰黛',
  nameEn: 'Estée Lauder',
};
export const COMPETITOR_LANCOME = { nameZh: '兰蔻', nameEn: 'Lancôme' };
export const COMPETITOR_SKII     = { nameZh: 'SK-II',  nameEn: 'SK-II' };
export const COMPETITOR_LAMER    = { nameZh: '海蓝之谜', nameEn: 'La Mer' };

export const REPORTS = [
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
