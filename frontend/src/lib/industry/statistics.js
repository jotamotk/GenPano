/**
 * Industry statistics helpers — PRD §4.6.1e §C (IQR) + §E (聚合派生)
 *
 * 单一真相源: 本文件是 5 KPI IQR / 集团聚合 / Top-N 排序的唯一实现。
 * 禁止在 pages/components 中 inline 计算 percentile (§G.3 harness 拦截).
 */

/**
 * Compute P25/P50/P75 + IQR fences + outliers.
 * Linear interpolation between order statistics (Type 7, 默认 NumPy / R).
 *
 * @param {number[]} values — 原始数组 (允许负数 / 零)
 * @returns {{ p25, p50, p75, iqr, lowerFence, upperFence, min, max, outliers, n, tooSmall, statOnly } | null}
 *   - tooSmall: true 当 n < 5 (无法画箱线, 仅点阵)
 *   - statOnly: true 当 n < 3 (只给均值, 不给分布)
 *   - 返回 null 当 values 空或全部 NaN
 */
export function computeIQR(values) {
  const clean = (values || []).filter(v => typeof v === 'number' && !Number.isNaN(v));
  const n = clean.length;
  if (n === 0) return null;

  const sorted = [...clean].sort((a, b) => a - b);
  const percentile = (p) => {
    // Type 7 linear interpolation: (n-1) * p/100
    const rank = ((n - 1) * p) / 100;
    const lo = Math.floor(rank);
    const hi = Math.ceil(rank);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (rank - lo);
  };

  const p25 = percentile(25);
  const p50 = percentile(50);
  const p75 = percentile(75);
  const iqr = p75 - p25;
  const lowerFence = p25 - 1.5 * iqr;
  const upperFence = p75 + 1.5 * iqr;
  const outliers = sorted.filter(v => v < lowerFence || v > upperFence);

  return {
    p25,
    p50,
    p75,
    iqr,
    lowerFence,
    upperFence,
    min: sorted[0],
    max: sorted[n - 1],
    mean: sorted.reduce((s, v) => s + v, 0) / n,
    outliers,
    n,
    tooSmall: n < 5,
    statOnly: n < 3,
  };
}

/**
 * Group an array by a key (string or function).
 * @param {T[]} arr
 * @param {string | (item: T) => string} key
 * @returns {Record<string, T[]>}
 */
export function groupBy(arr, key) {
  const fn = typeof key === 'function' ? key : (item) => item[key];
  const out = {};
  for (const item of arr || []) {
    const k = fn(item);
    if (k == null) continue;
    if (!out[k]) out[k] = [];
    out[k].push(item);
  }
  return out;
}

/**
 * Sort a BRANDS-like array by a numeric field, descending, take Top N.
 * @param {Array} arr
 * @param {string} field
 * @param {number} n
 */
export function topByField(arr, field, n = 10) {
  return [...(arr || [])]
    .filter(item => typeof item[field] === 'number' && !Number.isNaN(item[field]))
    .sort((a, b) => b[field] - a[field])
    .slice(0, n);
}

/**
 * Sort by absolute value of a numeric-string field (e.g. "+2.3" / "-1.2"),
 * descending, take Top N. Used for 异动 (change).
 * @param {Array} arr
 * @param {string} field
 * @param {number} n
 */
export function topByAbsField(arr, field, n = 3) {
  return [...(arr || [])]
    .filter(item => item[field] != null)
    .map(item => ({ ...item, _abs: Math.abs(parseFloat(item[field])) }))
    .filter(item => !Number.isNaN(item._abs))
    .sort((a, b) => b._abs - a._abs)
    .slice(0, n);
}

/**
 * Aggregate BRANDS by parentCompany into groups (段 ⑥ 集团版图).
 * Each group: { groupName, brandCount, totalSov, totalMentionRate, avgSentiment,
 *               maxBrand, brands: Brand[] }.
 * Returned sorted by totalSov desc.
 * @param {Array} brands
 */
