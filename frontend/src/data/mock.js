// Mock data for GENPANO frontend prototype
// GEO (Generative Engine Optimization) monitoring platform

// ── Knowledge Graph: Category Tree ──
export const CATEGORIES = {
  beauty: [
    { id: 'skincare', name: '护肤', level: 1, children: [
      { id: 'serum', name: '精华', level: 2 },
      { id: 'cream', name: '面霜', level: 2 },
      { id: 'sunscreen', name: '防晒', level: 2 },
      { id: 'cleanser', name: '洁面', level: 2 },
    ]},
    { id: 'makeup', name: '彩妆', level: 1, children: [
      { id: 'foundation', name: '底妆', level: 2 },
      { id: 'lipstick', name: '唇妆', level: 2 },
    ]},
    { id: 'fragrance', name: '香水', level: 1, children: [] },
    { id: 'personal-care', name: '个护', level: 1, children: [] },
  ],
  luxury: [
    { id: 'bags', name: '箱包', level: 1, children: [] },
    { id: 'watches', name: '腕表', level: 1, children: [] },
    { id: 'jewelry', name: '珠宝', level: 1, children: [] },
    { id: 'luxury-fashion', name: '高端服饰', level: 1, children: [] },
  ],
  food: [
    { id: 'dairy', name: '乳制品', level: 1, children: [] },
    { id: 'snacks', name: '零食', level: 1, children: [] },
    { id: 'beverages', name: '饮料', level: 1, children: [] },
    { id: 'health-food', name: '保健品', level: 1, children: [] },
  ],
  fashion: [
    { id: 'sportswear', name: '运动服饰', level: 1, children: [] },
    { id: 'fast-fashion', name: '快时尚', level: 1, children: [] },
    { id: 'designer', name: '设计师品牌', level: 1, children: [] },
    { id: 'underwear', name: '内衣', level: 1, children: [] },
  ],
};

// ── Knowledge Graph: Brand Relations ──
export const BRAND_RELATIONS = [
  { brandA: 'estee-lauder', brandB: 'lancome', type: 'COMPETES_WITH', confidence: 0.92 },
  { brandA: 'estee-lauder', brandB: 'sk-ii', type: 'COMPETES_WITH', confidence: 0.85 },
  { brandA: 'estee-lauder', brandB: 'la-mer', type: 'SAME_GROUP', confidence: 1.0 },
  { brandA: 'estee-lauder', brandB: 'dior', type: 'COMPETES_WITH', confidence: 0.78 },
  { brandA: 'lancome', brandB: 'loreal', type: 'SAME_GROUP', confidence: 1.0 },
  { brandA: 'lancome', brandB: 'sk-ii', type: 'COMPETES_WITH', confidence: 0.88 },
  { brandA: 'lancome', brandB: 'dior', type: 'COMPETES_WITH', confidence: 0.82 },
  { brandA: 'chanel', brandB: 'dior', type: 'COMPETES_WITH', confidence: 0.95 },
  { brandA: 'chanel', brandB: 'la-mer', type: 'COMPETES_WITH', confidence: 0.72 },
  { brandA: 'shiseido', brandB: 'sk-ii', type: 'COMPETES_WITH', confidence: 0.80 },
  { brandA: 'shiseido', brandB: 'lancome', type: 'COMPETES_WITH', confidence: 0.75 },
];

// ── Knowledge Graph: Product Relations ──
export const PRODUCT_RELATIONS = [
  { productA: 'elixir-mini', productB: 'genifique-eye', type: 'COMPETES_WITH', confidence: 0.95 },
  { productA: 'elixir-mini', productB: 'sk-ii-essence', type: 'COMPETES_WITH', confidence: 0.82 },
  { productA: 'elixir-mini', productB: 'la-mer-cream', type: 'UPGRADES_TO', confidence: 0.78 },
  { productA: 'genifique-eye', productB: 'sk-ii-essence', type: 'COMPETES_WITH', confidence: 0.85 },
];

// ── Helper: Get competitors for a brand from Knowledge Graph ──
export function getCompetitors(brandId) {
  const related = BRAND_RELATIONS
    .filter(r => r.type === 'COMPETES_WITH' && (r.brandA === brandId || r.brandB === brandId))
    .map(r => r.brandA === brandId ? r.brandB : r.brandA)
    .map(id => BRANDS.find(b => b.id === id))
    .filter(Boolean);
  return related;
}

// ── Projects (User View Layer) ──
export const PROJECTS = [
  {
    id: 'proj-001',
    name: '雅诗兰黛监测',
    industryId: 'beauty',
    primaryBrandId: 'estee-lauder',
    competitorBrandIds: ['lancome', 'sk-ii', 'dior'],
    preferences: {
      engineFilter: ['ChatGPT', 'DoubleBean', 'DeepSeek'],
      reportSchedule: { weeklyEnabled: true, monthlyEnabled: true, emailRecipients: ['frank@example.com'] },
      alertConfig: { p0Notify: true, p1Notify: true, channel: 'email' },
    },
    status: 'active',
    createdAt: '2026-03-15',
  },
  {
    id: 'proj-002',
    name: '兰蔻监测',
    industryId: 'beauty',
    primaryBrandId: 'lancome',
    competitorBrandIds: ['estee-lauder', 'dior', 'chanel'],
    preferences: {
      engineFilter: ['ChatGPT', 'DoubleBean', 'DeepSeek'],
      reportSchedule: { weeklyEnabled: true, monthlyEnabled: false, emailRecipients: ['frank@example.com'] },
      alertConfig: { p0Notify: true, p1Notify: false, channel: 'email' },
    },
    status: 'active',
    createdAt: '2026-04-01',
  },
];

// Brand search helper (simulates API search against knowledge graph)
export function searchBrands(query, industryId) {
  if (!query || query.length < 1) return [];
  const q = query.toLowerCase();
  return BRANDS
    .filter(b => b.industryId === industryId || !b.industryId)
    .filter(b => b.name.toLowerCase().includes(q) || b.nameEn.toLowerCase().includes(q) || (b.aliases || []).some(a => a.toLowerCase().includes(q)))
    .slice(0, 8);
}

export const INDUSTRIES = [
  {
    id: 'beauty',
    name: '美妆个护',
    nameEn: 'Beauty',
    icon: '💄',
    brandCount: 125,
    productCount: 3420
  },
  {
    id: 'luxury',
    name: '奢侈品',
    nameEn: 'Luxury',
    icon: '👑',
    brandCount: 48,
    productCount: 892
  },
  {
    id: 'food',
    name: '食品饮料',
    nameEn: 'Food & Beverage',
    icon: '🍽️',
    brandCount: 210,
    productCount: 5640
  },
  {
    id: 'fashion',
    name: '服装时尚',
    nameEn: 'Fashion',
    icon: '👗',
    brandCount: 380,
    productCount: 8920
  }
];