export function aggregateByGroup(brands) {
  const grouped = groupBy(brands, 'parentCompany');
  const out = Object.entries(grouped).map(([groupName, bs]) => {
    const totalSov = bs.reduce((s, b) => s + (b.sov || 0), 0);
    const totalMentionRate = bs.reduce((s, b) => s + (b.mentionRate || 0), 0);
    const avgSentiment =
      bs.reduce((s, b) => s + (b.sentiment || 0), 0) / bs.length;
    const avgPano = bs.reduce((s, b) => s + (b.panoScore || 0), 0) / bs.length;
    const maxBrand = bs.reduce((best, b) =>
      (b.panoScore || 0) > (best?.panoScore || 0) ? b : best, bs[0]);
    return {
      groupName,
      brandCount: bs.length,
      totalSov: Number(totalSov.toFixed(1)),
      totalMentionRate: Number((totalMentionRate * 100).toFixed(1)),
      avgSentiment: Number(avgSentiment.toFixed(2)),
      avgPano: Math.round(avgPano),
      maxBrand,
      brands: [...bs].sort((a, b) => (b.panoScore || 0) - (a.panoScore || 0)),
    };
  });
  return out.sort((a, b) => b.totalSov - a.totalSov);
}

/* ──────────────────────────────────────────────────────────────────
 * Deterministic hash-seeded synthesis helpers
 * (PRD §4.6.1f Ranking + §4.6.1g Topics, 零新增 mock)
 * ──────────────────────────────────────────────────────────────────
 * 以下 6 个 helper 用 string hash 做 seed → Mulberry32 PRNG, 保证:
 *   - 同一个品牌/话题/键组合, 每次结果完全相同 (stable)
 *   - 不同键组合结果分布足够自然, 不出现锯齿
 *   - 真实后端接入后整体替换这些 helper, 页面代码不动
 */

function _hashString(str) {
  // FNV-1a 32-bit, 输出 uint32
  let h = 0x811c9dc5;
  const s = String(str || '');
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

function _mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * §4.6.1f 段 ⑤ — 30d 排名异动合成.
 * hash(brand.id) seed → { rankFrom, rankTo, trend[30], primaryDriver }
 * rankFrom/rankTo 围绕 b.ranking ±5 位, 有符号变化.
 * primaryDriver ∈ {'panoScore','sov','citationShare','sentiment'}.
 *
 * @param {{id: string, ranking?: number}} brand
 * @returns {{
 *   rankFrom: number,
 *   rankTo: number,
 *   delta: number,
 *   trend: number[],   // 30 点 rank 序列, 从 rankFrom 线性过渡到 rankTo + 抖动
 *   primaryDriver: string
 * }}
 */
export function rankingDelta30d(brand) {
  if (!brand?.id) return null;
  const base = brand.ranking || 20;
  const rand = _mulberry32(_hashString(`rank-delta:${brand.id}`));
  const deltaRaw = Math.round((rand() - 0.5) * 10); // -5..+5
  const delta = deltaRaw === 0 ? (rand() > 0.5 ? 1 : -1) : deltaRaw;
  const rankFrom = Math.max(1, base + delta);
  const rankTo = Math.max(1, base);
  const trend = Array.from({ length: 30 }, (_, i) => {
    const t = i / 29;
    const interp = rankFrom + (rankTo - rankFrom) * t;
    const jitter = (rand() - 0.5) * 1.5;
    return Math.max(1, Math.round(interp + jitter));
  });
  const drivers = ['panoScore', 'sov', 'citationShare', 'sentiment'];
  const primaryDriver = drivers[Math.floor(rand() * drivers.length)];
  return {
    rankFrom,
    rankTo,
    delta: rankFrom - rankTo, // 正 = 排名上升 (#10 → #6 delta=4), 负 = 下滑
    trend,
    primaryDriver,
  };
}

/**
 * §4.6.1f 段 ⑥ — 3 引擎分位合成.
 * hash(brand.id) seed → { chatgpt, doubao, deepseek }, 都围绕 b.ranking ±3.
 * 附加: maxDelta = max - min (同 brand 3 引擎最大差).
 *
 * @param {{id: string, ranking?: number}} brand
 */
export function rankingByEngine(brand) {
  if (!brand?.id) return null;
  const base = brand.ranking || 20;
  const rand = _mulberry32(_hashString(`rank-engine:${brand.id}`));
  const pick = () => Math.max(1, Math.round(base + (rand() - 0.5) * 6));
  const chatgpt = pick();
  const doubao = pick();
  const deepseek = pick();
  return {
    chatgpt,
    doubao,
    deepseek,
    maxDelta: Math.max(chatgpt, doubao, deepseek) - Math.min(chatgpt, doubao, deepseek),
  };
}

/**
 * §4.6.1f 段 ④ — 排名离散度 (rank standard deviation 跨 KPI).
 * 对每个 kpiField, 在 allBrands 中按 desc 排名取该 brand 的名次,
 * 收集到 ranks 数组后计算标准差. 高 σ = 综合排但单项表现 uneven.
 *
 * @param {object} brand
 * @param {object[]} allBrands
 * @param {string[]} kpiFields — e.g. ['panoScore','sov','citationShare','sentiment']
 * @returns {{ ranks: Record<string, number>, sigma: number }}
 */
export function rankDispersion(brand, allBrands, kpiFields) {
  const ranks = {};
  for (const field of kpiFields || []) {
    const sorted = [...(allBrands || [])]
      .filter(b => typeof b[field] === 'number')
      .sort((a, b) => b[field] - a[field]);
    const idx = sorted.findIndex(b => b.id === brand.id);
    ranks[field] = idx >= 0 ? idx + 1 : null;
  }
  const vals = Object.values(ranks).filter(v => typeof v === 'number');
  if (vals.length < 2) return { ranks, sigma: 0 };
  const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
  const variance =
    vals.reduce((s, v) => s + (v - mean) * (v - mean), 0) / vals.length;
  return { ranks, sigma: Number(Math.sqrt(variance).toFixed(2)) };
}

/**
 * §4.6.1g 段 ④ — Brand × Topic 覆盖强度 (0-100 int).
 * hash("${brand.id}:${topicId}") seed → 0..100.
 * 纯确定性, 保证同一组合每次相同.
 *
 * @param {{id: string}} brand
 * @param {{topicId: string}} topic
 * @returns {number} 0-100
 */
export function brandTopicHits(brand, topic) {
  const bid = brand?.id;
  const tid = topic?.topicId || topic?.id;
  if (!bid || !tid) return 0;
  const rand = _mulberry32(_hashString(`brand-topic:${bid}:${tid}`));
  return Math.round(rand() * 100);
}

/**
 * §4.6.1g 段 ⑤ — Topic emerging/declining score.
 * hash(topic.topicId) seed:
 *   - isEmerging === true: 返回 10..80 (正, 越大越新兴)
 *   - 否则: 返回 -60..0 (负, 越小越衰退)
 *
 * @param {{topicId: string, isEmerging?: boolean}} topic
 * @returns {number}
 */
export function emergingScore(topic) {
  const tid = topic?.topicId || topic?.id;
  if (!tid) return 0;
  const rand = _mulberry32(_hashString(`emerging:${tid}`));
  if (topic.isEmerging) return Math.round(10 + rand() * 70);
  return Math.round(-60 + rand() * 60);
}

/**
 * §4.6.1g 段 ⑥ — Topic × Intent 占比分解 (sum = 100).
 * hash(topic.topicId) seed → 4 个 Dirichlet-like 占比.
 * 返回整数 % 且 sum 严格 = 100.
 *
 * @param {{topicId: string}} topic
 * @returns {{ informational, commercial, transactional, navigational, dominant }}
 */
export function topicIntentBreakdown(topic) {
  const tid = topic?.topicId || topic?.id;
  if (!tid) {
    return {
      informational: 25,
      commercial: 25,
      transactional: 25,
      navigational: 25,
      dominant: 'informational',
    };
  }
  const rand = _mulberry32(_hashString(`intent:${tid}`));
  const raw = [rand() + 0.1, rand() + 0.1, rand() + 0.1, rand() + 0.1];
  const sum = raw.reduce((s, v) => s + v, 0);
  const pct = raw.map(v => Math.round((v / sum) * 100));
  // Fix rounding drift so sum === 100
  const drift = 100 - pct.reduce((s, v) => s + v, 0);
  pct[0] += drift;
  const keys = ['informational', 'commercial', 'transactional', 'navigational'];
  const out = {};
  keys.forEach((k, i) => { out[k] = pct[i]; });
  const dominantIdx = pct.indexOf(Math.max(...pct));
  out.dominant = keys[dominantIdx];
  return out;
}