export const BRANDS = [
  {
    id: 'chanel',
    name: '香奈儿',
    nameEn: 'Chanel',
    aliases: ['CHANEL', '小香'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: 'Chanel S.A.',
    panoScore: 85,
    tier: 'A',
    change: '+2.3',
    mentionRate: 0.185,
    ranking: 1,
    sentiment: 0.82,
    sov: 22.0,
    citationShare: 17.2
  },
  {
    id: 'estee-lauder',
    name: '雅诗兰黛',
    nameEn: 'Estée Lauder',
    aliases: ['EL', '雅诗兰黛集团'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: 'The Estée Lauder Companies',
    panoScore: 82,
    tier: 'A',
    change: '+1.8',
    mentionRate: 0.162,
    ranking: 2,
    sentiment: 0.79,
    sov: 18.5,
    citationShare: 22.1
  },
  {
    id: 'lancome',
    name: '兰蔻',
    nameEn: 'Lancôme',
    aliases: ['LANCOME'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: "L'Oréal Group",
    panoScore: 79,
    tier: 'B',
    change: '-0.5',
    mentionRate: 0.147,
    ranking: 3,
    sentiment: 0.75,
    sov: 14.5,
    citationShare: 13.8
  },
  {
    id: 'sk-ii',
    name: 'SK-II',
    nameEn: 'SK-II',
    aliases: ['SKII', 'SK2'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: 'P&G',
    panoScore: 75,
    tier: 'B',
    change: '+0.9',
    mentionRate: 0.123,
    ranking: 5,
    sentiment: 0.72,
    sov: 10.5,
    citationShare: 10.2
  },
  {
    id: 'loreal',
    name: '欧莱雅',
    nameEn: "L'Oréal",
    aliases: ['LOREAL', '巴黎欧莱雅'],
    industryId: 'beauty',
    positioning: '大众高端',
    priceRange: '中端',
    parentCompany: "L'Oréal Group",
    panoScore: 71,
    tier: 'B',
    change: '-1.2',
    mentionRate: 0.118,
    ranking: 7,
    sentiment: 0.68,
    sov: 9.0,
    citationShare: 7.9
  },
  {
    id: 'shiseido',
    name: '资生堂',
    nameEn: 'Shiseido',
    aliases: ['SHISEIDO'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: 'Shiseido Group',
    panoScore: 68,
    tier: 'C',
    change: '-0.7',
    mentionRate: 0.094,
    ranking: 8,
    sentiment: 0.65,
    sov: 4.5,
    citationShare: 7.8
  },
  {
    id: 'dior',
    name: '迪奥',
    nameEn: 'Dior',
    aliases: ['DIOR', 'Christian Dior'],
    industryId: 'beauty',
    positioning: '国际高端',
    priceRange: '高端',
    parentCompany: 'LVMH',
    panoScore: 77,
    tier: 'B',
    change: '+1.1',
    mentionRate: 0.139,
    ranking: 4,
    sentiment: 0.74,
    sov: 12.0,
    citationShare: 11.5
  },
  {
    id: 'la-mer',
    name: '海蓝之谜',
    nameEn: 'La Mer',
    aliases: ['LA MER', '赫莲娜'],
    industryId: 'beauty',
    positioning: '顶级奢华',
    priceRange: '超高端',
    parentCompany: 'The Estée Lauder Companies',
    panoScore: 73,
    tier: 'B',
    change: '+0.4',
    mentionRate: 0.106,
    ranking: 6,
    sentiment: 0.70,
    sov: 6.0,
    citationShare: 9.5
  }
];

/* PRODUCTS — 14 条, 覆盖 4 个主要品牌
 * 雅诗兰黛 × 6 (flagship brand, 主演示)
 * 兰蔻 × 3, SK-II × 2, 海蓝之谜 × 3
 *
 * 契约 C7: ranking 必须按 panoScore 降序排列后的索引+1 (DESIGN_TOKENS C7 harness)
 * 契约 C11: mentionRate 必须是小数 0-1 (DESIGN_TOKENS C11 harness)
 */
export const PRODUCTS = [
  {
    id: 'elixir-mini',
    primaryName: '小棕瓶精华',
    name: '小棕瓶精华',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '精华液',
    categoryName: '精华液',
    panoScore: 86,
    change: '+2.1',
    mentionRate: 0.224,
    sov: 18.5,
    sentiment: 0.82,
    trend: 0.05,
    mentionCount: 2240,
    ranking: 1,
    sparkData: [18, 19, 18.5, 19.2, 18.8, 19.5, 18.2, 19.1, 19.3, 18.9, 19.4, 19.0, 18.7, 19.2]
  },
  {
    id: 'genifique-eye',
    primaryName: '小黑瓶精华',
    name: '小黑瓶精华',
    brand: '兰蔻',
    brandEn: 'Lancôme',
    category: '精华液',
    categoryName: '精华液',
    panoScore: 81,
    change: '+0.8',
    mentionRate: 0.189,
    sov: 16.2,
    sentiment: 0.79,
    trend: 0.02,
    mentionCount: 1890,
    ranking: 2,
    sparkData: [15.8, 16.1, 16.0, 16.3, 15.9, 16.2, 16.1, 16.4, 16.0, 16.3, 16.2, 16.1, 16.0, 16.2]
  },
  {
    id: 'estee-multi-smart',
    primaryName: '多效智妍眼霜',
    name: '多效智妍眼霜',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '眼霜',
    categoryName: '眼霜',
    panoScore: 79,
    change: '+1.5',
    mentionRate: 0.171,
    sov: 15.3,
    sentiment: 0.80,
    trend: 0.04,
    mentionCount: 1710,
    ranking: 3,
    sparkData: [14.6, 14.9, 15.0, 15.2, 14.8, 15.1, 15.3, 15.0, 15.2, 15.4, 15.3, 15.1, 15.2, 15.3]
  },
  {
    id: 'sk-ii-essence',
    primaryName: '神仙水',
    name: '神仙水',
    brand: 'SK-II',
    brandEn: 'SK-II',
    category: '精华水',
    categoryName: '精华水',
    panoScore: 78,
    change: '+1.3',
    mentionRate: 0.162,
    sov: 14.8,
    sentiment: 0.75,
    trend: 0.08,
    mentionCount: 1620,
    ranking: 4,
    sparkData: [13.9, 14.2, 14.1, 14.5, 14.3, 14.6, 14.4, 14.8, 14.5, 14.7, 14.9, 14.6, 14.8, 14.7]
  },
  {
    id: 'lancome-absolue-eye',
    primaryName: '菁纯臻颜眼霜',
    name: '菁纯臻颜眼霜',
    brand: '兰蔻',
    brandEn: 'Lancôme',
    category: '眼霜',
    categoryName: '眼霜',
    panoScore: 77,
    change: '+0.6',
    mentionRate: 0.155,
    sov: 13.9,
    sentiment: 0.78,
    trend: 0.03,
    mentionCount: 1550,
    ranking: 5,
    sparkData: [13.2, 13.5, 13.4, 13.7, 13.6, 13.8, 13.9, 13.7, 13.9, 14.0, 13.8, 13.9, 13.8, 13.9]
  },
  {
    id: 'la-mer-concentrate',
    primaryName: '修护精萃水',
    name: '修护精萃水',
    brand: '海蓝之谜',
    brandEn: 'La Mer',
    category: '精华水',
    categoryName: '精华水',
    panoScore: 76,
    change: '+0.4',
    mentionRate: 0.148,
    sov: 13.2,
    sentiment: 0.74,
    trend: 0.02,
    mentionCount: 1480,
    ranking: 6,
    sparkData: [12.6, 12.8, 12.9, 13.0, 13.1, 13.2, 13.0, 13.1, 13.2, 13.3, 13.1, 13.2, 13.2, 13.2]
  },
  {
    id: 'sk-ii-red-cream',
    primaryName: 'SK-II 大红瓶面霜',
    name: '大红瓶面霜',
    brand: 'SK-II',
    brandEn: 'SK-II',
    category: '面霜',
    categoryName: '面霜',
    panoScore: 75,
    change: '+0.9',
    mentionRate: 0.143,
    sov: 12.7,
    sentiment: 0.73,
    trend: 0.05,
    mentionCount: 1430,
    ranking: 7,
    sparkData: [11.8, 12.0, 12.2, 12.4, 12.3, 12.5, 12.6, 12.4, 12.6, 12.7, 12.5, 12.6, 12.7, 12.7]
  },
  {
    id: 'la-mer-cream',
    primaryName: '精华面霜',
    name: '精华面霜',
    brand: '海蓝之谜',
    brandEn: 'La Mer',
    category: '面霜',
    categoryName: '面霜',
    panoScore: 74,
    change: '-0.2',
    mentionRate: 0.141,
    sov: 12.1,
    sentiment: 0.71,
    trend: -0.01,
    mentionCount: 1410,
    ranking: 8,
    sparkData: [12.3, 12.1, 12.2, 12.0, 12.3, 12.1, 12.2, 12.0, 12.1, 12.2, 12.0, 12.3, 12.1, 12.2]
  },
  {
    id: 'estee-micro-essence',
    primaryName: '鲜亮焕颜精华水',
    name: '鲜亮焕颜精华水',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '精华水',
    categoryName: '精华水',
    panoScore: 73,
    change: '+0.7',
    mentionRate: 0.132,
    sov: 11.5,
    sentiment: 0.77,
    trend: 0.03,
    mentionCount: 1320,
    ranking: 9,
    sparkData: [10.8, 11.0, 11.1, 11.2, 11.3, 11.4, 11.3, 11.5, 11.4, 11.5, 11.6, 11.4, 11.5, 11.5]
  },
  {
    id: 'estee-night-repair',
    primaryName: '肌透修护晚霜',
    name: '肌透修护晚霜',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '面霜',
    categoryName: '面霜',
    panoScore: 72,
    change: '+0.3',
    mentionRate: 0.125,
    sov: 10.9,
    sentiment: 0.76,
    trend: 0.01,
    mentionCount: 1250,
    ranking: 10,
    sparkData: [10.3, 10.5, 10.6, 10.7, 10.8, 10.9, 10.7, 10.9, 10.8, 10.9, 11.0, 10.8, 10.9, 10.9]
  },
  {
    id: 'lancome-tonique',
    primaryName: '清滢柔肤水 (大粉水)',
    name: '大粉水',
    brand: '兰蔻',
    brandEn: 'Lancôme',
    category: '化妆水',
    categoryName: '化妆水',
    panoScore: 71,
    change: '-0.4',
    mentionRate: 0.118,
    sov: 10.2,
    sentiment: 0.72,
    trend: -0.02,
    mentionCount: 1180,
    ranking: 11,
    sparkData: [10.8, 10.6, 10.5, 10.4, 10.3, 10.2, 10.3, 10.1, 10.2, 10.1, 10.2, 10.3, 10.2, 10.2]
  },
  {
    id: 'estee-double-wear',
    primaryName: '沁水粉底液 (Double Wear)',
    name: '沁水粉底液',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '粉底液',
    categoryName: '粉底液',
    panoScore: 70,
    change: '+1.2',
    mentionRate: 0.113,
    sov: 9.8,
    sentiment: 0.74,
    trend: 0.06,
    mentionCount: 1130,
    ranking: 12,
    sparkData: [9.1, 9.3, 9.4, 9.5, 9.6, 9.7, 9.6, 9.7, 9.8, 9.9, 9.7, 9.8, 9.9, 9.8]
  },
  {
    id: 'estee-pomegranate',
    primaryName: '红石榴新生原液',
    name: '红石榴原液',
    brand: '雅诗兰黛',
    brandEn: 'Estée Lauder',
    category: '精华液',
    categoryName: '精华液',
    panoScore: 68,
    change: '-0.5',
    mentionRate: 0.098,
    sov: 8.5,
    sentiment: 0.69,
    trend: -0.03,
    mentionCount: 980,
    ranking: 13,
    sparkData: [9.2, 9.1, 8.9, 8.8, 8.7, 8.6, 8.7, 8.5, 8.6, 8.5, 8.4, 8.5, 8.5, 8.5]
  },
  {
    id: 'la-mer-eye-concentrate',
    primaryName: '修护眼霜',
    name: '修护眼霜',
    brand: '海蓝之谜',
    brandEn: 'La Mer',
    category: '眼霜',
    categoryName: '眼霜',
    panoScore: 66,
    change: '+0.1',
    mentionRate: 0.089,
    sov: 7.6,
    sentiment: 0.70,
    trend: 0.01,
    mentionCount: 890,
    ranking: 14,
    sparkData: [7.3, 7.4, 7.5, 7.6, 7.5, 7.6, 7.7, 7.5, 7.6, 7.7, 7.6, 7.6, 7.5, 7.6]
  }
];

/* ────────────────────────────────────────────────────────────────
 * DIAGNOSTICS · PRD §4.8.2 深度升级版 (2026-04-16)
 *
 * 每条诊断必须符合 PRD §4.7.0-a 洞察 Stack × 三读者视角框架:
 *   Layer 1 Observation:  evidence + responseSamples
 *   Layer 2 Explanation:  causalChain (含 confidence) + industryBenchmark
 *   Layer 3 Direction:    focusArea + anchorQuestions (3-5 条事实探查型, 不是 playbook)
 *                         + ifUntreated (不干预后果) + direction (方向性建议, Level 3 颗粒度)
 *
 * 🚫 严禁字段 (PRD §4.8.6):
 *   ✗ optimizationSteps (playbook, 违反 Layer 4 禁区)
 *   ✗ 具体执行步骤 ("发布 X 篇文章", "找 KOL Y")
 *   ✗ 自由文本 benchmarkReference (应改为结构化 industryBenchmark)
 *
 * Category 分布 (覆盖 PRD §4.8.2a 全部 8 类 + 1 行业):
 *   visibility_decline   × 2  (diag-001 热点主题丢失 / diag-009 引擎覆盖微降)
 *   sentiment_shift      × 2  (diag-006 产品负面 / diag-010 叙事防御信号)
 *   competitor_overtake  × 1  (diag-004 兰蔻反超)
 *   citation_source_loss × 1  (diag-005 权威引用链路断裂)
 *   product_misinformation × 1 (diag-003 成分描述错误)
 *   product_missing      × 1  (diag-007 品类场景未出现)
 *   new_entrant          × 1  (diag-008 国货新锐观夏)
 *   narrative_drift      × 1  (diag-002 AI 人设漂移)
 *
 * Severity 分布: P0 × 2 / P1 × 4 / P2 × 3 / P3 × 1
 * ──────────────────────────────────────────────────────────── */
export const DIAGNOSTICS = [
  /* ─────── P0 · 紧急 (composite >= 8.5) ─────── */
  {
    id: 'diag-001',
    category: 'visibility_decline',
    severity: 'P0',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '雅诗兰黛在 ChatGPT "熬夜急救" 主题 SoV 持续下滑',
    description: '雅诗兰黛在 ChatGPT 上"熬夜急救 / 夜间修护"主题的 SoV 从 18% 降至 12% (WoW -6pt), 引用份额同步 -8pt。该主题近 21 天份额持续下滑, 触发诊断 P0 升级。',
    engine: 'ChatGPT',
    detected: '2026-04-13',
    focusArea: '熬夜急救主题内容丢失',
    direction: '提升品牌在"熬夜急救"主题权威来源的内容覆盖密度与结构化程度',
    readerHints: ['operator', 'manager'],
    decisionPrompt: '是否在下 4 周启动"熬夜急救"专题内容补位? 预估需调整内容+传播预算 8-12 万',
    evidence: {
      metric: 'sov',
      currentValue: 12,
      previousValue: 18,
      changePercent: -33,
      timeRange: '2026-03-23 → 2026-04-13',
      affectedQueries: ['熬夜急救精华推荐', '夜间修护精华', '熬夜暗沉救急'],
      affectedEngines: ['ChatGPT'],
    },
    causalChain: {
      triggerMetrics: ['sov', 'citation_share', 'topic_mention_rate'],
      hypothesizedMechanism: 'ChatGPT 在该主题改用科普体内容, 品牌名被挤出推荐位; 同期高权威引用来源 -4, 弱化了品牌在该主题的可引用性',
      supportingEvidence: ['resp-2011-a', 'resp-2011-b', 'resp-2011-c'],
      confidenceLevel: 'medium',
      alternativeHypotheses: ['可能与 OpenAI 近期模型版本切换有关, 非内容侧变化 (需监测 2-4 周验证)'],
    },
    industryBenchmark: {
      metric: 'SoV in "熬夜急救" topic',
      myValue: 12,
      industryMedian: 18,
      industryTop10Avg: 21,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 30,
        keyCharacteristics: ['近 30 天该主题内容输出 8 篇', '权威媒体引用来源 12 个', '主打"实验室科技"叙事'],
      },
      gapAnalysis: { gapToMedian: -6, gapToTop: -18, percentileRank: 35 },
    },
    priorityScore: { impact: 9, ease: 5, urgency: 9, composite: 7.7, rankWithinPeriod: 1 },
    timeSeries: {
      firstObservedAt: '2026-03-23',
      lastUpdatedAt: '2026-04-13',
      trendStatus: 'growing',
      ageInDays: 21,
      severityHistory: [
        { date: '2026-03-23', severity: 'P1' },
        { date: '2026-03-30', severity: 'P1' },
        { date: '2026-04-06', severity: 'P0' },
        { date: '2026-04-13', severity: 'P0' },
      ],
    },
    anchorQuestions: [
      '该主题 Top5 引文来源是谁? 我方官网/权威媒体是否被 ChatGPT 索引?',
      '过去 3 周兰蔻在该主题发过多少条内容? URL 清单能否拉到?',
      '我方内部是否有该主题的 Q&A/科普素材? 是否已结构化发布?',
      '若启动内容补位, 预计产出周期多长? 4 周内能否追回?',
      '是否存在与 KOL/权威媒体的合作机会加速引用?',
    ],
    ifUntreated: {
      metric: 'SoV',
      projectedValue: 8,
      timeframe: '4 weeks',
      confidence: 'medium',
      scenarioDescription: '4 周内 SoV 预计跌至 8%, 行业排名从 #5 掉至 #8; 兰蔻"科技抗老"叙事可能进一步固化, 心智重建周期延长至 6-12 个月',
    },
    predictedImpact: { metric: 'SoV', projectedChange: 6, timeframe: '4-6 weeks', confidence: 'medium', scoreChange: '+4-6 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: ['diag-005'], historicalSimilar: [] },
    responseSamples: [
      { engine: 'ChatGPT', promptId: 'P-17832', responseId: 'R-2801', snippet: '针对熬夜导致的皮肤损伤, 推荐含神经酰胺的精华, 兰蔻小黑瓶在这方面表现突出, Olay 小白瓶也是近期热门选择...', capturedAt: '2026-04-11' },
      { engine: 'ChatGPT', promptId: 'P-18203', responseId: 'R-2815', snippet: '熬夜急救类精华, 近期被频繁提及的有 Olay 小白瓶和兰蔻新品系列...', capturedAt: '2026-04-12' },
    ],
    // 兼容字段 (legacy badge / 排序)
    impact: '+4-6 PANO',
    timeframe: '需要立即行动',
  },

  {
    id: 'diag-002',
    category: 'narrative_drift',
    severity: 'P0',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '雅诗兰黛 AI 人设正从"前沿抗老"漂移至"传统经典"',
    description: 'AI 对雅诗兰黛的描述关键词发生系统性变化: "创新""科技""前沿"提及率下降 40%, "经典""稳定""老牌"上升 35%。竞品兰蔻正抢占"科技新锐"心智, 若持续可能固化 6-12 个月。',
    engine: 'ChatGPT',
    detected: '2026-04-12',
    focusArea: 'AI 叙事定位漂移',
    direction: '稀释"传统稳定"类叙事, 增强"科技前沿"维度内容可引用性',
    readerHints: ['branding', 'manager'],
    decisionPrompt: '是否启动"科技抗老"内容战线以对冲兰蔻? 需要 Branding + Content + PR 跨职能协作',
    evidence: {
      metric: 'persona_keyword_frequency',
      currentValue: 60,
      previousValue: 100,
      changePercent: -40,
      timeRange: '2026-Q1 → 2026-W16',
      affectedQueries: ['雅诗兰黛品牌形象', '高端抗老精华', '经典护肤品牌'],
      affectedEngines: ['ChatGPT', '豆包'],
    },
    causalChain: {
      triggerMetrics: ['brand_persona_keyword_shift', 'competitor_narrative_strength'],
      hypothesizedMechanism: '竞品兰蔻近 30 天发布 "实验室科技" 主题内容 8+ 条并被 AI 索引, 抢占"科技"心智; 同期我方近 3 个月未产出科技叙事内容, AI 依赖存量内容形成"经典稳定"定位',
      supportingEvidence: ['brand-persona-diff-2026W13-W16', 'competitor-content-drop-lancome'],
      confidenceLevel: 'medium',
      alternativeHypotheses: ['AI 模型本身对"传统高端"品牌标签有偏好倾向, 非内容侧差距'],
    },
    industryBenchmark: {
      metric: 'AI persona freshness index',
      myValue: 58,
      industryMedian: 72,
      industryTop10Avg: 78,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 85,
        keyCharacteristics: ['AI 描述 Top3 词: 科技 / 新锐 / 前沿', '叙事紧张度: 上升动能', '近 30 天"实验室""专利""科技"关键词提及 +80%'],
      },
      gapAnalysis: { gapToMedian: -14, gapToTop: -27, percentileRank: 28 },
    },
    priorityScore: { impact: 9, ease: 3, urgency: 8, composite: 7.3, rankWithinPeriod: 2 },
    timeSeries: {
      firstObservedAt: '2026-02-15',
      lastUpdatedAt: '2026-04-12',
      trendStatus: 'growing',
      ageInDays: 57,
      severityHistory: [
        { date: '2026-02-15', severity: 'P2' },
        { date: '2026-03-15', severity: 'P1' },
        { date: '2026-04-12', severity: 'P0' },
      ],
    },
    anchorQuestions: [
      '漂移前后的人设高频词对比表能否拉到过去 12 周?',
      '漂移对应的内容事件是什么? (是竞品主动塑造 / 还是我方内容沉寂?)',
      '我方"科技/创新"维度现有内容库存盘点情况如何?',
      '是否有实验室合作 / 专利 / 研发项目可作为内容素材?',
      '是否需要 PR / Branding 团队介入叙事校准?',
    ],
    ifUntreated: {
      metric: 'persona_drift_depth',
      projectedValue: 75,
      timeframe: '2 quarters',
      confidence: 'medium',
      scenarioDescription: '2 个季度后 AI 人设可能固化为"经典稳定 · 偏向熟龄客群", 丢失年轻+科技向客群心智, 重建窗口需 6-12 个月',
    },
    predictedImpact: { metric: 'persona_freshness', projectedChange: 15, timeframe: '8-12 weeks', confidence: 'low', scoreChange: '+3-5 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: ['diag-004'], historicalSimilar: [] },
    responseSamples: [
      { engine: '豆包', promptId: 'P-19001', responseId: 'R-3020', snippet: 'XX 近年在新品创新速度上稍慢于兰蔻, 但仍是高端抗老中最稳定的经典品牌...', capturedAt: '2026-04-10' },
      { engine: 'ChatGPT', promptId: 'P-19102', responseId: 'R-3055', snippet: 'XX 是高端美妆中最稳定的抗老品牌之一, 适合追求经典品质的熟龄用户...', capturedAt: '2026-04-11' },
    ],
    impact: '+3-5 PANO',
    timeframe: '需要立即行动',
  },

  /* ─────── P1 · 重要 (composite 6.5-8.4) ─────── */
  {
    id: 'diag-003',
    category: 'product_misinformation',
    severity: 'P1',
    type: 'product',
    brandId: 'estee-lauder',
    productId: 'prod-anr',
    title: '小棕瓶精华在 DeepSeek 中被描述"含酒精" (实际不含)',
    description: 'DeepSeek 回答中, 小棕瓶精华成分描述出现"含酒精, 敏感肌慎用"错误信息, 影响 DeepSeek 中约 12% 相关响应。追溯发现某第三方测评文章被 AI 错误采样。',
    engine: 'DeepSeek',
    detected: '2026-04-11',
    focusArea: '产品成分描述错误 + 第三方来源污染',
    direction: '增强产品核心信息在 AI 可索引内容中的一致性和准确性',
    readerHints: ['operator'],
    evidence: {
      metric: 'product_accuracy',
      currentValue: 88,
      previousValue: 100,
      changePercent: -12,
      timeRange: '2026-04-05 → 2026-04-11',
      affectedQueries: ['小棕瓶成分', '敏感肌精华推荐', '酒精精华避雷'],
      affectedEngines: ['DeepSeek'],
    },
    causalChain: {
      triggerMetrics: ['product_info_accuracy', 'citation_source_composition'],
      hypothesizedMechanism: '某第三方测评文章(2025-Q4 发布)错误标注成分"含酒精"被 DeepSeek 索引, 错误信息扩散至相关 Topic 响应; 官网产品页 schema 标记不完整, AI 难以校准',
      supportingEvidence: ['resp-3041-a', 'source-3rdparty-X42'],
      confidenceLevel: 'high',
    },
    industryBenchmark: {
      metric: 'product_accuracy_score',
      myValue: 88,
      industryMedian: 92,
      industryTop10Avg: 96,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 98,
        keyCharacteristics: ['官网产品页 JSON-LD schema 完整', '3 大引擎准确率均 >95%'],
      },
      gapAnalysis: { gapToMedian: -4, gapToTop: -10, percentileRank: 42 },
    },
    priorityScore: { impact: 6, ease: 8, urgency: 7, composite: 6.9, rankWithinPeriod: 3 },
    timeSeries: {
      firstObservedAt: '2026-04-05',
      lastUpdatedAt: '2026-04-11',
      trendStatus: 'new',
      ageInDays: 6,
      severityHistory: [{ date: '2026-04-05', severity: 'P1' }],
    },
    anchorQuestions: [
      '错误描述的来源是哪份第三方文章? URL 能否定位?',
      '官网产品页 schema 结构化数据是否正确且完整?',
      '是否已向 DeepSeek 提交 feedback 纠错?',
      '关联的第三方文章能否联系原作者修正?',
    ],
    ifUntreated: {
      metric: 'product_accuracy',
      projectedValue: 80,
      timeframe: '6 weeks',
      confidence: 'medium',
      scenarioDescription: '错误描述若持续 6 周未纠正, 可能被其他 AI 引擎交叉采样固化, 敏感肌细分客群心智受损',
    },
    predictedImpact: { metric: 'product_accuracy', projectedChange: 10, timeframe: '2-4 weeks', confidence: 'high', scoreChange: '+1-2 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [
      { engine: 'DeepSeek', promptId: 'P-20101', responseId: 'R-4101', snippet: '小棕瓶精华含有少量酒精成分, 敏感肌使用前建议先做耳后测试...', capturedAt: '2026-04-09' },
    ],
    impact: '+1-2 PANO',
    timeframe: '需要 1 周内处理',
  },

  {
    id: 'diag-004',
    category: 'competitor_overtake',
    severity: 'P1',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '兰蔻在"科技抗老"心智中快速抢占, 反超至行业第 2',
    description: '兰蔻 SoV 4 周内上升 6pt, 反超雅诗兰黛至行业第 2。其近 30 天上线"实验室科技"主题内容 8 篇, 全部被 ChatGPT 索引。我方在"科技感"维度内容库存断档。',
    engine: 'ChatGPT',
    detected: '2026-04-10',
    focusArea: '竞品"科技抗老"叙事抢占',
    direction: '补强品牌在"科技 / 实验室 / 专利"维度的权威内容可引用性',
    readerHints: ['operator', 'manager', 'branding'],
    decisionPrompt: '是否在下季度加投预算追赶"科技抗老"内容战线? 预估 X 万, 窗口期 8 周内',
    evidence: {
      metric: 'sov',
      currentValue: 12,
      previousValue: 14,
      changePercent: -14,
      timeRange: '2026-03-16 → 2026-04-10',
      affectedQueries: ['高端抗老精华', '科技护肤推荐', '实验室级抗老产品'],
      affectedEngines: ['ChatGPT', '豆包'],
    },
    causalChain: {
      triggerMetrics: ['competitor_sov_delta', 'topic_content_supply'],
      hypothesizedMechanism: '兰蔻通过集中内容投放 (8 篇 / 30 天) 抢占"科技抗老"Topic 可引用性, 同时我方内容库存断档, AI 默认选择竞品作为首位推荐',
      supportingEvidence: ['competitor-content-audit-lancome', 'sov-weekly-trend-W13-W16'],
      confidenceLevel: 'high',
    },
    industryBenchmark: {
      metric: 'sov (高端抗老)',
      myValue: 12,
      industryMedian: 15,
      industryTop10Avg: 18,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 18,
        keyCharacteristics: ['近 30 天该主题内容输出 8 篇', '"实验室""专利"类引用来源 +4', '叙事紧张度: 上升动能'],
      },
      gapAnalysis: { gapToMedian: -3, gapToTop: -6, percentileRank: 45 },
    },
    priorityScore: { impact: 8, ease: 5, urgency: 8, composite: 7.2, rankWithinPeriod: 4 },
    timeSeries: {
      firstObservedAt: '2026-03-16',
      lastUpdatedAt: '2026-04-10',
      trendStatus: 'growing',
      ageInDays: 25,
      severityHistory: [
        { date: '2026-03-16', severity: 'P2' },
        { date: '2026-04-10', severity: 'P1' },
      ],
    },
    anchorQuestions: [
      '兰蔻近 30 天发了什么? 内容类型和分发渠道清单?',
      '我方在"科技感"维度的现有内容库存盘点?',
      '引文来源差异: 哪些权威媒体是兰蔻在用而我方没有?',
      '是否需要 Branding 团队配合重建"前沿科技"叙事?',
    ],
    ifUntreated: {
      metric: 'industry_rank',
      projectedValue: 4,
      timeframe: '8 weeks',
      confidence: 'medium',
      scenarioDescription: '8 周后可能被进一步推到第 4 位; 兰蔻的"科技抗老"心智固化 6-12 个月难逆转',
    },
    predictedImpact: { metric: 'sov', projectedChange: 4, timeframe: '6-8 weeks', confidence: 'medium', scoreChange: '+4-6 PANO' },
    relatedDiagnostics: { derivedFrom: ['diag-002'], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [
      { engine: 'ChatGPT', promptId: 'P-21001', responseId: 'R-5201', snippet: '在高端抗老领域, 兰蔻凭借其实验室研发体系和近期推出的专利成分, 是目前最受关注的品牌...', capturedAt: '2026-04-09' },
    ],
    impact: '+4-6 PANO',
    timeframe: '需要 1 周内处理',
  },

  {
    id: 'diag-005',
    category: 'citation_source_loss',
    severity: 'P1',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '核心权威媒体引用链路断裂, 低权威 UGC 稀释 A 分',
    description: '过去 4 周, 我方被 ChatGPT 引用的高权威来源 -4 (某美妆评测媒体停更 + 某权威博客改写); 同期低权威 UGC 类引用 +8, 导致 A (Authority) 分 -2。',
    engine: 'ChatGPT',
    detected: '2026-04-08',
    focusArea: '权威引用来源结构恶化',
    direction: '提升品牌官方内容的结构化程度和可被 AI 抓取/引用的能力',
    readerHints: ['operator'],
    evidence: {
      metric: 'authority_citation_ratio',
      currentValue: 38,
      previousValue: 52,
      changePercent: -27,
      timeRange: '2026-03-11 → 2026-04-08',
      affectedQueries: ['高端抗老推荐', '权威精华测评'],
      affectedEngines: ['ChatGPT'],
      // CitationSourceLossEvidence schema per PRD §4.2.6.F
      // 算法: T-14d vs T-0 Tier 1+2 域名集合 diff, 丢失 ≥3 且 remaining < 70% → P1
      citationSourceLoss: {
        tierFilter: [1, 2],
        t0Window: '2026-03-11 → 2026-03-25',
        t1Window: '2026-03-25 → 2026-04-08',
        t0TierSet: [
          { domain: 'esteelauder.com.cn', tier: 1, authorityConfidence: 1.0 },
          { domain: 'beauty.pclady.com.cn', tier: 2, authorityConfidence: 0.85 },
          { domain: 'cosmopolitan.com.cn', tier: 2, authorityConfidence: 0.80 },
          { domain: 'vogue.com.cn', tier: 2, authorityConfidence: 0.82 },
          { domain: 'allure.com', tier: 2, authorityConfidence: 0.78 },
          { domain: 'paulaschoice.com', tier: 2, authorityConfidence: 0.76 },
        ],
        t1TierSet: [
          { domain: 'esteelauder.com.cn', tier: 1, authorityConfidence: 1.0 },
          { domain: 'beauty.pclady.com.cn', tier: 2, authorityConfidence: 0.85 },
        ],
        lostDomains: [
          { domain: 'cosmopolitan.com.cn', tier: 2, lastSeenAt: '2026-03-20', reason: 'stopped_updating' },
          { domain: 'vogue.com.cn', tier: 2, lastSeenAt: '2026-03-22', reason: 'content_rewritten' },
          { domain: 'allure.com', tier: 2, lastSeenAt: '2026-03-18', reason: 'stopped_updating' },
          { domain: 'paulaschoice.com', tier: 2, lastSeenAt: '2026-03-24', reason: 'unknown' },
        ],
        lostCount: 4,
        remainingRatio: 0.33,
        thresholdLostCount: 3,
        thresholdRemainingRatio: 0.70,
        triggered: true,
      },
    },
    causalChain: {
      triggerMetrics: ['citation_source_composition', 'authority_score'],
      hypothesizedMechanism: '核心权威来源停更/改写 → AI 改用 UGC 类引用填补 → 引用权威度降低 → A 分下降',
      supportingEvidence: ['citation-diff-W12-W16', 'top-cited-domains-delta'],
      confidenceLevel: 'high',
    },
    industryBenchmark: {
      metric: 'authority citation ratio',
      myValue: 38,
      industryMedian: 48,
      industryTop10Avg: 55,
      topCompetitor: {
        brandId: 'sk-ii',
        brandName: 'SK-II',
        value: 62,
        keyCharacteristics: ['14 个高权威引用来源', '官方内容 schema 完整度 95%'],
      },
      gapAnalysis: { gapToMedian: -10, gapToTop: -24, percentileRank: 33 },
    },
    priorityScore: { impact: 7, ease: 6, urgency: 7, composite: 6.7, rankWithinPeriod: 5 },
    timeSeries: {
      firstObservedAt: '2026-03-15',
      lastUpdatedAt: '2026-04-08',
      trendStatus: 'persisting',
      ageInDays: 24,
      severityHistory: [
        { date: '2026-03-15', severity: 'P2' },
        { date: '2026-04-08', severity: 'P1' },
      ],
    },
    anchorQuestions: [
      '丢失的 Top 引用来源是谁? 停发或改写原因能否核实?',
      '是否存在替代来源 (同等权威度) 可主动对接?',
      '官方官网的结构化数据 (schema.org / JSON-LD) 能否补位?',
      '内部是否有权威合作伙伴 (皮肤科医生 / 研究机构) 可作为引用源?',
    ],
    ifUntreated: {
      metric: 'A (Authority) score',
      projectedValue: 56,
      timeframe: '6 weeks',
      confidence: 'medium',
      scenarioDescription: 'A 分可能继续下滑至 56 分, PANO Score 整体 -3 分; UGC 类引用主导可能引入更多噪声和情感风险',
    },
    predictedImpact: { metric: 'authority_citation_ratio', projectedChange: 12, timeframe: '4-6 weeks', confidence: 'medium', scoreChange: '+2-3 PANO' },
    relatedDiagnostics: { derivedFrom: ['diag-001'], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [],
    impact: '+2-3 PANO',
    timeframe: '需要 2 周内处理',
  },

  {
    id: 'diag-006',
    category: 'sentiment_shift',
    severity: 'P1',
    type: 'product',
    brandId: 'estee-lauder',
    productId: 'prod-anr',
    title: '小棕瓶精华"过敏"负面关键词 +180%, 情感分跌破阈值',
    description: '小棕瓶精华在豆包引擎中情感分从 0.85 降至 0.76 (-10.6%), "过敏""刺激"关键词 +180%, "效果不如以前" +95%。与近期 3 条高权重负面内容被 AI 高频引用相关。',
    engine: '豆包',
    detected: '2026-04-09',
    focusArea: '产品负面关键词扩散 + 情感来源污染',
    direction: '稀释负面内容源的权重, 增强正面用户体验内容的可引用性',
    readerHints: ['operator', 'branding'],
    evidence: {
      metric: 'sentiment_score',
      currentValue: 0.76,
      previousValue: 0.85,
      changePercent: -10.6,
      timeRange: '2026-03-26 → 2026-04-09',
      affectedQueries: ['敏感肌精华', '小棕瓶过敏', '抗初老精华副作用'],
      affectedEngines: ['豆包'],
    },
    causalChain: {
      triggerMetrics: ['sentiment_score', 'negative_keyword_frequency', 'citation_source_diff'],
      hypothesizedMechanism: '3 条高权重负面内容 (社交媒体过敏讨论帖) 被豆包高频采样 → 负面关键词扩散 → 情感分下降; 同时正面内容权威度不足, 无法平衡',
      supportingEvidence: ['sentiment-keyword-diff-W14-W16', 'top-cited-negative-pages'],
      confidenceLevel: 'high',
    },
    industryBenchmark: {
      metric: 'sentiment score',
      myValue: 0.76,
      industryMedian: 0.78,
      industryTop10Avg: 0.82,
      topCompetitor: {
        brandId: 'sk-ii',
        brandName: 'SK-II 神仙水',
        value: 0.86,
        keyCharacteristics: ['皮肤科医生背书内容占比 28%', '负面词频占比 <6%'],
      },
      gapAnalysis: { gapToMedian: -0.02, gapToTop: -0.1, percentileRank: 48 },
    },
    priorityScore: { impact: 7, ease: 6, urgency: 8, composite: 7.0, rankWithinPeriod: 6 },
    timeSeries: {
      firstObservedAt: '2026-03-28',
      lastUpdatedAt: '2026-04-09',
      trendStatus: 'growing',
      ageInDays: 12,
      severityHistory: [
        { date: '2026-03-28', severity: 'P2' },
        { date: '2026-04-09', severity: 'P1' },
      ],
    },
    anchorQuestions: [
      '负面关键词的原始来源是哪些内容? URL 清单可定位吗?',
      '该来源的权重能否通过正面内容覆盖降低?',
      '是否有 UGC / KOL 正面内容能覆盖同一语义场景?',
      '品牌官方是否有针对"过敏""刺激"疑虑的澄清通道 (FAQ / 专家解读)?',
    ],
    ifUntreated: {
      metric: 'sentiment_score',
      projectedValue: 0.68,
      timeframe: '5 weeks',
      confidence: 'medium',
      scenarioDescription: '负面情感可能随时间固化在 AI 模型品牌认知中, 5 周后情感分预计降至 0.68, 进入行业末位区间',
    },
    predictedImpact: { metric: 'sentiment_score', projectedChange: 0.09, timeframe: '3-5 weeks', confidence: 'medium', scoreChange: '+1-2 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [
      { engine: '豆包', promptId: 'P-22001', responseId: 'R-6101', snippet: '小棕瓶精华部分敏感肌用户反馈使用后有刺痛感, 建议过敏肌谨慎使用...', capturedAt: '2026-04-08' },
    ],
    impact: '+1-2 PANO',
    timeframe: '需要 2 周内处理',
  },

  /* ─────── P2 · 关注 (composite 4.5-6.4) ─────── */
  {
    id: 'diag-007',
    category: 'product_missing',
    severity: 'P2',
    type: 'product',
    brandId: 'estee-lauder',
    productId: 'prod-anr',
    title: '小棕瓶在"500 元内精华液推荐"品类场景出现率 0%',
    description: '在"500 元内精华液推荐"等 12 条高相关品类 Topic 中, 小棕瓶提及率 0%, 竞品兰蔻小黑瓶 83%。品牌词 + 产品直接查询提及率正常 (95%), 问题出在通用品类场景。',
    engine: 'ChatGPT',
    detected: '2026-04-07',
    focusArea: '通用品类场景产品识别失败',
    direction: '增强产品在品类通用场景中的内容关联性和可发现性',
    readerHints: ['operator'],
    evidence: {
      metric: 'product_mention_rate (category_scope)',
      currentValue: 0,
      previousValue: 0,
      changePercent: 0,
      timeRange: '2026-03-10 → 2026-04-07',
      affectedQueries: ['500元内精华液推荐', '平价抗老精华', '性价比高的精华液'],
      affectedEngines: ['ChatGPT', '豆包'],
    },
    causalChain: {
      triggerMetrics: ['product_category_coverage', 'recommendation_context_match'],
      hypothesizedMechanism: '产品 SKU 信息在"性价比""价格区间"维度缺失标签, AI 在品类场景下无法识别产品适配性; 或是命名/别名识别失败 (产品中文名 vs 英文名 vs 昵称)',
      supportingEvidence: ['resp-7001-list'],
      confidenceLevel: 'medium',
    },
    industryBenchmark: {
      metric: 'category scope mention rate',
      myValue: 0,
      industryMedian: 25,
      industryTop10Avg: 45,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 83,
        keyCharacteristics: ['小黑瓶在"500 元内"品类场景出现率 83%', '官方产品页含完整价格区间 tag'],
      },
      gapAnalysis: { gapToMedian: -25, gapToTop: -83, percentileRank: 5 },
    },
    priorityScore: { impact: 6, ease: 7, urgency: 5, composite: 6.0, rankWithinPeriod: 7 },
    timeSeries: {
      firstObservedAt: '2026-03-10',
      lastUpdatedAt: '2026-04-07',
      trendStatus: 'persisting',
      ageInDays: 28,
      severityHistory: [{ date: '2026-03-10', severity: 'P2' }],
    },
    anchorQuestions: [
      '该 Topic 的 Top 产品是什么? 我方产品在同 Topic 是否有内容?',
      '是否是产品命名 / 别名识别失败 (英文名 vs 中文名 vs 口语化名)?',
      '官方产品页是否含价格区间 / 性价比相关标签?',
      '近期有无产品信息更新计划可借机补齐 schema?',
    ],
    ifUntreated: {
      metric: 'product_category_coverage',
      projectedValue: 0,
      timeframe: 'persistent',
      confidence: 'high',
      scenarioDescription: '若不干预将长期缺席品类场景推荐, 失去非品牌词搜索流量; 竞品兰蔻将进一步巩固该品类心智',
    },
    predictedImpact: { metric: 'product_mention_rate', projectedChange: 30, timeframe: '4-6 weeks', confidence: 'medium', scoreChange: '+2-3 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [],
    impact: '+2-3 PANO',
    timeframe: '需要 3 周内处理',
  },

  {
    id: 'diag-008',
    category: 'new_entrant',
    severity: 'P2',
    type: 'industry',
    title: '国货新锐"观夏"在国产高端香水类首次进入 Top 10',
    description: '过去 30 天, 观夏在"国产高端香水""中国风香水"类 Topic 中从 0 跃升至 SoV 4%, 增速行业第 1。可能分流雅诗兰黛等国际品牌在"高端香水推荐"类 8-15% 的 SoV。',
    engine: 'ChatGPT',
    detected: '2026-04-06',
    focusArea: '新竞争者入场 + 细分心智抢占',
    direction: '监测新入场品牌增长趋势, 评估是否威胁核心品类',
    readerHints: ['manager'],
    decisionPrompt: '是否在下 2-4 周加强对观夏的监测并评估品类防御必要性?',
    evidence: {
      metric: 'new_entrant_sov',
      currentValue: 4,
      previousValue: 0,
      changePercent: 400,
      timeRange: '2026-03-06 → 2026-04-06',
      affectedQueries: ['国产高端香水', '中国风香水推荐'],
      affectedEngines: ['ChatGPT', '豆包'],
    },
    causalChain: {
      triggerMetrics: ['new_brand_detection', 'topic_share_delta'],
      hypothesizedMechanism: '观夏近期与多名美妆博主联动内容被 ChatGPT 索引, 快速建立"国产高端""中国风"细分心智',
      supportingEvidence: ['new-entrant-obsidian-audit'],
      confidenceLevel: 'high',
    },
    industryBenchmark: {
      metric: 'new_entrant_growth_rate',
      myValue: 0,
      industryMedian: 1,
      industryTop10Avg: 2,
      topCompetitor: {
        brandId: 'obsidian',
        brandName: '观夏',
        value: 4,
        keyCharacteristics: ['SoV 30 天从 0 升至 4%', 'PANO Score 从 F(0) 升至 C(58)'],
      },
      gapAnalysis: { gapToMedian: -1, gapToTop: -4, percentileRank: 10 },
    },
    priorityScore: { impact: 5, ease: 4, urgency: 6, composite: 5.0, rankWithinPeriod: 8 },
    timeSeries: {
      firstObservedAt: '2026-03-20',
      lastUpdatedAt: '2026-04-06',
      trendStatus: 'new',
      ageInDays: 17,
      severityHistory: [{ date: '2026-03-20', severity: 'P2' }],
    },
    anchorQuestions: [
      '新竞品的起势内容是什么? (主要分发渠道 / 内容类型)',
      '它抢占了我方哪些主题份额? 是否是核心品类?',
      '核心品牌在同主题的内容库存和引用强度如何?',
      '观察窗口需要多长? 4 周 / 8 周的触发条件是什么?',
    ],
    ifUntreated: {
      metric: 'high_end_fragrance_sov',
      projectedValue: -8,
      timeframe: '12 weeks',
      confidence: 'low',
      scenarioDescription: '若观夏维持增速, 3 个月可能稀释高端香水类 8-15% SoV; 该细分心智一旦固化, 再争夺难度指数上升',
    },
    predictedImpact: { metric: 'defensive_content_coverage', projectedChange: 15, timeframe: '8-12 weeks', confidence: 'low', scoreChange: '+1-2 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [],
    impact: '+1-2 PANO',
    timeframe: '需要 4 周内观察',
  },

  {
    id: 'diag-009',
    category: 'visibility_decline',
    severity: 'P2',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '雅诗兰黛在豆包引擎 SoV 微降 2pt, 趋势性下滑信号',
    description: '豆包引擎近 4 周 SoV 从 16% 微降至 14% (-2pt), 单周看仍在正常波动, 但连续 3 周同向下滑构成趋势信号。主要在"高端抗老精华"主题。',
    engine: '豆包',
    detected: '2026-04-05',
    focusArea: '豆包引擎趋势性 SoV 下滑',
    direction: '观察豆包引擎内容覆盖 / 引用强度, 判断是否需要针对性补强',
    readerHints: ['operator'],
    evidence: {
      metric: 'sov (doubao)',
      currentValue: 14,
      previousValue: 16,
      changePercent: -12.5,
      timeRange: '2026-03-09 → 2026-04-05',
      affectedQueries: ['高端抗老精华推荐'],
      affectedEngines: ['豆包'],
    },
    causalChain: {
      triggerMetrics: ['sov_trend_delta_3week'],
      hypothesizedMechanism: '可能是竞品在豆包的内容投放增强 / 也可能是豆包模型对高端类目评价逻辑调整',
      supportingEvidence: ['sov-doubao-trend-W11-W15'],
      confidenceLevel: 'low',
      alternativeHypotheses: ['属随机波动, 非趋势性问题 (需再监测 2 周验证)'],
    },
    industryBenchmark: {
      metric: 'sov (doubao) 趋势',
      myValue: 14,
      industryMedian: 13,
      industryTop10Avg: 15,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 17,
        keyCharacteristics: ['豆包 SoV 稳步上升 +1pt / 周'],
      },
      gapAnalysis: { gapToMedian: 1, gapToTop: -3, percentileRank: 58 },
    },
    priorityScore: { impact: 4, ease: 6, urgency: 4, composite: 4.6, rankWithinPeriod: 9 },
    timeSeries: {
      firstObservedAt: '2026-03-15',
      lastUpdatedAt: '2026-04-05',
      trendStatus: 'growing',
      ageInDays: 22,
      severityHistory: [{ date: '2026-03-15', severity: 'P3' }, { date: '2026-04-05', severity: 'P2' }],
    },
    anchorQuestions: [
      '豆包引擎的内容来源结构与 ChatGPT 差异在哪?',
      '过去 4 周竞品在豆包上的内容投放数据能否拉到?',
      '是否存在豆包模型升级 / 算法调整导致的非内容侧因素?',
      '再观察 2 周是否必要? 如需要, 监测什么指标作为触发条件?',
    ],
    ifUntreated: {
      metric: 'sov (doubao)',
      projectedValue: 11,
      timeframe: '8 weeks',
      confidence: 'low',
      scenarioDescription: '若趋势成立, 8 周后豆包 SoV 可能降至 11%, 跌破行业中位; 但若仅是波动, 则无需过度干预',
    },
    predictedImpact: { metric: 'sov', projectedChange: 2, timeframe: '4-6 weeks', confidence: 'low', scoreChange: '+0-2 PANO' },
    relatedDiagnostics: { derivedFrom: [], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [],
    impact: '+0-2 PANO',
    timeframe: '需要持续观察',
  },

  /* ─────── P3 · 信息 (composite < 4.5) ─────── */
  {
    id: 'diag-010',
    category: 'sentiment_shift',
    severity: 'P3',
    type: 'brand',
    brandId: 'estee-lauder',
    title: '雅诗兰黛"老牌""经典"中性标签轻度增加, 叙事防御信号',
    description: 'ChatGPT / 豆包 中"老牌""经典""稳定"等中性偏褒义关键词 +15 次 (较上月 +22%)。单独看非负面, 但结合 diag-002 的 narrative drift, 构成叙事固化的早期信号。',
    engine: 'ChatGPT',
    detected: '2026-04-04',
    focusArea: '中性关键词累积 → 品牌形象固化早期信号',
    direction: '观察中性标签累积趋势, 判断是否需要叙事主动校准',
    readerHints: ['operator', 'branding'],
    evidence: {
      metric: 'neutral_keyword_frequency',
      currentValue: 83,
      previousValue: 68,
      changePercent: 22,
      timeRange: '2026-03-05 → 2026-04-04',
      affectedQueries: ['雅诗兰黛品牌印象'],
      affectedEngines: ['ChatGPT', '豆包'],
    },
    causalChain: {
      triggerMetrics: ['neutral_keyword_frequency'],
      hypothesizedMechanism: '缺乏新鲜叙事 + 存量内容偏"经典稳定"定位, AI 倾向选择此类标签描述品牌',
      supportingEvidence: [],
      confidenceLevel: 'low',
    },
    industryBenchmark: {
      metric: 'neutral/negative keyword freshness',
      myValue: 72,
      industryMedian: 75,
      industryTop10Avg: 80,
      topCompetitor: {
        brandId: 'lancome',
        brandName: '兰蔻',
        value: 85,
        keyCharacteristics: ['近 4 周中性关键词稳定', '新鲜叙事输出规律'],
      },
      gapAnalysis: { gapToMedian: -3, gapToTop: -8, percentileRank: 55 },
    },
    priorityScore: { impact: 3, ease: 4, urgency: 3, composite: 3.2, rankWithinPeriod: 10 },
    timeSeries: {
      firstObservedAt: '2026-03-05',
      lastUpdatedAt: '2026-04-04',
      trendStatus: 'growing',
      ageInDays: 30,
      severityHistory: [{ date: '2026-03-05', severity: 'P3' }],
    },
    anchorQuestions: [
      '中性关键词的上升是否伴随负面关键词的同步增加?',
      '是否可通过新品 / 新叙事内容覆盖"经典"标签?',
      '需要等 P0/P1 诊断处理后再复盘本条, 还是现在并入叙事校准?',
    ],
    ifUntreated: {
      metric: 'brand_persona_freshness',
      projectedValue: 55,
      timeframe: '12 weeks',
      confidence: 'low',
      scenarioDescription: '若中性标签持续累积, 可能与 diag-002 叙事漂移合流, 加速品牌人设固化',
    },
    predictedImpact: { metric: 'neutral_keyword_frequency', projectedChange: -15, timeframe: '8 weeks', confidence: 'low', scoreChange: '+0-1 PANO' },
    relatedDiagnostics: { derivedFrom: ['diag-002'], childDiagnostics: [], historicalSimilar: [] },
    responseSamples: [],
    impact: '+0-1 PANO',
    timeframe: '持续观察',
  },
];

// Topics: 监测主题 (Planner 从品牌图谱 Bottom-Up 生成)
// Pipeline: Topic → Prompt (×Intent) → Query (×Profile) → Response
// ── Topics: PRD 4.2.5 四层 Pipeline 数据 ──
export const TOPICS = [
  {
    id: 'topic-001',
    name: '小棕瓶评价',
    dimension: '产品',        // PRD: 品类/品牌/产品/竞品
    brand: '雅诗兰黛',
    source: 'Planner',
    promptCount: 8,
    queryCount: 48,
    responseCount: 144,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'key',          // key / normal / ignore
  },
  {
    id: 'topic-002',
    name: '精华液对比推荐',
    dimension: '品类',
    brand: null,
    source: 'Planner',
    promptCount: 12,
    queryCount: 72,
    responseCount: 216,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'normal',
  },
  {
    id: 'topic-003',
    name: '雅诗兰黛抗衰方案',
    dimension: '品牌',
    brand: '雅诗兰黛',
    source: 'Planner',
    promptCount: 6,
    queryCount: 36,
    responseCount: 108,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'key',
  },
  {
    id: 'topic-004',
    name: '高端面霜性价比',
    dimension: '品类',
    brand: null,
    source: 'Planner',
    promptCount: 10,
    queryCount: 60,
    responseCount: 180,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'normal',
  },
  {
    id: 'topic-005',
    name: '兰蔻小黑瓶 vs 雅诗兰黛',
    dimension: '竞品',
    brand: '兰蔻',
    source: 'Planner',
    promptCount: 4,
    queryCount: 24,
    responseCount: 72,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'normal',
  },
  {
    id: 'topic-006',
    name: '神仙水成分与功效',
    dimension: '产品',
    brand: 'SK-II',
    source: 'Planner',
    promptCount: 6,
    queryCount: 36,
    responseCount: 108,
    lastCollected: '3h ago',
    status: 'active',
    priority: 'normal',
  },
  {
    id: 'topic-007',
    name: '抗衰老精华选购指南',
    dimension: '品类',
    brand: null,
    source: 'Planner',
    promptCount: 8,
    queryCount: 48,
    responseCount: 144,
    lastCollected: '2h ago',
    status: 'active',
    priority: 'key',
  },
  {
    id: 'topic-008',
    name: '护肤品安全性评估',
    dimension: '品类',
    brand: null,
    source: 'Planner',
    promptCount: 4,
    queryCount: 24,
    responseCount: 72,
    lastCollected: '3h ago',
    status: 'active',
    priority: 'normal',
  },
];

// ── Prompts: PRD 4.2.5 第2层 ──
export const PROMPTS = {
  'topic-001': [
    { id: 'pr-001-1', text: '小棕瓶精华怎么样？值得买吗', intent: 'informational', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-2', text: '小棕瓶和小黑瓶哪个更值得买？', intent: 'commercial', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-3', text: '雅诗兰黛小棕瓶在哪买最便宜', intent: 'transactional', queryCount: 3, coverage: '50%' },
    { id: 'pr-001-4', text: '小棕瓶精华的成分是什么', intent: 'informational', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-5', text: '推荐一款抗衰精华，小棕瓶好用吗', intent: 'commercial', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-6', text: '小棕瓶精华适合什么年龄段', intent: 'informational', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-7', text: '小棕瓶精华液使用方法和顺序', intent: 'navigational', queryCount: 6, coverage: '100%' },
    { id: 'pr-001-8', text: '小棕瓶精华有假货吗，怎么辨别', intent: 'informational', queryCount: 6, coverage: '100%' },
  ],
  'topic-005': [
    { id: 'pr-005-1', text: '小黑瓶和小棕瓶的成分有什么区别？', intent: 'informational', queryCount: 6, coverage: '100%' },
    { id: 'pr-005-2', text: '小黑瓶和小棕瓶哪个抗衰效果更好？', intent: 'commercial', queryCount: 6, coverage: '100%' },
    { id: 'pr-005-3', text: '兰蔻小黑瓶好还是雅诗兰黛小棕瓶好', intent: 'commercial', queryCount: 6, coverage: '100%' },
    { id: 'pr-005-4', text: '25岁抗初老用小黑瓶还是小棕瓶', intent: 'commercial', queryCount: 6, coverage: '100%' },
  ],
};

// ── Queries: PRD 4.2.5 第3层 ──
export const QUERIES = {
  'pr-001-2': [
    { id: 'q-001-2-1', engine: 'ChatGPT', profile: '25岁女性,一线', time: '2026-04-15 02:30', status: 'success', brandMentions: 3 },
    { id: 'q-001-2-2', engine: 'ChatGPT', profile: '35岁女性,二线', time: '2026-04-15 02:31', status: 'success', brandMentions: 4 },
    { id: 'q-001-2-3', engine: '豆包', profile: '25岁女性,一线', time: '2026-04-15 02:35', status: 'success', brandMentions: 2 },
    { id: 'q-001-2-4', engine: '豆包', profile: '35岁女性,二线', time: '2026-04-15 02:36', status: 'success', brandMentions: 3 },
    { id: 'q-001-2-5', engine: 'DeepSeek', profile: '25岁女性,一线', time: '2026-04-15 02:40', status: 'success', brandMentions: 5 },
    { id: 'q-001-2-6', engine: 'DeepSeek', profile: '35岁女性,二线', time: '2026-04-15 02:41', status: 'failed', brandMentions: 0 },
  ],
};

// ── Responses: PRD 4.2.5 第4层 ──
export const RESPONSES = {
  'q-001-2-1': {
    id: 'resp-001-2-1',
    engine: 'ChatGPT',
    profile: '25岁女性,一线',
    prompt: '小棕瓶和小黑瓶哪个更值得买？',
    time: '2026-04-15 02:30',
    rawText: `小棕瓶（雅诗兰黛特润修护精华）和小黑瓶（兰蔻精华肌底液）都是非常经典的抗衰精华产品。以下从几个维度帮你对比：

**功效对比**
- 小棕瓶：主打修护 + 抗氧化，核心成分二裂酵母发酵产物，适合熬夜后修复、抗初老
- 小黑瓶：主打微生态平衡 + 肌底修护，核心成分二裂酵母发酵产物溶胞物，适合肌肤状态不稳定时使用

**适合人群**
- 小棕瓶更适合 25-35 岁、需要日常抗初老的用户
- 小黑瓶更适合肌肤状态不稳定、需要肌底调理的用户

**价格**
- 小棕瓶 50ml 约 590 元
- 小黑瓶 50ml 约 560 元

综合来看，如果你更关注抗老修护，推荐小棕瓶；如果想改善整体肤质，小黑瓶是更好的选择。`,
    analysis: {
      brands: [
        { name: '雅诗兰黛', position: '#1', sentiment: '正面', sentimentScore: 0.78, recommended: true },
        { name: '兰蔻', position: '#2', sentiment: '正面', sentimentScore: 0.72, recommended: true },
      ],
      products: [
        { name: '小棕瓶', brand: '雅诗兰黛', sentiment: '正面', keywords: ['修护', '抗氧化', '抗初老'] },
        { name: '小黑瓶', brand: '兰蔻', sentiment: '正面', keywords: ['微生态', '肌底修护'] },
      ],
      // citations 字段对齐 PRD §4.2.6.A AiCitation 模型
      citations: [
        { index: 1, sourceDomain: 'esteelauder.com.cn', sourceTitle: '小棕瓶精华液 | 雅诗兰黛官网', sourceUrl: 'https://esteelauder.com.cn/product/anr', engineRaw: 'chatgpt', authorityTier: 1, authorityConfidence: 1.0, brandsAttributed: ['estee-lauder'], productsAttributed: ['elixir-mini'] },
        { index: 2, sourceDomain: 'beauty.pclady.com.cn', sourceTitle: '小棕瓶精华深度评测报告', sourceUrl: 'https://beauty.pclady.com.cn/review/anr', engineRaw: 'chatgpt', authorityTier: 2, authorityConfidence: 0.85, brandsAttributed: ['estee-lauder'], productsAttributed: ['elixir-mini'] },
        { index: 3, sourceDomain: 'xiaohongshu.com', sourceTitle: '小棕瓶vs小黑瓶真实测评', sourceUrl: 'https://xiaohongshu.com/discovery/item/abc123', engineRaw: 'chatgpt', authorityTier: 3, authorityConfidence: 0.88, brandsAttributed: ['estee-lauder', 'lancome'], productsAttributed: ['elixir-mini', 'genifique-eye'] },
      ],
      wordCount: 287,
      recommendationType: '条件性推荐',
    },
  },
  'q-001-2-3': {
    id: 'resp-001-2-3',
    engine: '豆包',
    profile: '25岁女性,一线',
    prompt: '小棕瓶和小黑瓶哪个更值得买？',
    time: '2026-04-15 02:35',
    rawText: `这两款都是经典精华，各有千秋。小棕瓶主打抗老修护，小黑瓶主打肌底调理。25岁的话其实两款都可以，看你更想解决什么问题。如果经常熬夜、皮肤暗沉，小棕瓶更适合；如果换季容易敏感、肤质不稳定，小黑瓶更好。价格差不多，小棕瓶稍贵一点。`,
    analysis: {
      brands: [
        { name: '雅诗兰黛', position: '#1', sentiment: '正面', sentimentScore: 0.71, recommended: true },
        { name: '兰蔻', position: '#2', sentiment: '正面', sentimentScore: 0.68, recommended: true },
      ],
      products: [
        { name: '小棕瓶', brand: '雅诗兰黛', sentiment: '正面', keywords: ['抗老修护', '熬夜修复'] },
        { name: '小黑瓶', brand: '兰蔻', sentiment: '正面', keywords: ['肌底调理', '换季适用'] },
      ],
      // citations 字段对齐 PRD §4.2.6.A AiCitation 模型 (豆包 DOM 抓取 .reference-card)
      citations: [
        { index: 1, sourceDomain: 'zhihu.com', sourceTitle: '雅诗兰黛值不值得买？', sourceUrl: 'https://zhihu.com/question/12345', engineRaw: 'doubao', authorityTier: 3, authorityConfidence: 0.82, brandsAttributed: ['estee-lauder'], productsAttributed: ['elixir-mini'] },
        { index: 2, sourceDomain: 'xiaohongshu.com', sourceTitle: '25岁选精华指南', sourceUrl: 'https://xiaohongshu.com/discovery/item/def456', engineRaw: 'doubao', authorityTier: 3, authorityConfidence: 0.88, brandsAttributed: ['estee-lauder', 'lancome'], productsAttributed: [] },
      ],
      wordCount: 142,
      recommendationType: '条件性推荐',
    },
  },
};

export const ENGINES = [
  {
    name: 'ChatGPT',
    score: 78,
    mentionRate: 0.72,
    color: 'var(--color-engine-chatgpt)'
  },
  {
    name: '豆包',
    score: 84,
    mentionRate: 0.81,
    color: 'var(--color-engine-doubao)'
  },
  {
    name: 'DeepSeek',
    score: 71,
    mentionRate: 0.65,
    color: 'var(--color-engine-deepseek)'
  }
];

/* ─────────────────────────────────────────────────────────────
   ProfileGroup — PRD §4.2.3a (2026-04-16)
   ─────────────────────────────────────────────────────────────
   7 MVP 预置画像组. 在生产中由 Session 2 seed script 生成,
   原型阶段在前端 mock; 字段命名严格对齐 PRD §4.2.3a interface.

   Sample count 用于演示 §4.2.3a 中"小样本兜底": 当 sampleCount < 50
   触发 ProfileGroupFilter 的黄色降级条 + 数据卡片灰化.
*/
export const PROFILE_GROUPS = [
  {
    id: 'all',
    nameZh: '全部 Profile',
    nameEn: 'All Profiles',
    description: '默认聚合基线, 不做画像切片',
    descriptionEn: 'Default aggregation baseline; no audience slicing',
    filterRules: {},
    isDefault: true,
    sampleCount: 4280,
  },
  {
    id: 'young_female_tier1',
    nameZh: '一线年轻女性',
    nameEn: 'Young Female · Tier 1',
    description: '18-34 岁 / 女性 / 一线城市',
    descriptionEn: 'Female · Age 18-34 · Tier-1 cities',
    filterRules: {
      gender: 'F',
      ageBandIn: ['18-24', '25-34'],
      regionIn: ['tier1'],
    },
    isDefault: false,
    sampleCount: 612,
  },
  {
    id: 'mid_age_female_tier23',
    nameZh: '下沉中年女性',
    nameEn: 'Mid-age Female · Tier 2-3',
    description: '35-44 岁 / 女性 / 下沉市场',
    descriptionEn: 'Female · Age 35-44 · Tier-2/3 cities',
    filterRules: {
      gender: 'F',
      ageBandIn: ['35-44'],
      regionIn: ['tier2-3'],
    },
    isDefault: false,
    sampleCount: 198,
  },
  {
    id: 'male_tier1',
    nameZh: '一线男性',
    nameEn: 'Male · Tier 1',
    description: '男性 / 一线城市 / 全年龄段',
    descriptionEn: 'Male · Tier-1 cities · All ages',
    filterRules: {
      gender: 'M',
      regionIn: ['tier1'],
    },
    isDefault: false,
    sampleCount: 87,
  },
  {
    id: 'price_sensitive',
    nameZh: '价格敏感型',
    nameEn: 'Price-sensitive',
    description: '上下文含"性价比 / 平替 / 便宜"关键词',
    descriptionEn: 'Context contains "value", "dupe", "affordable"',
    filterRules: {
      contextKeywords: ['性价比', '平替', '便宜', 'value', 'dupe', 'affordable'],
    },
    isDefault: false,
    sampleCount: 326,
  },
  {
    id: 'zh_chatgpt',
    nameZh: '中文 ChatGPT 用户',
    nameEn: 'Chinese ChatGPT users',
    description: '中文 Prompt × ChatGPT 引擎',
    descriptionEn: 'Chinese-language prompts on ChatGPT',
    filterRules: {
      promptLanguageIn: ['zh-CN'],
      enginesIn: ['ChatGPT'],
    },
    isDefault: false,
    sampleCount: 41, // 故意 < 50, 演示降级
  },
  {
    id: 'en_chatgpt',
    nameZh: '英文 ChatGPT 用户',
    nameEn: 'English ChatGPT users',
    description: '英文 Prompt × ChatGPT 引擎',
    descriptionEn: 'English-language prompts on ChatGPT',
    filterRules: {
      promptLanguageIn: ['en-US'],
      enginesIn: ['ChatGPT'],
    },
    isDefault: false,
    sampleCount: 156,
  },
];

/** 阈值: 见 PRD §4.2.3a "聚合语义" — 单组 ≥50 Queries / 30 天 才显示指标 */
export const PROFILE_GROUP_SAMPLE_THRESHOLD = 50;

/**
 * Mock 实现: 根据 group id 返回当前选中时间/引擎下的样本量.
 * 生产对应 `GET /api/v1/profile-groups?range=30d&engines=...` 返回的
 * `{ id, sampleCount, sufficient, fallback }` 字段.
 */
export function getProfileGroupSampleCount(id) {
  const g = PROFILE_GROUPS.find((p) => p.id === id);
  return g ? g.sampleCount : 0;
}

/** 是否达到出指标阈值 (PRD §4.2.3a) */
export function hasEnoughSamplesInGroup(id) {
  return getProfileGroupSampleCount(id) >= PROFILE_GROUP_SAMPLE_THRESHOLD;
}

// Generate 30 days of trend data with natural variation
export const TREND_DATA = Array.from({ length: 30 }, (_, index) => {
  const day = index + 1;
  const dayOfWeek = (index % 7);

  // Create natural sinusoidal variation
  const baseMentionRate = 72 + Math.sin(day / 5) * 10;
  const baseSentiment = 0.68 + Math.sin(day / 7 + 1) * 0.08;
  const basePanoScore = 75 + Math.sin(day / 4.5) * 8;
  const baseCompetitorScore = 70 + Math.sin(day / 6) * 6;

  // Add some randomness
  const noise = () => (Math.random() - 0.5) * 4;

  return {
    name: `${day}日`,
    day,
    mentionRate: Math.round((baseMentionRate + noise()) * 10) / 10,
    sentiment: Math.round((Math.max(0.55, Math.min(0.8, baseSentiment + (Math.random() - 0.5) * 0.08))) * 100) / 100,
    panoScore: Math.round(Math.max(65, Math.min(85, basePanoScore + noise()))),
    competitorScore: Math.round(Math.max(62, Math.min(78, baseCompetitorScore + noise())))
  };
});

// SoV 分片: 覆盖 Top 8 品牌, 其他 ≤ 10% 避免灰块视觉吞噬真实品牌洞察
export const SOV_DATA = [
  { name: '香奈儿', nameEn: 'Chanel', value: 20, color: 'var(--color-accent)' },
  { name: '雅诗兰黛', nameEn: 'Estée Lauder', value: 17, color: 'var(--color-chart-7)' },
  { name: '兰蔻', nameEn: 'Lancôme', value: 14, color: 'var(--color-chart-6)' },
  { name: '迪奥', nameEn: 'Dior', value: 12, color: 'var(--color-chart-3)' },
  { name: 'SK-II', nameEn: 'SK-II', value: 10, color: 'var(--color-danger)' },
  { name: '海蓝之谜', nameEn: 'La Mer', value: 8, color: 'var(--color-accent-2)' },
  { name: '欧莱雅', nameEn: "L'Oréal", value: 7, color: 'var(--color-chart-4)' },
  { name: '资生堂', nameEn: 'Shiseido', value: 5, color: 'var(--color-chart-2)' },
  { name: '其他', nameEn: 'Others', value: 7, color: 'var(--color-chart-line-grid)' }
];

// ── Metric Breakdown Tab Data ──

// Mention rate trend by engine (30 days)
export const MENTION_TREND_BY_ENGINE = Array.from({ length: 30 }, (_, i) => {
  const day = i + 1;
  const noise = () => (Math.random() - 0.5) * 6;
  return {
    name: `${Math.ceil(day / 30 * 30)}日`,
    chatgpt: Math.round(Math.max(20, Math.min(50, 35 + Math.sin(day / 5) * 8 + noise()))),
    doubao: Math.round(Math.max(25, Math.min(55, 42 + Math.sin(day / 4) * 7 + noise()))),
    deepseek: Math.round(Math.max(15, Math.min(45, 28 + Math.sin(day / 6) * 9 + noise()))),
  };
});

// Mention position distribution
export const MENTION_POSITION_DATA = [
  { name: '首位提及', value: 28, color: 'var(--color-accent)' },
  { name: '前3位', value: 35, color: 'var(--color-chart-7)' },
  { name: '中段', value: 22, color: 'var(--color-chart-6)' },
  { name: '末段', value: 15, color: 'var(--color-chart-axis-text)' },
];

// Competitor mention matrix: brand × engine
export const COMPETITOR_MENTION_MATRIX = [
  { brand: '雅诗兰黛', chatgpt: 34.2, chatgptChange: '+2.1', doubao: 41.5, doubaoChange: '+3.8', deepseek: 28.7, deepseekChange: '+1.2' },
  { brand: '香奈儿', chatgpt: 38.6, chatgptChange: '+1.5', doubao: 36.2, doubaoChange: '-0.8', deepseek: 32.4, deepseekChange: '+2.3' },
  { brand: '兰蔻', chatgpt: 29.1, chatgptChange: '-1.2', doubao: 33.8, doubaoChange: '+2.1', deepseek: 25.6, deepseekChange: '-0.5' },
  { brand: 'SK-II', chatgpt: 22.4, chatgptChange: '+0.8', doubao: 26.1, doubaoChange: '+1.5', deepseek: 19.3, deepseekChange: '+0.3' },
  { brand: '迪奥', chatgpt: 25.7, chatgptChange: '+1.1', doubao: 30.4, doubaoChange: '+0.6', deepseek: 22.8, deepseekChange: '-0.7' },
  { brand: '欧莱雅', chatgpt: 20.3, chatgptChange: '-0.5', doubao: 24.6, doubaoChange: '+1.9', deepseek: 18.2, deepseekChange: '+0.4' },
];

// Sentiment trend by engine (30 days)
export const SENTIMENT_TREND_BY_ENGINE = Array.from({ length: 30 }, (_, i) => {
  const day = i + 1;
  const noise = () => (Math.random() - 0.5) * 0.08;
  return {
    name: `${day}日`,
    chatgpt: Math.round(Math.max(0.5, Math.min(0.95, 0.72 + Math.sin(day / 5) * 0.06 + noise())) * 100) / 100,
    doubao: Math.round(Math.max(0.5, Math.min(0.95, 0.78 + Math.sin(day / 4) * 0.05 + noise())) * 100) / 100,
    deepseek: Math.round(Math.max(0.5, Math.min(0.95, 0.68 + Math.sin(day / 6) * 0.07 + noise())) * 100) / 100,
  };
});

// Sentiment distribution per engine (positive / neutral / negative)
export const SENTIMENT_DISTRIBUTION = [
  { engine: 'ChatGPT', positive: 62, neutral: 28, negative: 10 },
  { engine: '豆包', positive: 68, neutral: 24, negative: 8 },
  { engine: 'DeepSeek', positive: 55, neutral: 30, negative: 15 },
];

// Sentiment keywords
export const SENTIMENT_KEYWORDS = {
  positive: [
    { word: '高品质', weight: 92 }, { word: '口碑好', weight: 85 },
    { word: '效果显著', weight: 80 }, { word: '值得推荐', weight: 78 },
    { word: '经典', weight: 75 }, { word: '持久', weight: 70 },
    { word: '温和', weight: 68 }, { word: '高端', weight: 65 },
    { word: '口碑佳', weight: 60 }, { word: '性价比', weight: 55 },
  ],
  negative: [
    { word: '价格高', weight: 88 }, { word: '过敏', weight: 72 },
    { word: '效果一般', weight: 65 }, { word: '不适合', weight: 60 },
    { word: '假货多', weight: 55 }, { word: '刺激', weight: 50 },
  ],
};

// Citation trend by engine (30 days)
export const CITATION_TREND_BY_ENGINE = Array.from({ length: 30 }, (_, i) => {
  const day = i + 1;
  const noise = () => Math.round((Math.random() - 0.5) * 8);
  return {
    name: `${day}日`,
    chatgpt: Math.max(5, Math.round(18 + Math.sin(day / 5) * 6 + noise())),
    doubao: Math.max(3, Math.round(12 + Math.sin(day / 4) * 5 + noise())),
    deepseek: Math.max(2, Math.round(10 + Math.sin(day / 6) * 4 + noise())),
  };
});

// Top cited domains — 字段对齐 PRD §4.2.6 (AiCitation + CitationDomainAuthority)
// authorityTier: 0 未知 / 1 官方 / 2 权威媒体 / 3 垂直/KOL / 4 UGC
// authorityConfidence: [0,1] Tier 归类置信度
// brandsAttributed: 引用归属的品牌 ID 数组 (3 级归因: official_domain > co_occurrence > text_match)
export const TOP_CITED_DOMAINS = [
  { domain: 'xiaohongshu.com', citations: 156, share: 24.2, authorityTier: 3, authorityConfidence: 0.88, brandsAttributed: ['estee-lauder', 'lancome', 'sk-ii'] },
  { domain: 'esteelauder.com.cn', citations: 98, share: 15.2, authorityTier: 1, authorityConfidence: 1.00, brandsAttributed: ['estee-lauder'] },
  { domain: 'zhihu.com', citations: 87, share: 13.5, authorityTier: 3, authorityConfidence: 0.82, brandsAttributed: ['estee-lauder', 'lancome'] },
  { domain: 'douyin.com', citations: 72, share: 11.2, authorityTier: 3, authorityConfidence: 0.75, brandsAttributed: ['estee-lauder'] },
  { domain: 'weibo.com', citations: 54, share: 8.4, authorityTier: 4, authorityConfidence: 0.70, brandsAttributed: ['estee-lauder', 'dior'] },
  { domain: 'tmall.com', citations: 48, share: 7.5, authorityTier: 4, authorityConfidence: 0.65, brandsAttributed: ['estee-lauder', 'sk-ii'] },
  { domain: 'beauty.pclady.com.cn', citations: 36, share: 5.6, authorityTier: 2, authorityConfidence: 0.85, brandsAttributed: ['estee-lauder'] },
  { domain: 'others', citations: 93, share: 14.4, authorityTier: 0, authorityConfidence: 0.0, brandsAttributed: [] },
];

// Citation source composition
export const CITATION_SOURCE_COMPOSITION = [
  { name: '自有域名', value: 18, color: 'var(--color-accent)' },
  { name: '竞品域名', value: 32, color: 'var(--color-danger)' },
  { name: '第三方', value: 50, color: 'var(--color-chart-axis-text)' },
];

// ── Detail Lists (明细列表) ──

// Mention detail list
export const MENTION_DETAIL_LIST = [
  { id: 'md-1', topic: '抗衰老精华推荐', prompt: '推荐几款好用的抗衰老精华液', summary: '推荐了雅诗兰黛小棕瓶、兰蔻小黑瓶和SK-II神仙水，小棕瓶排首位', position: '首位', engine: 'ChatGPT', time: '2026-04-14 09:23' },
  { id: 'md-2', topic: '美妆品牌对比', prompt: '雅诗兰黛和兰蔻哪个更好', summary: '从品牌历史、产品线、价格等方面对比，雅诗兰黛在抗衰领域更强', position: '首位', engine: '豆包', time: '2026-04-14 08:45' },
  { id: 'md-3', topic: '护肤品排行榜', prompt: '2026年最好的护肤品品牌排行', summary: '列出十大品牌排行，雅诗兰黛排第3位，前两名为香奈儿和迪奥', position: '前3', engine: 'DeepSeek', time: '2026-04-14 07:12' },
  { id: 'md-4', topic: '精华液成分分析', prompt: '小棕瓶精华的主要成分和功效', summary: '详细分析了二裂酵母、透明质酸等成分，正面评价为主', position: '首位', engine: 'ChatGPT', time: '2026-04-13 22:30' },
  { id: 'md-5', topic: '敏感肌护肤', prompt: '敏感肌适合用什么品牌的护肤品', summary: '推荐了理肤泉、雅漾为主，雅诗兰黛被提及但排在第5位', position: '中段', engine: '豆包', time: '2026-04-13 20:15' },
  { id: 'md-6', topic: '高端护肤推荐', prompt: '预算2000以内的高端护肤品推荐', summary: '推荐了海蓝之谜、雅诗兰黛、SK-II等，雅诗兰黛排第2', position: '前3', engine: 'DeepSeek', time: '2026-04-13 18:42' },
  { id: 'md-7', topic: '精华液效果对比', prompt: '小棕瓶和小黑瓶哪个效果更好', summary: '从成分、质地、适用肤质等对比，认为小棕瓶抗衰更好，小黑瓶修复更好', position: '首位', engine: 'ChatGPT', time: '2026-04-13 16:08' },
  { id: 'md-8', topic: '护肤品安全性', prompt: '雅诗兰黛产品有没有有害成分', summary: '分析了产品成分安全性，整体评价安全，提到部分人可能对香精过敏', position: '首位', engine: '豆包', time: '2026-04-13 14:55' },
];

// Sentiment detail list
export const SENTIMENT_DETAIL_LIST = [
  { id: 'sd-1', topic: '品牌口碑评价', prompt: '雅诗兰黛品牌口碑怎么样', summary: '"雅诗兰黛是全球知名的高端护肤品牌，以其卓越的抗衰老产品线闻名..."', label: '正面', keywords: ['高端', '卓越', '知名'], engine: 'ChatGPT', time: '2026-04-14 10:15' },
  { id: 'sd-2', topic: '产品使用体验', prompt: '小棕瓶精华使用感受如何', summary: '"质地轻薄易吸收，使用后皮肤明显更有光泽，但部分敏感肌用户反馈有刺激感..."', label: '中性', keywords: ['轻薄', '光泽', '刺激感'], engine: '豆包', time: '2026-04-14 09:30' },
  { id: 'sd-3', topic: '价格评价', prompt: '雅诗兰黛性价比高吗', summary: '"相对于价格，部分用户认为效果不如预期，尤其与平价替代品相比优势不明显..."', label: '负面', keywords: ['价格高', '不如预期', '优势不明显'], engine: 'DeepSeek', time: '2026-04-14 08:20' },
  { id: 'sd-4', topic: '抗衰效果评测', prompt: '小棕瓶真的能抗衰老吗', summary: '"经过长期使用，小棕瓶在减少细纹方面有一定效果，是值得信赖的抗衰产品..."', label: '正面', keywords: ['减少细纹', '值得信赖', '一定效果'], engine: 'ChatGPT', time: '2026-04-13 21:45' },
  { id: 'sd-5', topic: '成分安全性', prompt: '雅诗兰黛产品安全吗', summary: '"产品通过了严格的安全检测，但含有酒精和香精，敏感肌需谨慎..."', label: '中性', keywords: ['安全检测', '酒精', '敏感肌谨慎'], engine: '豆包', time: '2026-04-13 19:30' },
  { id: 'sd-6', topic: '用户差评分析', prompt: '为什么有人说雅诗兰黛不好用', summary: '"主要差评集中在过敏反应、价格过高以及部分新品效果不佳三个方面..."', label: '负面', keywords: ['过敏', '价格过高', '效果不佳'], engine: 'DeepSeek', time: '2026-04-13 17:20' },
];

// Top cited pages
export const TOP_CITED_PAGES = [
  { url: 'esteelauder.com.cn/product/anr', title: '小棕瓶精华液 | 雅诗兰黛官网', citations: 42, topicCount: 8 },
  { url: 'xiaohongshu.com/discovery/item/abc123', title: '小棕瓶vs小黑瓶真实测评', citations: 38, topicCount: 6 },
  { url: 'zhihu.com/question/12345', title: '雅诗兰黛值不值得买？', citations: 31, topicCount: 5 },
  { url: 'esteelauder.com.cn/skincare', title: '护肤全系列 | 雅诗兰黛官网', citations: 28, topicCount: 7 },
  { url: 'douyin.com/video/xyz789', title: '皮肤科医生解析小棕瓶成分', citations: 24, topicCount: 4 },
  { url: 'beauty.pclady.com.cn/review/anr', title: '小棕瓶精华深度评测报告', citations: 19, topicCount: 3 },
];

// Citation detail list
export const CITATION_DETAIL_LIST = [
  { id: 'cd-1', topic: '精华液推荐', prompt: '2026年最好的精华液推荐', urls: ['esteelauder.com.cn/product/anr', 'xiaohongshu.com/abc'], position: '正文引用', engine: 'ChatGPT', time: '2026-04-14 10:30' },
  { id: 'cd-2', topic: '成分分析', prompt: '小棕瓶精华成分详解', urls: ['esteelauder.com.cn/product/anr', 'zhihu.com/question/12345'], position: '底部来源', engine: '豆包', time: '2026-04-14 09:15' },
  { id: 'cd-3', topic: '护肤品对比', prompt: '雅诗兰黛和兰蔻精华对比', urls: ['beauty.pclady.com.cn/review/anr'], position: '正文引用', engine: 'DeepSeek', time: '2026-04-14 08:40' },
  { id: 'cd-4', topic: '抗衰老护肤', prompt: '最好的抗衰老护肤品', urls: ['esteelauder.com.cn/skincare', 'douyin.com/video/xyz789'], position: '底部来源', engine: 'ChatGPT', time: '2026-04-13 22:10' },
  { id: 'cd-5', topic: '品牌评价', prompt: '雅诗兰黛品牌怎么样', urls: ['zhihu.com/question/12345', 'xiaohongshu.com/abc'], position: '正文引用', engine: '豆包', time: '2026-04-13 20:35' },
  { id: 'cd-6', topic: '高端护肤', prompt: '高端护肤品品牌排行', urls: ['esteelauder.com.cn/skincare'], position: '底部来源', engine: 'DeepSeek', time: '2026-04-13 18:20' },
];

// Competitor sentiment bubble chart data (X=SoV, Y=sentiment, size=mentions)
export const COMPETITOR_SENTIMENT_BUBBLE = [
  { brand: '香奈儿', sov: 22, sentiment: 0.82, mentions: 185, color: 'var(--color-accent)' },
  { brand: '雅诗兰黛', sov: 18, sentiment: 0.79, mentions: 162, color: 'var(--color-chart-2)' },
  { brand: '兰蔻', sov: 15, sentiment: 0.75, mentions: 147, color: 'var(--color-chart-3)' },
  { brand: 'SK-II', sov: 12, sentiment: 0.72, mentions: 123, color: 'var(--color-chart-6)' },
  { brand: '迪奥', sov: 10, sentiment: 0.74, mentions: 139, color: 'var(--color-accent-2)' },
  { brand: '欧莱雅', sov: 11.8, sentiment: 0.68, mentions: 118, color: 'var(--color-chart-4)' },
];

// ──────────────────────────────────────────────────────────────
// §4.2.7 Citation-Driven User Actions (2026-04-17 新增)
// 6 条行动面: A 归因诊断 / B 内容策略 / C 外联PR / D 竞品解构 /
//           E 模拟 What-if / F Agent API
// PRD 唯一真相源: §4.2.7 A-H, 此处仅承载 frontend 原型 mock
// ──────────────────────────────────────────────────────────────

// §4.2.7.A — Authority Share 时序 (30 天), 每日 3 种归因方法百分比之和 = 100
// 故事线: 前 10 天 official_domain 在 40%+ (健康), 11-20 天开始掉到 30%,
//        21-30 天跌到 25% (触发 citation_attribution_mismatch P2 Alert 条件)
export const AUTHORITY_SHARE_SERIES = Array.from({ length: 30 }, (_, i) => {
  // 平滑衰减: official 从 42 → 26, co_occurrence 从 38 → 48, text_match 从 20 → 26
  const t = i / 29; // 0..1
  const officialDomainPct = Math.round((42 - 16 * t) * 10) / 10;
  const coOccurrencePct = Math.round((38 + 10 * t) * 10) / 10;
  const textMatchPct = Math.round((100 - officialDomainPct - coOccurrencePct) * 10) / 10;
  const date = new Date(2026, 2, 19 + i); // 2026-03-19 起
  return {
    date: date.toISOString().slice(0, 10),
    official_domain_pct: officialDomainPct,
    co_occurrence_pct: coOccurrencePct,
    text_match_pct: textMatchPct,
  };
});

// §4.2.7.A — citation_attribution_mismatch 示例诊断 (P2)
// UI 挂载到品牌详情诊断 Tab, 用与 DIAGNOSTICS 同 shape 的 evidence
export const ATTRIBUTION_MISMATCH_DIAGNOSTIC = {
  id: 'diag-007',
  brandId: 'estee-lauder',
  type: 'brand',
  category: 'citation_attribution_mismatch',
  severity: 'P2',
  title: '引用归因失配 · 官方域名占比连续 14 天 < 40%',
  evidence: {
    metric: 'official_domain_attribution_pct',
    currentValue: 26.4,
    previousValue: 42.0,
    changePercent: -37.1,
    timeRange: '2026-04-03 ~ 2026-04-17',
    citationAttributionMismatch: {
      brandId: 'estee-lauder',
      windowStart: '2026-04-03',
      windowEnd: '2026-04-17',
      byMethod: {
        official_domain: { count: 38, pct: 26.4 },
        co_occurrence: { count: 69, pct: 47.9 },
        text_match: { count: 37, pct: 25.7 },
      },
      possibleCauses: [
        'missing_official_domain_config',
        'alias_mismatch_in_text',
      ],
      panoAShortfall: 8.2,
    },
  },
};

// §4.2.7.B — Content Gap: Top 20 Topic (按 gap_ratio 降序)
// 供 BrandContentGapTab.jsx 区块 ① 消费; CSV #10 同结构导出
export const CONTENT_GAP_TOPICS = [
  { topicId: 't-cg-001', topicText: '抗衰老精华液推荐 500 元内', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 86, myMentions: 62, myAttributions: 18, gapRatio: 0.7097, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 44, topPageType: '评测页' },
  { topicId: 't-cg-002', topicText: '敏感肌专用精华排行', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 72, myMentions: 48, myAttributions: 15, gapRatio: 0.6875, topCompetitorBrand: '雅漾', topCompetitorAttributions: 36, topPageType: '榜单页' },
  { topicId: 't-cg-003', topicText: '高端护肤品对比', categoryPath: '美妆个护 > 护肤', relevantResponses: 94, myMentions: 71, myAttributions: 24, gapRatio: 0.6620, topCompetitorBrand: '香奈儿', topCompetitorAttributions: 51, topPageType: '评测页' },
  { topicId: 't-cg-004', topicText: '小棕瓶 vs 小黑瓶', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 58, myMentions: 42, myAttributions: 16, gapRatio: 0.6190, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 38, topPageType: 'KOL文' },
  { topicId: 't-cg-005', topicText: '产后护肤推荐', categoryPath: '美妆个护 > 护肤', relevantResponses: 65, myMentions: 34, myAttributions: 14, gapRatio: 0.5882, topCompetitorBrand: 'SK-II', topCompetitorAttributions: 24, topPageType: 'KOL文' },
  { topicId: 't-cg-006', topicText: '精华液成分科普', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 103, myMentions: 66, myAttributions: 29, gapRatio: 0.5606, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 43, topPageType: '知识百科' },
  { topicId: 't-cg-007', topicText: '眼部抗衰精华', categoryPath: '美妆个护 > 护肤 > 眼霜', relevantResponses: 49, myMentions: 30, myAttributions: 14, gapRatio: 0.5333, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 22, topPageType: '产品页' },
  { topicId: 't-cg-008', topicText: '护肤品安全性指南', categoryPath: '美妆个护 > 护肤', relevantResponses: 77, myMentions: 44, myAttributions: 21, gapRatio: 0.5227, topCompetitorBrand: '理肤泉', topCompetitorAttributions: 31, topPageType: '知识百科' },
  { topicId: 't-cg-009', topicText: '性价比精华推荐', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 54, myMentions: 25, myAttributions: 12, gapRatio: 0.5200, topCompetitorBrand: '珀莱雅', topCompetitorAttributions: 28, topPageType: '榜单页' },
  { topicId: 't-cg-010', topicText: '冬季干皮护肤', categoryPath: '美妆个护 > 护肤', relevantResponses: 62, myMentions: 37, myAttributions: 18, gapRatio: 0.5135, topCompetitorBrand: '海蓝之谜', topCompetitorAttributions: 22, topPageType: 'KOL文' },
  { topicId: 't-cg-011', topicText: '油皮控油精华', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 46, myMentions: 22, myAttributions: 11, gapRatio: 0.5000, topCompetitorBrand: '修丽可', topCompetitorAttributions: 17, topPageType: '评测页' },
  { topicId: 't-cg-012', topicText: '男士抗衰护肤', categoryPath: '美妆个护 > 护肤 > 男士', relevantResponses: 41, myMentions: 18, myAttributions: 9, gapRatio: 0.5000, topCompetitorBrand: '碧欧泉', topCompetitorAttributions: 13, topPageType: 'KOL文' },
  { topicId: 't-cg-013', topicText: '送礼护肤品 1000 元档', categoryPath: '美妆个护 > 护肤', relevantResponses: 39, myMentions: 21, myAttributions: 11, gapRatio: 0.4762, topCompetitorBrand: 'Dior', topCompetitorAttributions: 15, topPageType: '榜单页' },
  { topicId: 't-cg-014', topicText: '烟酰胺精华推荐', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 66, myMentions: 31, myAttributions: 17, gapRatio: 0.4516, topCompetitorBrand: 'The Ordinary', topCompetitorAttributions: 24, topPageType: '知识百科' },
  { topicId: 't-cg-015', topicText: '精华液正确使用顺序', categoryPath: '美妆个护 > 护肤', relevantResponses: 58, myMentions: 28, myAttributions: 16, gapRatio: 0.4286, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 19, topPageType: '知识百科' },
  { topicId: 't-cg-016', topicText: '视黄醇产品评测', categoryPath: '美妆个护 > 护肤', relevantResponses: 52, myMentions: 27, myAttributions: 16, gapRatio: 0.4074, topCompetitorBrand: '修丽可', topCompetitorAttributions: 23, topPageType: '评测页' },
  { topicId: 't-cg-017', topicText: '精华液与面霜搭配', categoryPath: '美妆个护 > 护肤', relevantResponses: 43, myMentions: 23, myAttributions: 14, gapRatio: 0.3913, topCompetitorBrand: '海蓝之谜', topCompetitorAttributions: 16, topPageType: 'KOL文' },
  { topicId: 't-cg-018', topicText: '夜间修护护肤', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 37, myMentions: 19, myAttributions: 12, gapRatio: 0.3684, topCompetitorBrand: 'SK-II', topCompetitorAttributions: 14, topPageType: '产品页' },
  { topicId: 't-cg-019', topicText: '抗糖抗氧化精华', categoryPath: '美妆个护 > 护肤 > 精华', relevantResponses: 44, myMentions: 23, myAttributions: 15, gapRatio: 0.3478, topCompetitorBrand: '兰蔻', topCompetitorAttributions: 18, topPageType: '评测页' },
  { topicId: 't-cg-020', topicText: '换季敏感肌急救', categoryPath: '美妆个护 > 护肤', relevantResponses: 51, myMentions: 26, myAttributions: 17, gapRatio: 0.3462, topCompetitorBrand: '雅漾', topCompetitorAttributions: 21, topPageType: '知识百科' },
];

// §4.2.7.B — 页面类型分布对比 (我 vs 行业中位 vs Top 竞品), 6 类占比之和必 = 100
export const CONTENT_GAP_PAGE_TYPE_DISTRIBUTION = [
  { pageType: '产品页',    me: 38, industryMedian: 22, topCompetitor: 18 }, // 我在产品页偏多, 竞品在评测页偏多
  { pageType: '评测页',    me: 16, industryMedian: 28, topCompetitor: 34 },
  { pageType: '榜单页',    me: 12, industryMedian: 18, topCompetitor: 20 },
  { pageType: 'KOL文',     me: 14, industryMedian: 15, topCompetitor: 14 },
  { pageType: '知识百科',  me: 8,  industryMedian: 12, topCompetitor: 10 },
  { pageType: '其他',      me: 12, industryMedian: 5,  topCompetitor: 4 },
];

// §4.2.7.C — PR 候选 Top 50, 按 pr_score 降序. 结构对齐 CSV #9.
// 表内含已覆盖的 domain (attributed_to_me_count > 0) 作为"已收获"参照, 以及未覆盖 (=0) 作为新机会
// 实际 API 会支持 excludeCovered=true 过滤掉 attributed_to_me_count > 0
export const PR_TARGETS = [
  { domain: 'sohu.com/beauty',           authorityTier: 2, authorityConfidence: 0.88, attributedToMeCount: 0,  competitorsCount: 5, competitors: ['lancome','sk-ii','chanel','dior','shiseido'], citations30d: 24, trending30dPct: 48.5, siteType: '权威媒体', sameGroupShared: false, prScore: 0.642 },
  { domain: 'iyingji.com',               authorityTier: 2, authorityConfidence: 0.86, attributedToMeCount: 0,  competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','la-mer'],          citations30d: 19, trending30dPct: 36.2, siteType: '权威媒体', sameGroupShared: false, prScore: 0.589 },
  { domain: 'onlylady.com',              authorityTier: 2, authorityConfidence: 0.82, attributedToMeCount: 0,  competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','shiseido'],        citations30d: 17, trending30dPct: 22.4, siteType: '权威媒体', sameGroupShared: false, prScore: 0.534 },
  { domain: 'beauty.pclady.com.cn',      authorityTier: 2, authorityConfidence: 0.85, attributedToMeCount: 12, competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','dior'],             citations30d: 36, trending30dPct: 8.1,  siteType: '权威媒体', sameGroupShared: false, prScore: 0.512 },
  { domain: 'vogue.com.cn',              authorityTier: 2, authorityConfidence: 0.90, attributedToMeCount: 2,  competitorsCount: 5, competitors: ['lancome','sk-ii','chanel','dior','la-mer'],    citations30d: 28, trending30dPct: 12.6, siteType: '权威媒体', sameGroupShared: false, prScore: 0.498 },
  { domain: 'ruili.com.cn',              authorityTier: 2, authorityConfidence: 0.80, attributedToMeCount: 0,  competitorsCount: 3, competitors: ['lancome','sk-ii','dior'],                      citations30d: 14, trending30dPct: 41.0, siteType: '权威媒体', sameGroupShared: false, prScore: 0.487 },
  { domain: 'mayya.xiaohongshu.com',     authorityTier: 3, authorityConfidence: 0.92, attributedToMeCount: 1,  competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','la-mer'],          citations30d: 22, trending30dPct: 28.9, siteType: 'KOL',       sameGroupShared: false, prScore: 0.442 },
  { domain: 'cosmopolitan.com.cn',       authorityTier: 2, authorityConfidence: 0.83, attributedToMeCount: 0,  competitorsCount: 3, competitors: ['lancome','dior','shiseido'],                  citations30d: 11, trending30dPct: 18.2, siteType: '权威媒体', sameGroupShared: false, prScore: 0.431 },
  { domain: 'paulaschoice.com',          authorityTier: 1, authorityConfidence: 0.95, attributedToMeCount: 0,  competitorsCount: 2, competitors: ['lancome','sk-ii'],                            citations30d: 9,  trending30dPct: 14.3, siteType: '官方',       sameGroupShared: false, prScore: 0.418 },
  { domain: 'cosme.net.cn',              authorityTier: 3, authorityConfidence: 0.79, attributedToMeCount: 0,  competitorsCount: 3, competitors: ['lancome','sk-ii','shiseido'],                 citations30d: 12, trending30dPct: 34.5, siteType: 'KOL',       sameGroupShared: false, prScore: 0.401 },
  { domain: 'allure.com',                authorityTier: 2, authorityConfidence: 0.91, attributedToMeCount: 0,  competitorsCount: 3, competitors: ['lancome','chanel','la-mer'],                  citations30d: 10, trending30dPct: 15.8, siteType: '权威媒体', sameGroupShared: false, prScore: 0.386 },
  { domain: 'meilapp.com',               authorityTier: 3, authorityConfidence: 0.76, attributedToMeCount: 4,  competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','dior'],            citations30d: 18, trending30dPct: 6.2,  siteType: 'KOL',       sameGroupShared: false, prScore: 0.371 },
  { domain: 'clinique.com.cn',           authorityTier: 1, authorityConfidence: 0.98, attributedToMeCount: 8,  competitorsCount: 0, competitors: [],                                              citations30d: 15, trending30dPct: 5.5,  siteType: '官方',       sameGroupShared: true,  prScore: 0.364 }, // 同集团共享, 低分但值得标注
  { domain: 'sephora.cn',                authorityTier: 3, authorityConfidence: 0.77, attributedToMeCount: 2,  competitorsCount: 4, competitors: ['lancome','sk-ii','chanel','dior'],            citations30d: 16, trending30dPct: 19.4, siteType: 'KOL',       sameGroupShared: false, prScore: 0.352 },
  { domain: 'globaltimes.cn/beauty',     authorityTier: 2, authorityConfidence: 0.81, attributedToMeCount: 0,  competitorsCount: 2, competitors: ['lancome','chanel'],                           citations30d: 7,  trending30dPct: 20.3, siteType: '权威媒体', sameGroupShared: false, prScore: 0.328 },
];

// §4.2.7.C — Tier 2 覆盖矩阵 (行=Tier 2 域, 列=我+3 主要竞品, 值=引用次数)
export const TIER2_COVERAGE_MATRIX = {
  domains: ['beauty.pclady.com.cn', 'vogue.com.cn', 'cosmopolitan.com.cn', 'allure.com', 'ruili.com.cn', 'sohu.com/beauty', 'iyingji.com', 'onlylady.com'],
  brands: [
    { brandId: 'estee-lauder', label: '我',       counts: [12, 2,  0, 0,  0, 0,  0, 0] },
    { brandId: 'lancome',      label: '兰蔻',     counts: [18, 22, 9, 8,  6, 14, 12, 10] },
    { brandId: 'sk-ii',        label: 'SK-II',    counts: [15, 14, 7, 6,  5, 11, 9,  8] },
    { brandId: 'chanel',       label: '香奈儿',   counts: [11, 16, 6, 8,  4, 10, 8,  9] },
  ],
};

// §4.2.7.C — KOL 评分卡 (仅 Tier 3, Top 10)
// diversity = Shannon entropy, 0..log2(N_brands) ≈ 0..3.3 for 10 brands
export const KOL_SCORECARDS = [
  { domain: 'mayya.xiaohongshu.com',   authorityConfidence: 0.92, diversity: 2.81, avgCitationsPerWeek: 5.4, brandDiversity90d: ['兰蔻','SK-II','香奈儿','La Mer','Dior','雅诗兰黛'] },
  { domain: 'beautyeditor.zhihu.com',  authorityConfidence: 0.88, diversity: 2.65, avgCitationsPerWeek: 4.1, brandDiversity90d: ['兰蔻','SK-II','香奈儿','Dior'] },
  { domain: 'skin_doctor.douyin.com',  authorityConfidence: 0.85, diversity: 2.48, avgCitationsPerWeek: 3.8, brandDiversity90d: ['兰蔻','SK-II','理肤泉','雅漾'] },
  { domain: 'lab_ingredient.xhs.com',  authorityConfidence: 0.83, diversity: 2.22, avgCitationsPerWeek: 3.5, brandDiversity90d: ['修丽可','The Ordinary','兰蔻'] },
  { domain: 'lifestyle.weibo.com',     authorityConfidence: 0.74, diversity: 2.98, avgCitationsPerWeek: 2.9, brandDiversity90d: ['兰蔻','雅诗兰黛','SK-II','海蓝之谜','Dior','香奈儿','Fresh'] },
  { domain: 'review_lab.xhs.com',      authorityConfidence: 0.80, diversity: 1.54, avgCitationsPerWeek: 2.6, brandDiversity90d: ['兰蔻','SK-II'] }, // 低多样性, 可能是竞品独家
];

// §4.2.7.D — Authority Radar 5 维数据 (me vs industryMedian vs topCompetitor='lancome')
// 各 Tier 份额 = 该品牌在该 Tier 的 citation 数 / 该品牌总 citation 数 × 100
export const AUTHORITY_RADAR_DATA = [
  { tier: 'Tier 0 (未知)',    me: 14, industryMedian: 8,  topCompetitor: 6 },  // 我偏高, 说明新域识别不佳
  { tier: 'Tier 1 (官方)',    me: 15, industryMedian: 18, topCompetitor: 22 },
  { tier: 'Tier 2 (权威媒体)', me: 11, industryMedian: 25, topCompetitor: 32 }, // 核心差距点
  { tier: 'Tier 3 (KOL)',     me: 42, industryMedian: 36, topCompetitor: 30 },
  { tier: 'Tier 4 (UGC)',     me: 18, industryMedian: 13, topCompetitor: 10 },
];

// §4.2.7.D — Same-Group 共享 (欧莱雅集团内部)
export const SAME_GROUP_SHARED = {
  currentBrand: 'estee-lauder',
  group: 'The Estée Lauder Companies',
  siblingBrands: ['clinique', 'mac', 'la-mer', 'origins'],
  sharedDomains: [
    { domain: 'clinique.com.cn',   tier: 1, sharedWith: ['clinique'] },
    { domain: 'esteelauder.com.cn', tier: 1, sharedWith: ['estee-lauder'] }, // 自己的官方, 不算共享, UI 过滤
    { domain: 'lamer.com.cn',      tier: 1, sharedWith: ['la-mer'] },
  ],
  sharedRatio: 0.12, // 共享占双方总引用 12%
};

// §4.2.7.D — Acquisition Event Stream (近 30 天新 Tier 1+2 来源首次出现)
export const ACQUISITION_EVENTS = [
  { date: '2026-04-15', domain: 'vogue.com.cn',       tier: 2, sourceResponseId: 'r-2026-04-15-0034', note: '首次在 Vogue 中文站评测中被引用' },
  { date: '2026-04-12', domain: 'paulaschoice.com',   tier: 1, sourceResponseId: 'r-2026-04-12-0089', note: '成分专家网站首次标注' },
  { date: '2026-04-05', domain: 'cosmopolitan.com.cn',tier: 2, sourceResponseId: 'r-2026-04-05-0201', note: '首次出现在 Cosmo 中文榜单' },
  { date: '2026-03-28', domain: 'ruili.com.cn',       tier: 2, sourceResponseId: 'r-2026-03-28-0145', note: '瑞丽新增产品评测' },
];

// §4.2.7.E — Simulator baseline (品牌当前状态, Simulator 页输入区只读快照)
export const SIMULATOR_BASELINE = {
  brandId: 'estee-lauder',
  currentByTier: {
    0: 93,   // unknown domains (占位)
    1: 98,   // official
    2: 36,   // authority media
    3: 315,  // KOL
    4: 102,  // UGC
  },
  currentPanoA: 61.3,
  industryMedian: 69.4,
  industryTop3Avg: 78.9,
  // Tier weights 来自 §4.2.6.B (真实系统读 DB, 此处仅 mock)
  tierWeights: { 0: 0, 1: 1.0, 2: 0.7, 3: 0.4, 4: 0.15 },
  // 默认 confidence (真实系统按 CitationDomainAuthority 实际值加权)
  defaultConfidence: { 0: 0.0, 1: 1.0, 2: 0.85, 3: 0.75, 4: 0.65 },
  // basePriceByTier 来自 Admin 参数服务 (mock 仅作示意)
  basePriceByTier: { 1: 0, 2: 15000, 3: 3500, 4: 800 }, // CNY / 次
};

// §4.2.7.E — Simulator 预设 3 个"典型场景"供用户点击快试
export const SIMULATOR_PRESETS = [
  { id: 'catch-up-median', label: '追平行业中位',   deltaByTier: { 1: 0, 2: 12, 3: 0 },  confidenceOverride: null, expectedDeltaPanoA: 7.8 },
  { id: 'surpass-top3',    label: '超越 Top 3 均值', deltaByTier: { 1: 5, 2: 25, 3: 10 }, confidenceOverride: null, expectedDeltaPanoA: 18.4 },
  { id: 'tier1-surge',     label: '仅补 Tier 1 官域', deltaByTier: { 1: 10, 2: 0, 3: 0 },  confidenceOverride: null, expectedDeltaPanoA: 6.1 },
];

/* ─────────────────────────────────────────────────────────────
   Industry Plan S v2 — 2026-04-20 (dead exports 已删除)
   ─────────────────────────────────────────────────────────────
   原 INDUSTRY_KPI_DISTRIBUTION / INDUSTRY_TRENDING_EVENTS 两个派生 mock
   与 PRD §4.6.1e §G.1 harness 冲突 (违反 "Industry 页不得新建派生 mock" 规则),
   且从未被 import 使用。v2 IQR / 异动改为从 BRANDS 实时派生 (computeIQR
   + BRANDS.change 排序), 无任何依赖, 清理后 vite build 无破坏。

   v2 行业页数据源 (零新增 mock, 全部复用):
   - BRANDS (过滤 industryId, 字段: panoScore/sov/mentionRate/sentiment/
     citationShare/ranking/change/parentCompany)
   - INDUSTRY_TOPIC_HEATMAP (下方 line ~2195)
   - TOP_CITED_DOMAINS (上方 line ~1807)
*/

/* ─────────────────────────────────────────────────────────────
   Deep Brand Mode Pages — Mock Data Enrichments
   2026-04-20
   ─────────────────────────────────────────────────────────────
   - SENTIMENT_TOPIC_ATTRIBUTION: 情感溯源 by Topic
   - VISIBILITY_UNMISSED_PROMPTS: 遗漏高流量 Prompt
   - INDUSTRY_TOPIC_HEATMAP: 行业 Topic 覆盖矩阵 (v3.1: 不再用于"热度", 仅承载 topic × brand 命中强度)
   - PRODUCTS sparkData + mentionCount enrichment
   - BRANDS sparkPano enrichment
*/

export const SENTIMENT_TOPIC_ATTRIBUTION = [
  {
    topicId: 'topic-skincare-retinol',
    topicName: '视黄醇/视A成分安全争议',
    negativeCount: 127,
    negativeRatio: 0.34,
    sampleSnippet: '视黄醇虽然效果好，但对敏感肌确实有刺激，浓度不当会导致泛红脱皮...',
  },
  {
    topicId: 'topic-eyecream-efficacy',
    topicName: '眼霜抗衰效果评估',
    negativeCount: 89,
    negativeRatio: 0.22,
    sampleSnippet: '很多眼霜价格虚高，实际效果与平价产品差异不大，消费者容易被营销迷惑...',
  },
  {
    topicId: 'topic-sunscreen-texture',
    topicName: '防晒霜使用体验问题',
    negativeCount: 156,
    negativeRatio: 0.41,
    sampleSnippet: '高防晒值的产品普遍厚重，容易闷痘，夏天使用体验差，需要专业卸妆...',
  },
  {
    topicId: 'topic-serum-consistency',
    topicName: '精华液质地与肤感差异',
    negativeCount: 64,
    negativeRatio: 0.18,
    sampleSnippet: '同一品牌的精华液批次差异明显，某批次过水，某批次过油，质量不稳定...',
  },
  {
    topicId: 'topic-moisturizer-balance',
    topicName: '保湿霜油水平衡度',
    negativeCount: 43,
    negativeRatio: 0.12,
    sampleSnippet: '这款保湿霜对干皮友好，但油皮容易长闭口，需根据季节灵活使用...',
  },
];

export const VISIBILITY_UNMISSED_PROMPTS = [
  {
    promptText: '熬夜皮肤差怎么快速恢复？推荐一下好用的修复精华',
    engine: 'ChatGPT',
    date: '2026-04-19',
    volume: 3240,
    mentionRate: 0,
  },
  {
    promptText: '敏感肌可以用的高效抗衰精华有哪些',
    engine: '豆包',
    date: '2026-04-18',
    volume: 2840,
    mentionRate: 0,
  },
  {
    promptText: '平价防晒霜推荐，要求不油腻不搓泥',
    engine: 'DeepSeek',
    date: '2026-04-18',
    volume: 2650,
    mentionRate: 0,
  },
  {
    promptText: '秋冬护肤品怎么选？干皮适用的面霜对比',
    engine: 'ChatGPT',
    date: '2026-04-17',
    volume: 2180,
    mentionRate: 0,
  },
  {
    promptText: '眼部细纹明显，有没有口碑好的眼霜',
    engine: '豆包',
    date: '2026-04-17',
    volume: 1950,
    mentionRate: 0,
  },
  {
    promptText: '油皮痘肌专业护肤方案，控油保湿兼顾',
    engine: 'DeepSeek',
    date: '2026-04-16',
    volume: 1820,
    mentionRate: 0,
  },
  {
    promptText: '美白产品哪个品牌效果最明显，新手友好的',
    engine: 'ChatGPT',
    date: '2026-04-16',
    volume: 1670,
    mentionRate: 0,
  },
  {
    promptText: '抗氧化护肤品怎么选，维C精华值得买吗',
    engine: '豆包',
    date: '2026-04-15',
    volume: 1540,
    mentionRate: 0,
  },
  {
    promptText: '夏季清爽护肤露：轻薄补水不黏腻的推荐',
    engine: 'DeepSeek',
    date: '2026-04-15',
    volume: 1310,
    mentionRate: 0,
  },
  {
    promptText: '玻尿酸精华怎么用效果最好，和其他精华能叠用吗',
    engine: 'ChatGPT',
    date: '2026-04-14',
    volume: 1185,
    mentionRate: 0,
  },
];

export const INDUSTRY_TOPIC_HEATMAP = [
  {
    topicId: 'hm-1',
    topicName: '抗衰老成分科普',
    mentionCount: 3450,
    avgSentiment: 0.76,
    isEmerging: false,
  },
  {
    topicId: 'hm-2',
    topicName: '敏感肌护肤指南',
    mentionCount: 3120,
    avgSentiment: 0.72,
    isEmerging: false,
  },
  {
    topicId: 'hm-3',
    topicName: '防晒产品选购指南',
    mentionCount: 2890,
    avgSentiment: 0.68,
    isEmerging: false,
  },
  {
    topicId: 'hm-4',
    topicName: '护肤品成分安全性评估',
    mentionCount: 2650,
    avgSentiment: 0.61,
    isEmerging: false,
  },
  {
    topicId: 'hm-5',
    topicName: '油皮控制方案',
    mentionCount: 2480,
    avgSentiment: 0.65,
    isEmerging: false,
  },
  {
    topicId: 'hm-6',
    topicName: '肌肤屏障修复产品',
    mentionCount: 2310,
    avgSentiment: 0.74,
    isEmerging: true,
  },
  {
    topicId: 'hm-7',
    topicName: '精华液多效复合方案',
    mentionCount: 2140,
    avgSentiment: 0.71,
    isEmerging: true,
  },
  {
    topicId: 'hm-8',
    topicName: '眼部护理专题',
    mentionCount: 1950,
    avgSentiment: 0.69,
    isEmerging: false,
  },
  {
    topicId: 'hm-9',
    topicName: '美白淡斑成分研究',
    mentionCount: 1780,
    avgSentiment: 0.64,
    isEmerging: false,
  },
  {
    topicId: 'hm-10',
    topicName: '护肤品叠用技巧',
    mentionCount: 1620,
    avgSentiment: 0.73,
    isEmerging: true,
  },
  {
    topicId: 'hm-11',
    topicName: '春夏护肤转换方案',
    mentionCount: 1450,
    avgSentiment: 0.70,
    isEmerging: false,
  },
  {
    topicId: 'hm-12',
    topicName: '高端护肤品 ROI 评估',
    mentionCount: 1280,
    avgSentiment: 0.67,
    isEmerging: true,
  },
];

// Enrich PRODUCTS with sparkData and mentionCount for deep pages
PRODUCTS.forEach((p, i) => {
  p.mentionCount = Math.round(800 + Math.random() * 2000);
  p.sparkData = Array.from({ length: 14 }, (_, j) => {
    const base = p.mentionRate || 10;
    const variation = Math.sin(j * 0.5 + i) * 2 + (Math.random() - 0.5) * 1.5;
    const value = base + variation;
    return Math.max(0, Math.min(50, value));
  });
});

// Enrich BRANDS with sparkPano for competitor trend comparison
BRANDS.forEach((b, i) => {
  b.sparkPano = Array.from({ length: 14 }, (_, j) => {
    const base = b.panoScore || 50;
    return Math.round((base + Math.sin(j * 0.4 + i * 0.7) * 4 + (Math.random() - 0.5) * 3) * 10) / 10;
  });
});
