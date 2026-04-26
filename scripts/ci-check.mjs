#!/usr/bin/env node
/**
 * GENPANO · Harness L1 Rule Registry (ci-check.mjs)
 *
 * Single source of truth for all grep-based harness rules.
 * Session 0-rev delivers 38 rules across 5 groups (A / B / C / D / E).
 *
 * Each rule is a specific function that reads files under `frontend/src/**` and
 * returns an array of violations. Violations carry `{ rule, file, line, message, fixHint }`.
 *
 * Rule bloodline: docs/TEST_STRATEGY.md §13 + CLAUDE.md Decision #21.A.
 *
 * CLI:
 *   node scripts/ci-check.mjs              # run all rules
 *   node scripts/ci-check.mjs --json       # structured JSON output
 *   node scripts/ci-check.mjs --rule=A1    # run a single rule by id
 *   node scripts/ci-check.mjs --changed-only   # (placeholder for --changed-only in pre-commit; runs all for now)
 *   node scripts/ci-check.mjs --include-fixtures   # include __ci_fixtures__/ in scan (used by selftest)
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const PROJECT_ROOT = join(__filename, '..', '..');
const FRONTEND_SRC = join(PROJECT_ROOT, 'frontend', 'src');
const FRONTEND_I18N = join(FRONTEND_SRC, 'i18n');
const FIXTURES_DIR = join(FRONTEND_SRC, '__ci_fixtures__');

const argv = process.argv.slice(2);
const FLAG_JSON = argv.includes('--json');
const FLAG_INCLUDE_FIXTURES = argv.includes('--include-fixtures');
const FLAG_CHANGED_ONLY = argv.includes('--changed-only'); // reserved for future
void FLAG_CHANGED_ONLY;
const ruleFilter = (argv.find((a) => a.startsWith('--rule=')) || '').slice('--rule='.length) || null;

/* ---------------- File helpers ---------------- */

function listFiles(dir, extensions, { includeFixtures = false } = {}) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (p) => {
    for (const name of readdirSync(p)) {
      const full = join(p, name);
      let s;
      try {
        s = statSync(full);
      } catch {
        continue;
      }
      if (s.isDirectory()) {
        if (name === 'node_modules') continue;
        if (!includeFixtures && name === '__ci_fixtures__') continue;
        walk(full);
      } else if (extensions.some((ext) => name.endsWith(ext))) {
        out.push(full);
      }
    }
  };
  walk(dir);
  return out;
}

function readSafe(p) {
  try {
    return readFileSync(p, 'utf8');
  } catch {
    return '';
  }
}

function grepLines(content, regex) {
  const lines = content.split(/\r?\n/);
  const hits = [];
  for (let i = 0; i < lines.length; i++) {
    if (regex.test(lines[i])) hits.push({ lineNumber: i + 1, lineText: lines[i] });
  }
  return hits;
}

function relFromRoot(absPath) {
  return relative(PROJECT_ROOT, absPath).split(sep).join('/');
}

/* ---------------- Rule registry ---------------- */

/** @type {{id:string, group:string, description:string, fn:Function}[]} */
const rules = [];
function registerRule(id, group, description, fn) {
  rules.push({ id, group, description, fn });
}

/* ========================================================================
 *  GROUP A · i18n / 文案边界 (6 rules) — PRD §4.10.4a.D + §4.6.0a.D
 * ======================================================================== */

const DEV_CONSTRAINT_RE = /本页(只|不)做|只回答|不承担|详情请进入|请去.*查看|严禁|🚫|⚠️ ?(本页|本段)/;

// A1: JSX 文本节点禁 CJK (whitelist: comments, stories, test files, data-locale attributes)
registerRule('A1', 'A', 'i18n-cjk-leak · JSX text 禁未经 t() 的中日韩字符', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  const cjk = /[一-鿿぀-ヿ가-힯]/;
  for (const file of files) {
    if (file.includes('messages.') && !file.endsWith('.jsx')) continue;
    const content = readSafe(file);
    const lines = content.split(/\r?\n/);
    let inBlockComment = false;
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];
      // Strip block comments
      if (inBlockComment) {
        const endIdx = line.indexOf('*/');
        if (endIdx >= 0) {
          inBlockComment = false;
          line = line.slice(endIdx + 2);
        } else continue;
      }
      const startIdx = line.indexOf('/*');
      if (startIdx >= 0 && line.indexOf('*/', startIdx) < 0) {
        inBlockComment = true;
        line = line.slice(0, startIdx);
      }
      // Skip // comments
      const sc = line.indexOf('//');
      if (sc >= 0) line = line.slice(0, sc);
      // Skip attribute data-locale="zh..." whitelist
      if (/data-locale\s*=\s*["']zh/.test(line)) continue;
      // JSX text heuristic: `>...<` with CJK between, or `{'...' + CJK + '...'}` literal strings
      const jsxText = />[^<{}]*[一-鿿぀-ヿ가-힯][^<{}]*</.test(line);
      const literalString = /(['"`])[^'"`]*[一-鿿぀-ヿ가-힯][^'"`]*\1/.test(line);
      if (jsxText || literalString) {
        if (cjk.test(line)) {
          out.push({
            rule: 'A1',
            file: relFromRoot(file),
            line: i + 1,
            message: 'JSX text node or literal contains raw CJK characters',
            fixHint: 'Wrap the text with t(key) from useTranslation() instead of hardcoding CJK.',
            snippet: line.trim().slice(0, 120),
          });
          break; // one hit per file is enough
        }
      }
    }
  }
  return out;
});

// A2: i18n pair coverage — zh-CN vs en-US key set equal
registerRule('A2', 'A', 'i18n-pair-coverage · zh-CN 与 en-US 键集合必须对齐', (ctx) => {
  // MVP uses a single messages.js file. Full namespace split is deferred to Session 4a.
  // This rule degrades gracefully: if JSON namespaces exist, diff them; else pass.
  const zhCN = join(FRONTEND_I18N, 'messages.zh-CN.json');
  const enUS = join(FRONTEND_I18N, 'messages.en-US.json');
  if (!existsSync(zhCN) || !existsSync(enUS)) return [];
  try {
    const zhKeys = flattenKeys(JSON.parse(readSafe(zhCN)));
    const enKeys = flattenKeys(JSON.parse(readSafe(enUS)));
    const diff = [...zhKeys].filter((k) => !enKeys.has(k)).concat([...enKeys].filter((k) => !zhKeys.has(k)));
    return diff.slice(0, 20).map((k) => ({
      rule: 'A2',
      file: 'frontend/src/i18n/messages.*.json',
      line: 0,
      message: `key missing on one side: ${k}`,
      fixHint: 'Ensure every key exists in both locales.',
    }));
  } catch {
    return [];
  }
  void ctx;
});

function flattenKeys(obj, prefix = '', out = new Set()) {
  for (const [k, v] of Object.entries(obj || {})) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) flattenKeys(v, path, out);
    else out.add(path);
  }
  return out;
}

// A3: formatBrand entry — JSX 禁直接 {brand.nameZh} / {brand.nameEn} / {item.productNameZh|En}
registerRule('A3', 'A', 'formatBrand-entry · 品牌/产品多语言名称必须经 formatBrand / formatProduct', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const re = /\{[^}]*\b(brand|product|item)\.(nameZh|nameEn|productNameZh|productNameEn)\b[^}]*\}/;
  const out = [];
  for (const file of files) {
    // Skip the LocaleContext itself where formatBrand is defined
    if (/LocaleContext\.jsx/.test(file)) continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'A3',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Direct access to multi-locale brand/product name field',
          fixHint: 'Use formatBrand(brand, locale) / formatProduct(product, locale) from LocaleContext.',
          snippet: lines[i].trim().slice(0, 120),
        });
        break;
      }
    }
  }
  return out;
});

// A4: i18n JSON 禁开发者约束措辞
registerRule('A4', 'A', 'ui-developer-constraint-leak-i18n · i18n 字典禁开发者约束措辞', (ctx) => {
  const out = [];
  const i18nFiles = [
    ...listFiles(FRONTEND_I18N, ['.json', '.js', '.ts'], { includeFixtures: ctx.includeFixtures }),
  ];
  for (const file of i18nFiles) {
    if (file.endsWith('.broken-backup')) continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (DEV_CONSTRAINT_RE.test(lines[i])) {
        out.push({
          rule: 'A4',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Developer-constraint wording leaked into i18n',
          fixHint: 'Express boundaries via IA / navigation, not by telling the user "本页不做 X".',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  // Dedup per file (one hit is enough)
  const seen = new Set();
  return out.filter((v) => (seen.has(v.file) ? false : seen.add(v.file)));
});

// A5: JSX 文本节点同规则
registerRule('A5', 'A', 'ui-developer-constraint-leak-jsx · JSX 禁开发者约束措辞', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (DEV_CONSTRAINT_RE.test(lines[i])) {
        out.push({
          rule: 'A5',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Developer-constraint wording in JSX',
          fixHint: 'Move the constraint to PRD comments; remove from UI text.',
          snippet: lines[i].trim().slice(0, 120),
        });
        break;
      }
    }
  }
  return out;
});

// A6: interpolation API — 禁 t('key', 'fallback string')
registerRule('A6', 'A', 'i18n-interpolation-api · t(key, {values}) 强制, 禁 fallback-string 二路歧义', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx', '.js', '.ts'], { includeFixtures: ctx.includeFixtures });
  // Match: t('xxx', 'some fallback')  — the 2nd arg is a plain string literal, not an object
  const re = /\bt\s*\(\s*['"`][^'"`]+['"`]\s*,\s*['"`][^'"`]+['"`]\s*\)/;
  const out = [];
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'A6',
          file: relFromRoot(file),
          line: i + 1,
          message: 't() called with string fallback (should be {values} object or nothing)',
          fixHint: 'Use t(key) or t(key, { brand, count }). A fallback string is ambiguous with interpolation.',
          snippet: lines[i].trim().slice(0, 120),
        });
        break;
      }
    }
  }
  return out;
});

/* ========================================================================
 *  GROUP B · Chart contracts C1-C7 (7 rules) — DESIGN_TOKENS.md
 * ======================================================================== */

// B1: MiniSparkline width/height 默认必须 '100%'
registerRule('B1', 'B', 'chart-c1-sparkline-default · width/height 默认必须 100%', (ctx) => {
  const targets = [];
  const sparklineFile = join(FRONTEND_SRC, 'components', 'charts', 'MiniSparkline.jsx');
  if (existsSync(sparklineFile)) targets.push(sparklineFile);
  if (ctx.includeFixtures && existsSync(FIXTURES_DIR)) {
    // Also scan any fixture deliberately seeded to trigger B1.
    targets.push(...listFiles(FIXTURES_DIR, ['.jsx', '.tsx'], { includeFixtures: true })
      .filter((f) => /B1_/.test(f)));
  }
  const out = [];
  for (const file of targets) {
    const hits = grepLines(readSafe(file), /(width|height)\s*=\s*\{?\s*[0-9]+\s*\}?\s*[,\s}/]/);
    for (const h of hits) {
      out.push({
        rule: 'B1',
        file: relFromRoot(file),
        line: h.lineNumber,
        message: 'Numeric pixel default locks parent layout',
        fixHint: 'Use width="100%" / height="100%" strings so Sparkline fills the parent.',
        snippet: h.lineText.trim().slice(0, 120),
      });
    }
  }
  return out;
});

// B2: Recharts <Line stroke={...}> 禁内联 hex
registerRule('B2', 'B', 'chart-c2-engine-color-binding · stroke / fill 必须 var(--color-chart-*)', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  for (const file of files) {
    const content = readSafe(file);
    if (!/from ['"]recharts['"]/.test(content)) continue;
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (/\b(stroke|fill)\s*=\s*['"]#[0-9a-fA-F]{3,8}['"]/.test(lines[i])) {
        out.push({
          rule: 'B2',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Recharts stroke/fill hardcodes a hex color',
          fixHint: 'Use var(--color-chart-*) or themed token variable.',
          snippet: lines[i].trim().slice(0, 120),
        });
        break;
      }
    }
  }
  return out;
});

// B3: SoV others schema present (runtime assertion lives in check-data-contracts)
registerRule('B3', 'B', 'chart-c3-sov-others · mock.js 存在 SOV_PIE/SOV_OTHERS schema', () => {
  const file = join(FRONTEND_SRC, 'data', 'mock.js');
  if (!existsSync(file)) return [];
  // No regex violation expected; hand off runtime value checks to check-data-contracts.mjs.
  return [];
});

// B4: sentiment.toFixed(2) in pages — except `// C4-exempt`
registerRule('B4', 'B', 'chart-c4-sentiment-pct · sentiment 禁 .toFixed(2) (除 C4-exempt)', () => {
  const pagesDir = join(FRONTEND_SRC, 'pages');
  const files = listFiles(pagesDir, ['.jsx', '.tsx']);
  const out = [];
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/sentiment.*\.toFixed\(2\)|\.toFixed\(2\).*sentiment/.test(line)) {
        if (/\/\/\s*C4-exempt/.test(line)) continue;
        out.push({
          rule: 'B4',
          file: relFromRoot(file),
          line: i + 1,
          message: 'sentiment.toFixed(2) exposed to UI',
          fixHint: 'Use semantic labels (正面/中性/负面) or mark line with `// C4-exempt`.',
          snippet: line.trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// B5: sparkline i%N===0?±V:0 sawtooth
registerRule('B5', 'B', 'chart-c5-sparkline-sawtooth · 禁 i%N===0?±V:0 锯齿波合成', () => {
  const pagesDir = join(FRONTEND_SRC, 'pages');
  const files = listFiles(pagesDir, ['.jsx', '.tsx']);
  const re = /spark[A-Za-z]+\s*=.*i\s*%\s*[0-9]+\s*===\s*0\s*\?/;
  const out = [];
  for (const file of files) {
    const hits = grepLines(readSafe(file), re);
    for (const h of hits) {
      out.push({
        rule: 'B5',
        file: relFromRoot(file),
        line: h.lineNumber,
        message: 'Synthetic sawtooth sparkline data',
        fixHint: 'Use realistic mock data from mock.js, not modulo-zero pulses.',
        snippet: h.lineText.trim().slice(0, 120),
      });
    }
  }
  return out;
});

// B6: DonutChart size ≥ 120
registerRule('B6', 'B', 'chart-c6-donut-size-minimum · <DonutChart size={n}> 禁 n<120', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const re = /<DonutChart[^>]*\bsize\s*=\s*\{?\s*([0-9]{1,3})/;
  const out = [];
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(re);
      if (m && Number(m[1]) < 120) {
        out.push({
          rule: 'B6',
          file: relFromRoot(file),
          line: i + 1,
          message: `DonutChart size=${m[1]} below minimum 120`,
          fixHint: 'Minimum usable donut size is 120; default is 180.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// B7: ranking integrity — delegated to check-data-contracts.mjs
registerRule('B7', 'B', 'chart-c7-ranking-integrity · BRANDS/PRODUCTS ranking 契约 (运行时)', () => {
  return []; // runtime, owned by check-data-contracts.mjs
});

/* ========================================================================
 *  GROUP C · V2 analysis page contracts (15 rules) — §4.6-IA-v2.K-N/M.5/M.6/O
 * ======================================================================== */

// C9-1: BrandTopicHeatmap 禁 chart-N / sentiment-* token
registerRule('C9-1', 'C', 'heatmap 禁借 chart-N / sentiment-* token', () => {
  const file = join(FRONTEND_SRC, 'components', 'charts', 'BrandTopicHeatmap.jsx');
  if (!existsSync(file)) return [];
  const hits = grepLines(readSafe(file), /var\(--color-(chart-[0-9]|sentiment-(positive|negative|neutral))/);
  return hits.map((h) => ({
    rule: 'C9-1',
    file: relFromRoot(file),
    line: h.lineNumber,
    message: 'Heatmap uses chart-N or sentiment-* token (band must be dedicated)',
    fixHint: 'Use --color-heatmap-seq-0..5 / --color-heatmap-div-neg-2..pos-2.',
    snippet: h.lineText.trim().slice(0, 120),
  }));
});

// C9-2: BrandTopicHeatmap 禁内联 hex
registerRule('C9-2', 'C', 'heatmap 禁内联 hex (fill / background)', () => {
  const file = join(FRONTEND_SRC, 'components', 'charts', 'BrandTopicHeatmap.jsx');
  if (!existsSync(file)) return [];
  const hits = grepLines(readSafe(file), /(fill|background)[:=]\s*['"]?#[0-9a-fA-F]{3,8}/);
  return hits.map((h) => ({
    rule: 'C9-2',
    file: relFromRoot(file),
    line: h.lineNumber,
    message: 'Inline hex color in heatmap',
    fixHint: 'Use CSS variable from design tokens.',
    snippet: h.lineText.trim().slice(0, 120),
  }));
});

// C10-1: Brand Mode 6 pages mount BrandAnalysisFilterBar or useBrandAnalysisFilters
registerRule('C10-1', 'C', '6 分析页必须 mount BrandAnalysisFilterBar 或 hook (Overview 豁免)', () => {
  const brandDir = join(FRONTEND_SRC, 'pages', 'brand');
  const required = [
    'BrandVisibilityPage.jsx',
    'BrandTopicsPage.jsx',
    'BrandSentimentPage.jsx',
    'BrandCitationsPage.jsx',
    'BrandProductsPage.jsx',
    'BrandCompetitorsPage.jsx',
  ];
  const out = [];
  for (const name of required) {
    const file = join(brandDir, name);
    if (!existsSync(file)) {
      out.push({
        rule: 'C10-1',
        file: `frontend/src/pages/brand/${name}`,
        line: 0,
        message: `V2 analysis page file missing — can't verify FilterBar mount`,
        fixHint: 'Create page under pages/brand/ and import BrandAnalysisFilterBar or useBrandAnalysisFilters.',
      });
      continue;
    }
    const content = readSafe(file);
    if (!/BrandAnalysisFilterBar|useBrandAnalysisFilters/.test(content)) {
      out.push({
        rule: 'C10-1',
        file: relFromRoot(file),
        line: 0,
        message: 'Analysis page does not mount FilterBar or its hook',
        fixHint: 'import { BrandAnalysisFilterBar } from components/filters/BrandAnalysisFilterBar or the hook.',
      });
    }
  }
  return out;
});

// C10-2: analysis pages 禁本地 time state
registerRule('C10-2', 'C', '分析页禁本地 useState("7d") / dateRange / fromDate 本地 state', () => {
  const brandDir = join(FRONTEND_SRC, 'pages', 'brand');
  if (!existsSync(brandDir)) return [];
  const files = listFiles(brandDir, ['.jsx', '.tsx']);
  const re = /useState\s*\(\s*['"]7d|useState.*dateRange|useState.*fromDate/;
  const out = [];
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'C10-2',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Local time-range state bypasses URL truth source',
          fixHint: 'Read from useBrandAnalysisFilters() hook which reads URL params.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// C11-1: mock.js mentionRate literal must be 0-1 decimal (≥1 integer → fail)
registerRule('C11-1', 'C', 'mentionRate literal 必须 0-1 小数 (整数 ≥1 即违规)', (ctx) => {
  const targets = [];
  const mockFile = join(FRONTEND_SRC, 'data', 'mock.js');
  if (existsSync(mockFile)) targets.push(mockFile);
  if (ctx.includeFixtures && existsSync(FIXTURES_DIR)) {
    targets.push(...listFiles(FIXTURES_DIR, ['.js', '.jsx', '.ts', '.tsx'], { includeFixtures: true })
      .filter((f) => /C11_/.test(f)));
  }
  const re = /mentionRate:\s*[1-9][0-9]*(\.[0-9]+)?[,\s}]/;
  const out = [];
  for (const file of targets) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'C11-1',
          file: relFromRoot(file),
          line: i + 1,
          message: 'mentionRate literal ≥ 1 (must be 0-1 decimal)',
          fixHint: 'Divide by 100. UI renders as (value * 100).toFixed(1) + "%".',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// C12-1: BrandSentimentPage must import DonutChart
registerRule('C12-1', 'C', 'BrandSentimentPage 必须 import DonutChart', () => {
  const file = join(FRONTEND_SRC, 'pages', 'brand', 'BrandSentimentPage.jsx');
  if (!existsSync(file)) return [];
  const content = readSafe(file);
  if (/import.*DonutChart/.test(content)) return [];
  return [
    {
      rule: 'C12-1',
      file: relFromRoot(file),
      line: 0,
      message: 'BrandSentimentPage must import DonutChart',
      fixHint: 'Replace the 3 large-text percentages with a <DonutChart size={180} />.',
    },
  ];
});

// C12-2: 禁 text-3xl+ 直接渲染 sentiment 百分比
registerRule('C12-2', 'C', 'BrandSentimentPage 禁 text-3xl+ 大号文字百分比', () => {
  const file = join(FRONTEND_SRC, 'pages', 'brand', 'BrandSentimentPage.jsx');
  if (!existsSync(file)) return [];
  const hits = grepLines(
    readSafe(file),
    /text-(3xl|4xl|5xl).*(positive|negative|neutral)Pct|(positivePct|negativePct|neutralPct).*text-(3xl|4xl|5xl)/,
  );
  return hits.map((h) => ({
    rule: 'C12-2',
    file: relFromRoot(file),
    line: h.lineNumber,
    message: 'Large-text percentage for sentiment (anti-pattern)',
    fixHint: 'Use <DonutChart /> instead; large text hurts visual density.',
    snippet: h.lineText.trim().slice(0, 120),
  }));
});

// C13-1: CompetitorQuadrantChart radius literal > 40 banned
registerRule('C13-1', 'C', 'CompetitorQuadrantChart radius literal 禁 > 40', () => {
  const file = join(FRONTEND_SRC, 'components', 'charts', 'CompetitorQuadrantChart.jsx');
  if (!existsSync(file)) return [];
  const hits = grepLines(readSafe(file), /radius\s*=\s*[4-9][0-9]|r=\{?\s*[4-9][0-9][^0-9]/);
  return hits.map((h) => ({
    rule: 'C13-1',
    file: relFromRoot(file),
    line: h.lineNumber,
    message: 'Quadrant bubble radius > 40 will dominate viewport',
    fixHint: 'Use bubbleRadius={[rMin, rMax]} prop with default [8, 24].',
    snippet: h.lineText.trim().slice(0, 120),
  }));
});

// C13-2: Quadrant must Math.sqrt (sqrt area mapping)
registerRule('C13-2', 'C', 'CompetitorQuadrantChart 必须 Math.sqrt (sqrt 面积正比)', () => {
  const file = join(FRONTEND_SRC, 'components', 'charts', 'CompetitorQuadrantChart.jsx');
  if (!existsSync(file)) return [];
  const content = readSafe(file);
  if (/Math\.sqrt/.test(content)) return [];
  return [
    {
      rule: 'C13-2',
      file: relFromRoot(file),
      line: 0,
      message: 'CompetitorQuadrantChart missing sqrt radius mapping',
      fixHint: 'Linear mapping lets a large z-value dominate. Use Math.sqrt for proper area-proportional bubbles.',
    },
  ];
});

// C13-3: Quadrant must expose showLabels prop
registerRule('C13-3', 'C', 'CompetitorQuadrantChart 必须暴露 showLabels prop', () => {
  const file = join(FRONTEND_SRC, 'components', 'charts', 'CompetitorQuadrantChart.jsx');
  if (!existsSync(file)) return [];
  const content = readSafe(file);
  if (/showLabels/.test(content)) return [];
  return [
    {
      rule: 'C13-3',
      file: relFromRoot(file),
      line: 0,
      message: 'CompetitorQuadrantChart missing showLabels prop',
      fixHint: 'Add showLabels prop so callers can turn bubble labels on/off.',
    },
  ];
});

// C14-1: V2 analysis pages h1/h2 不得 text-2xl+
registerRule('C14-1', 'C', 'V2 分析页 h1/h2 不得 text-2xl+ (密度契约)', (ctx) => {
  const targets = [];
  const brandDir = join(FRONTEND_SRC, 'pages', 'brand');
  if (existsSync(brandDir)) targets.push(...listFiles(brandDir, ['.jsx', '.tsx']));
  if (ctx.includeFixtures && existsSync(FIXTURES_DIR)) {
    targets.push(...listFiles(FIXTURES_DIR, ['.jsx', '.tsx'], { includeFixtures: true })
      .filter((f) => /C14_/.test(f)));
  }
  const out = [];
  const re = /<h[12][^>]*text-(2xl|3xl|4xl)/;
  for (const file of targets) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        if (/\/\/\s*C14-exempt/.test(lines[i])) continue;
        out.push({
          rule: 'C14-1',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Heading uses text-2xl or larger (violates density contract)',
          fixHint: 'Use text-xl for page title per DESIGN_TOKENS C14.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// C14-2: V2 analysis pages 禁 p-[4-9] Card padding
registerRule('C14-2', 'C', 'V2 分析页 Card 禁 p-[4-9] padding', () => {
  const brandDir = join(FRONTEND_SRC, 'pages', 'brand');
  if (!existsSync(brandDir)) return [];
  const files = listFiles(brandDir, ['.jsx', '.tsx']);
  const out = [];
  const re = /className=["'][^"']*\bp-[4-9]\b/;
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        if (/\/\/\s*C14-exempt/.test(lines[i])) continue;
        out.push({
          rule: 'C14-2',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Card padding >= p-4 (should be p-3 per density contract)',
          fixHint: 'Use p-3 as the analysis-page default.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// C14-3: V2 analysis page root div 禁 space-y-[4-9]
registerRule('C14-3', 'C', 'V2 分析页根 div 禁 space-y-[4-9]', () => {
  const brandDir = join(FRONTEND_SRC, 'pages', 'brand');
  if (!existsSync(brandDir)) return [];
  const files = listFiles(brandDir, ['.jsx', '.tsx']);
  const out = [];
  const re = /return\s*\(\s*<div\s+className=["'][^"']*space-y-[4-9]/;
  for (const file of files) {
    const content = readSafe(file);
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      // multi-line friendly: use a windowed regex
      const window = lines.slice(i, i + 3).join('\n');
      if (re.test(window)) {
        out.push({
          rule: 'C14-3',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Root div spacing >= space-y-4 (should be space-y-3)',
          fixHint: 'Use space-y-3 as the analysis-page root rhythm.',
          snippet: lines[i].trim().slice(0, 120),
        });
        break;
      }
    }
  }
  return out;
});

// C15-1: BrandProductDetailPage 禁从 useParams() 解构 brandId
registerRule('C15-1', 'C', 'BrandProductDetailPage 禁 useParams 解构 brandId (走 query string)', () => {
  const candidates = [
    join(FRONTEND_SRC, 'pages', 'BrandProductDetailPage.jsx'),
    join(FRONTEND_SRC, 'pages', 'brand', 'BrandProductDetailPage.jsx'),
  ];
  const out = [];
  for (const file of candidates) {
    if (!existsSync(file)) continue;
    const lines = readSafe(file).split(/\r?\n/);
    const re = /useParams\(\)[^{]*\{[^}]*\bbrandId\b/;
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'C15-1',
          file: relFromRoot(file),
          line: i + 1,
          message: 'brandId destructured from useParams() — it must come from query string',
          fixHint: 'Use const brandId = useSearchParams()[0].get("brandId"). The path only carries :productId.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// C15-2: BrandProductDetailPage must import useSearchParams
registerRule('C15-2', 'C', 'BrandProductDetailPage 必须 import useSearchParams', () => {
  const candidates = [
    join(FRONTEND_SRC, 'pages', 'BrandProductDetailPage.jsx'),
    join(FRONTEND_SRC, 'pages', 'brand', 'BrandProductDetailPage.jsx'),
  ];
  const existing = candidates.filter((p) => existsSync(p));
  if (existing.length === 0) return [];
  const out = [];
  for (const file of existing) {
    const content = readSafe(file);
    if (!/useSearchParams/.test(content)) {
      out.push({
        rule: 'C15-2',
        file: relFromRoot(file),
        line: 0,
        message: 'BrandProductDetailPage missing useSearchParams import',
        fixHint: 'Import useSearchParams from react-router-dom and read ?brandId=.',
      });
    }
  }
  return out;
});

// C15-3: 空状态守卫只能 basis productId
registerRule('C15-3', 'C', '空状态守卫禁 !brand 导致整页空白', () => {
  const candidates = [
    join(FRONTEND_SRC, 'pages', 'BrandProductDetailPage.jsx'),
    join(FRONTEND_SRC, 'pages', 'brand', 'BrandProductDetailPage.jsx'),
  ];
  const out = [];
  for (const file of candidates) {
    if (!existsSync(file)) continue;
    const lines = readSafe(file).split(/\r?\n/);
    const re = /if\s*\(\s*!brand[^)]*\)\s*\{?\s*return\b.*(Empty|暂无)/;
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i])) {
        out.push({
          rule: 'C15-3',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Empty-state guard triggered by !brand blanks the entire page',
          fixHint: 'Guard by !product only. brand may be null (fallback to product.brand).',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

/* ========================================================================
 *  GROUP D · Product decisions (7 rules) — §4.1.1-gate / §4.1.1e / §4.11.5 / §4.6-IA-v2
 * ======================================================================== */

const LEGACY_REDIRECTS = [
  ['/dashboard', '/brand/overview'],
  ['/topics', '/brand/topics'],
  ['/industry', '/industry/overview'],
  ['/industries', '/industry/overview'],
  ['/industries/:id', '/industry/overview?industryId='],
  ['/knowledge-graph', '/industry/knowledge-graph'],
  ['/diagnostics', '/brand/diagnostics'],
  ['/reports', '/brand/reports'],
  ['/brands/:id', '/brand/overview?brandId='],
  ['/brands/:id/simulator', '/brand/citations?sub=simulator'],
  ['/brands/:id/products/:productId', '/brand/products/:productId?brandId='],
];

// D1: Auth-gate route guard — at least one of the gated routes references RequireAuth / middleware / RouteGuard
registerRule('D1', 'D', 'auth-gate-route-guard · /brand /industry /reports /brands 必须有 RequireAuth', () => {
  const appFile = join(FRONTEND_SRC, 'App.jsx');
  if (!existsSync(appFile)) return [];
  const content = readSafe(appFile);
  const hasGuard =
    /RequireAuth|RouteGuard|AuthGuard|requireAuth/.test(content) ||
    /middleware\.ts/.test(content);
  if (hasGuard) return [];
  return [
    {
      rule: 'D1',
      file: 'frontend/src/App.jsx',
      line: 0,
      message: 'No auth gate (RequireAuth / RouteGuard) referenced in App.jsx for /brand /industry /reports',
      fixHint: 'Wrap gated routes with <RequireAuth>…</RequireAuth>; anonymous → /register?redirect=.',
    },
  ];
});

// D2: logout 6-step order — mixpanel.reset() 必须晚于 track('user_logged_out')
registerRule('D2', 'D', 'logout-6-step-order · track 必须晚于 reset', () => {
  const hookFiles = [
    join(FRONTEND_SRC, 'hooks', 'useLogout.ts'),
    join(FRONTEND_SRC, 'hooks', 'useLogout.js'),
    join(FRONTEND_SRC, 'hooks', 'useLogout.tsx'),
    join(FRONTEND_SRC, 'hooks', 'useLogout.jsx'),
  ];
  const existing = hookFiles.find((f) => existsSync(f));
  if (!existing) return []; // optional; hook not yet created
  const content = readSafe(existing);
  const idxTrack = content.search(/track\s*\(\s*['"]user_logged_out['"]/);
  const idxReset = content.search(/mixpanel\.reset\s*\(/);
  if (idxTrack === -1 || idxReset === -1) return [];
  if (idxTrack < idxReset) return []; // correct order
  return [
    {
      rule: 'D2',
      file: relFromRoot(existing),
      line: 0,
      message: 'mixpanel.reset() called before track("user_logged_out") — loses attribution',
      fixHint: 'Order: track(user_logged_out) → mixpanel.reset() → clearSession → navigate.',
    },
  ];
});

// D3: Mixpanel PII redline — track()/identify() 2nd arg禁 email/phone/token/password/company_name/ip_address
registerRule('D3', 'D', 'mixpanel-pii-redline · 事件属性禁 PII', (ctx) => {
  const files = listFiles(FRONTEND_SRC, ['.jsx', '.tsx', '.js', '.ts'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  // Match: track('evt', { email: ..., ... })
  const trackRe = /\b(track|identify)\s*\([^)]*\{[^}]*\b(email|phone|token|password|company_name|ip_address)\s*:/;
  // But allow `email_domain:`
  for (const file of files) {
    if (/lib\/analytics\./.test(file)) continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (trackRe.test(line) && !/email_domain\s*:/.test(line)) {
        out.push({
          rule: 'D3',
          file: relFromRoot(file),
          line: i + 1,
          message: 'PII (email/phone/token/password/company_name/ip_address) in analytics event properties',
          fixHint: 'Remove PII; use email_domain (after @) only if required.',
          snippet: line.trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// D4: 11 Legacy 301 redirects — all must appear in App.jsx
registerRule('D4', 'D', 'legacy-301 · 11 条 Legacy redirect 全覆盖', (ctx) => {
  const targets = [];
  const appFile = join(FRONTEND_SRC, 'App.jsx');
  if (existsSync(appFile)) targets.push(appFile);
  if (ctx.includeFixtures && existsSync(FIXTURES_DIR)) {
    targets.push(...listFiles(FIXTURES_DIR, ['.jsx', '.tsx'], { includeFixtures: true })
      .filter((f) => /D4_/.test(f)));
  }
  const out = [];
  for (const file of targets) {
    const content = readSafe(file);
    for (const [from /*, to */] of LEGACY_REDIRECTS) {
      // Loose match: path="/dashboard" or from="/dashboard".
      const esc = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/:\w+/g, '[^"\']+');
      const re = new RegExp(`(path|from)\\s*=\\s*["']${esc}["']`);
      if (!re.test(content)) {
        out.push({
          rule: 'D4',
          file: relFromRoot(file),
          line: 0,
          message: `Legacy redirect missing: ${from}`,
          fixHint: `Add a <Route> or <Navigate> mapping ${from} → V2 path.`,
        });
      }
    }
  }
  return out;
});

// D5: /brands/:id and /brands/:id/products/:pid 301 — subset of D4 but distinct
registerRule('D5', 'D', 'brand-detail-legacy-301 · brand/product detail 301', () => {
  const appFile = join(FRONTEND_SRC, 'App.jsx');
  if (!existsSync(appFile)) return [];
  const content = readSafe(appFile);
  const out = [];
  const required = ['/brands/:id', '/brands/:id/products/:productId'];
  for (const route of required) {
    const esc = route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/:\w+/g, '[^"\']+');
    const re = new RegExp(`(path|from)\\s*=\\s*["']${esc}["']`);
    if (!re.test(content)) {
      out.push({
        rule: 'D5',
        file: 'frontend/src/App.jsx',
        line: 0,
        message: `Brand detail legacy route missing: ${route}`,
        fixHint: 'Add Navigate to V2 equivalent with brandId query param.',
      });
    }
  }
  return out;
});

// D6: Anonymous data-API gate — no anonymous endpoints outside whitelist
registerRule('D6', 'D', 'auth-required-anonymous-data-api · 无匿名数据 API', () => {
  const apiDir = join(PROJECT_ROOT, 'backend', 'src', 'app', 'api');
  if (!existsSync(apiDir)) return []; // backend API not implemented yet
  const files = listFiles(apiDir, ['.ts', '.tsx', '.js']);
  const out = [];
  const whitelist = /\/(auth|health|og|sitemap)\//;
  for (const file of files) {
    if (whitelist.test(file.replace(/\\/g, '/'))) continue;
    const content = readSafe(file);
    if (!/requireAuth|withAuth|getSession/.test(content)) {
      out.push({
        rule: 'D6',
        file: relFromRoot(file),
        line: 0,
        message: 'API route does not call requireAuth',
        fixHint: 'Wrap handler with requireAuth(req) or withAuth().',
      });
    }
  }
  return out;
});

// D7: Onboarding draft route guard — middleware redirects zero-project users to /onboarding
registerRule('D7', 'D', 'onboarding-draft-route-guard · projects.length===0 → /onboarding', () => {
  const middlewareCandidates = [
    join(PROJECT_ROOT, 'backend', 'middleware.ts'),
    join(PROJECT_ROOT, 'backend', 'src', 'middleware.ts'),
    join(FRONTEND_SRC, 'routes', 'RouteGuard.jsx'),
    join(FRONTEND_SRC, 'routes', 'RouteGuard.tsx'),
  ];
  const existing = middlewareCandidates.find((p) => existsSync(p));
  if (!existing) return []; // not yet implemented; Session 4a will add
  const content = readSafe(existing);
  if (/projects\.length\s*===\s*0/.test(content) && /\/onboarding/.test(content)) return [];
  return [
    {
      rule: 'D7',
      file: relFromRoot(existing),
      line: 0,
      message: 'Route guard does not redirect zero-project users to /onboarding',
      fixHint: 'Detect session user with projects.length === 0 and return NextResponse.redirect(/onboarding).',
    },
  ];
});

// D8: ADMIN_JWT_SECRET must come from env, never from a string-literal assignment.
registerRule('D8', 'D', 'no-hardcoded-jwt-secret · ADMIN_JWT_SECRET 禁字面量赋值', (ctx) => {
  const backendSrc = join(PROJECT_ROOT, 'backend', 'src');
  if (!existsSync(backendSrc)) return [];
  const files = listFiles(backendSrc, ['.ts', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  // Flag `ADMIN_JWT_SECRET = '...literal...'` but NOT `process.env.ADMIN_JWT_SECRET = '...'`
  // (the latter is an env-var write, only legitimate in test setup — and tests
  // live under backend/tests/**, not backend/src/**).
  const hardcodeRe = /(?<!process\.env\.)\bADMIN_JWT_SECRET\s*=\s*['"`]([^'"`\n]*)['"`]/;
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip comment lines — docstrings reference the banned pattern by name.
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) continue;
      const m = hardcodeRe.exec(line);
      if (!m) continue;
      out.push({
        rule: 'D8',
        file: relFromRoot(file),
        line: i + 1,
        message: 'ADMIN_JWT_SECRET assigned from a string literal — must read from process.env only',
        fixHint: 'Replace with `process.env.ADMIN_JWT_SECRET` read inside readSecret(); assert length ≥ 32 bytes.',
        snippet: line.trim().slice(0, 120),
      });
    }
  }
  return out;
});

// D9: bcrypt cost must be ≥ 12, and admin password hashing must funnel through hashPassword().
registerRule('D9', 'D', 'admin-password-bcrypt-cost-at-least-12 · bcrypt cost ≥ 12 + 必须走 hashPassword()', (ctx) => {
  const backendSrc = join(PROJECT_ROOT, 'backend', 'src');
  if (!existsSync(backendSrc)) return [];
  // Only evaluate files under admin/** or the self-seeded fixtures dir. D9 is
  // scoped to admin password hashing; future user-facing auth gets its own rule.
  const files = listFiles(backendSrc, ['.ts', '.tsx'], { includeFixtures: ctx.includeFixtures })
    .filter((p) => /[\\/]admin[\\/]/.test(p) || /__ci_fixtures__/.test(p));
  const out = [];
  // Match `bcrypt.hash(x, N)` with a NUMERIC literal cost. Non-numeric second
  // args (e.g., BCRYPT_COST constant imported from constants.ts) are the
  // permitted funnel — they flow through the constants module where D9
  // contract is enforced by a separate unit test.
  const hashRe = /bcrypt(?:js)?\s*\.\s*hash(?:Sync)?\s*\(\s*[^,]+,\s*(\d+)\s*\)/;
  const whitelist = [
    // password.ts is the single approved hashPassword() funnel. It imports
    // BCRYPT_COST so its bcrypt.hash(pw, BCRYPT_COST) will not match this
    // numeric-literal regex anyway — but we whitelist defensively.
    /[\\/]admin[\\/]auth[\\/]password\.ts$/,
  ];
  for (const file of files) {
    if (whitelist.some((re) => re.test(file))) continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) continue;
      const m = hashRe.exec(line);
      if (!m) continue;
      const cost = Number(m[1]);
      if (cost >= 12) continue;
      out.push({
        rule: 'D9',
        file: relFromRoot(file),
        line: i + 1,
        message: `bcrypt cost=${cost} is below the required minimum of 12`,
        fixHint: 'Route admin password hashing through hashPassword() in src/admin/auth/password.ts (cost = BCRYPT_COST = 12).',
        snippet: line.trim().slice(0, 120),
      });
    }
  }
  return out;
});

// D10: admin session cookies must use SameSite=Strict. Lax/None breaks CSRF defense.
registerRule('D10', 'D', 'admin-session-cookie-samesite-strict · Admin cookie 必须 SameSite=Strict', (ctx) => {
  const cookieFile = join(PROJECT_ROOT, 'backend', 'src', 'admin', 'auth', 'cookies.ts');
  const backendSrc = join(PROJECT_ROOT, 'backend', 'src');
  if (!existsSync(backendSrc)) return [];
  // Scan all of backend/src so __ci_fixtures__/ files are reachable, but only
  // evaluate files whose path includes `admin` or the fixtures dir — bare
  // sameSite: 'lax' elsewhere (e.g., future user-facing auth) is not in scope.
  const files = listFiles(backendSrc, ['.ts', '.tsx'], { includeFixtures: ctx.includeFixtures })
    .filter((p) => /[\\/]admin[\\/]/.test(p) || /__ci_fixtures__/.test(p));
  // The cookies module itself must type `sameSite: 'strict' | 'lax' | 'none'`
  // (union is OK) AND set sameSite to 'strict' (never 'lax'/'none') when
  // building the access/refresh cookie options.
  const out = [];
  // Flag any literal `sameSite: 'lax'` or `sameSite: 'none'` inside admin code.
  const loosenedRe = /\bsameSite\s*:\s*['"](lax|none)['"]/i;
  // Flag SameSite cookie-header strings set to Lax/None in any admin module.
  const headerRe = /\bSameSite\s*=\s*(Lax|None)\b/;
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) continue;
      const m = loosenedRe.exec(line) || headerRe.exec(line);
      if (!m) continue;
      out.push({
        rule: 'D10',
        file: relFromRoot(file),
        line: i + 1,
        message: `Admin cookie uses SameSite=${m[1]} — must be Strict to block CSRF`,
        fixHint: 'Set sameSite: "strict" in all admin cookie setters; the type union allows "lax"/"none" only for compatibility with shared interfaces.',
        snippet: line.trim().slice(0, 120),
      });
    }
  }
  // Extra guardrail: cookies.ts must mention 'strict' explicitly.
  if (existsSync(cookieFile)) {
    const content = readSafe(cookieFile);
    if (!/sameSite\s*:\s*['"]strict['"]/.test(content)) {
      out.push({
        rule: 'D10',
        file: relFromRoot(cookieFile),
        line: 0,
        message: 'backend/src/admin/auth/cookies.ts does not declare sameSite: "strict" on any cookie setter',
        fixHint: 'At minimum one call site must set sameSite: "strict" — this is the contract for admin_access_token / admin_refresh_token.',
      });
    }
  }
  return out;
});

/* ========================================================================
 *  GROUP E · Citation + KG contracts (4 rules) — §4.2.6 / §4.2.7 / Decision #19
 * ======================================================================== */

// E1: Tier weights must not be hardcoded
registerRule('E1', 'E', 'citation-tier-not-hardcoded · Tier 权重禁硬编码', () => {
  const searchDirs = [
    join(FRONTEND_SRC, 'pages'),
    join(FRONTEND_SRC, 'components'),
    join(PROJECT_ROOT, 'backend', 'src'),
  ];
  const out = [];
  for (const dir of searchDirs) {
    if (!existsSync(dir)) continue;
    const files = listFiles(dir, ['.ts', '.tsx', '.js', '.jsx']);
    for (const file of files) {
      const lines = readSafe(file).split(/\r?\n/);
      for (let i = 0; i < lines.length; i++) {
        if (/const\s+TIER_WEIGHTS\s*=\s*\{/.test(lines[i]) || /tierWeight\s*=\s*[0-9]+\.[0-9]+\s*[,;]/.test(lines[i])) {
          out.push({
            rule: 'E1',
            file: relFromRoot(file),
            line: i + 1,
            message: 'Citation tier weight hardcoded',
            fixHint: 'Load from citation_domain_authority table via parameter_service.',
            snippet: lines[i].trim().slice(0, 120),
          });
        }
      }
    }
  }
  return out;
});

// E2: URL normalization must use tldts
registerRule('E2', 'E', 'url-normalization-tldts · citation URL 必须走 tldts', () => {
  const citationDirs = [
    join(FRONTEND_SRC, 'components', 'citation'),
    join(FRONTEND_SRC, 'lib', 'citation'),
    join(PROJECT_ROOT, 'backend', 'src', 'services', 'citation'),
    join(PROJECT_ROOT, 'backend', 'src', 'parser'),
  ];
  const out = [];
  for (const dir of citationDirs) {
    if (!existsSync(dir)) continue;
    const files = listFiles(dir, ['.ts', '.tsx', '.js', '.jsx']);
    for (const file of files) {
      const content = readSafe(file);
      const usesURL = /new URL\(/.test(content) && /\.hostname/.test(content);
      const usesTldts = /from ['"]tldts['"]/.test(content);
      if (usesURL && !usesTldts) {
        out.push({
          rule: 'E2',
          file: relFromRoot(file),
          line: 0,
          message: 'Citation domain parsing uses new URL(...).hostname without tldts',
          fixHint: "import { parse } from 'tldts' and use parse(url).domain for eTLD+1.",
        });
      }
    }
  }
  return out;
});

// E3: citation_attribution_mismatch vs citation_source_loss mutex
registerRule('E3', 'E', 'citation-attribution-diagnostic-mutex · 同函数不得同时 emit 两类 alert', () => {
  const diagDirs = [
    join(PROJECT_ROOT, 'backend', 'src', 'services', 'diagnostics'),
    join(FRONTEND_SRC, 'services', 'diagnostics'),
  ];
  const out = [];
  for (const dir of diagDirs) {
    if (!existsSync(dir)) continue;
    const files = listFiles(dir, ['.ts', '.tsx', '.js', '.jsx']);
    for (const file of files) {
      const content = readSafe(file);
      if (/citation_attribution_mismatch/.test(content) && /citation_source_loss/.test(content)) {
        // Heuristic: both identifiers in same function body — check 20-line proximity
        const lines = content.split(/\r?\n/);
        for (let i = 0; i < lines.length; i++) {
          if (/citation_attribution_mismatch/.test(lines[i])) {
            const window = lines.slice(Math.max(0, i - 20), Math.min(lines.length, i + 20)).join('\n');
            if (/citation_source_loss/.test(window)) {
              out.push({
                rule: 'E3',
                file: relFromRoot(file),
                line: i + 1,
                message: 'attribution_mismatch and source_loss both emitted in same function (they are mutex)',
                fixHint: 'Branch early: pick one diagnostic per response, never both.',
              });
              break;
            }
          }
        }
      }
    }
  }
  return out;
});

// E4: pr_score formula must not inline tier × trending coefficients
registerRule('E4', 'E', 'pr-score-not-hardcoded · pr_score 系数必须参数服务', () => {
  const dirs = [
    join(FRONTEND_SRC, 'pages'),
    join(FRONTEND_SRC, 'components', 'citation'),
    join(PROJECT_ROOT, 'backend', 'src'),
  ];
  const out = [];
  const re = /prScore\s*=\s*.*\*\s*[0-9]*\.?[0-9]+\s*\*\s*[0-9]*\.?[0-9]+/;
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    const files = listFiles(dir, ['.ts', '.tsx', '.js', '.jsx']);
    for (const file of files) {
      const lines = readSafe(file).split(/\r?\n/);
      for (let i = 0; i < lines.length; i++) {
        if (re.test(lines[i])) {
          out.push({
            rule: 'E4',
            file: relFromRoot(file),
            line: i + 1,
            message: 'pr_score computed with hardcoded coefficients',
            fixHint: 'Load tier_weight / trending_coefficient / kol_diversity_weight from parameter_service.',
            snippet: lines[i].trim().slice(0, 120),
          });
        }
      }
    }
  }
  return out;
});

/* ========================================================================
 *  GROUP F · Adapter framework (Session 1) — ADAPTER_CONTRACT §2 / §5 / §8
 * ======================================================================== */

const BACKEND_SRC = join(PROJECT_ROOT, 'backend', 'src');
const BACKEND_TESTS = join(PROJECT_ROOT, 'backend', 'tests');
const HAR_FIXTURES_DIR = join(BACKEND_TESTS, 'fixtures', 'adapters');

// F1: adapters must go through humanize.ts — bare playwright launches banned
registerRule('F1', 'F', 'no-bare-playwright-import · 适配器禁直接 import playwright 启动', (ctx) => {
  const files = listFiles(BACKEND_SRC, ['.ts', '.tsx'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  // Whitelisted files that DO need raw playwright access.
  const whitelist = [
    /[\\/]engines[\\/]behavior[\\/]humanize\.ts$/,
    /[\\/]engines[\\/]behavior[\\/]camoufox-launch\.ts$/, // Session 1.2 reserved
    /[\\/]engines[\\/]har[\\/]recorder\.ts$/,            // Session 1.2 reserved
  ];
  const importRe = /from\s+['"]playwright(-extra|-core)?['"]/;
  const chromiumRe = /import\s*\{\s*[^}]*\b(chromium|firefox|webkit)\b[^}]*\}\s*from\s*['"]playwright(-extra|-core)?['"]/;
  for (const file of files) {
    if (whitelist.some((re) => re.test(file))) continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip comment lines — doc-strings commonly reference the banned pattern
      // by name (e.g., "Harness F1 bans `import { chromium } from 'playwright'`").
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;
      if (importRe.test(line) || chromiumRe.test(line)) {
        out.push({
          rule: 'F1',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Direct playwright import outside humanize.ts / camoufox-launch.ts',
          fixHint: 'Go through src/engines/behavior/humanize.ts so jitter/stealth policies cannot be bypassed.',
          snippet: line.trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// F2: HAR fixtures must not leak raw secrets post-sanitize
registerRule('F2', 'F', 'har-fixture-secret-leak · HAR 固件不得含未脱敏的凭据', (ctx) => {
  if (!existsSync(HAR_FIXTURES_DIR)) return [];
  const out = [];
  const fixtureFiles = [];
  const walk = (p) => {
    for (const name of readdirSync(p)) {
      const full = join(p, name);
      let s;
      try { s = statSync(full); } catch { continue; }
      if (s.isDirectory()) {
        if (!ctx.includeFixtures && name === '__ci_fixtures__') continue;
        walk(full);
      } else if (name.endsWith('.har') || name.endsWith('.har.json')) {
        fixtureFiles.push(full);
      }
    }
  };
  walk(HAR_FIXTURES_DIR);

  // HAR 1.2 stores headers as [{ "name": "...", "value": "..." }] arrays and
  // response bodies under `content.text` as an embedded JSON STRING with
  // escaped quotes (\"refresh_token\":\"...\"). Patterns below cover both.
  const patterns = [
    // Header name/value pair form (HAR spec): Authorization Bearer
    { re: /"name"\s*:\s*"Authorization"\s*,\s*"value"\s*:\s*"(?!__REDACTED__)Bearer\s+\S{8,}/i, label: 'unredacted Authorization: Bearer token' },
    // Header name/value pair form: Set-Cookie
    { re: /"name"\s*:\s*"Set-Cookie"\s*,\s*"value"\s*:\s*"(?!__REDACTED__)\S+=/i, label: 'unredacted Set-Cookie value' },
    // Header name/value pair form: Cookie request header
    { re: /"name"\s*:\s*"Cookie"\s*,\s*"value"\s*:\s*"(?!__REDACTED__)\S+=/i, label: 'unredacted Cookie header' },
    // Response body embedded JSON (escaped): \"refresh_token\":\"...\"
    { re: /\\"refresh_token\\"\s*:\s*\\"(?!__REDACTED__)[^"\\]+\\"/, label: 'unredacted refresh_token body (escaped)' },
    { re: /\\"access_token\\"\s*:\s*\\"(?!__REDACTED__)[A-Za-z0-9._-]{16,}\\"/, label: 'unredacted access_token body (escaped)' },
    { re: /\\"password\\"\s*:\s*\\"(?!__REDACTED__)[^"\\]+\\"/, label: 'unredacted password body (escaped)' },
    // Fallback: unescaped JSON bodies (if HAR post-processed into pretty JSON)
    { re: /(?<!\\)"refresh_token"\s*:\s*"(?!__REDACTED__)[^"]+"/, label: 'unredacted refresh_token body' },
    { re: /(?<!\\)"access_token"\s*:\s*"(?!__REDACTED__)[A-Za-z0-9._-]{16,}"/, label: 'unredacted access_token body' },
    { re: /(?<!\\)"password"\s*:\s*"(?!__REDACTED__)[^"]+"/, label: 'unredacted password body' },
  ];
  for (const file of fixtureFiles) {
    const content = readSafe(file);
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      for (const { re, label } of patterns) {
        if (re.test(lines[i])) {
          out.push({
            rule: 'F2',
            file: relFromRoot(file),
            line: i + 1,
            message: `HAR fixture leaks: ${label}`,
            fixHint: 'Re-run scripts/record-har.ts on the HAR; sanitizeHar replaces the value with __REDACTED__.',
            snippet: lines[i].trim().slice(0, 120),
          });
          break;
        }
      }
    }
  }
  return out;
});

// F3: adapter/HAR-replay tests must pull prompts from queries.json, not inline
registerRule('F3', 'F', 'no-inline-prompt-literal · adapter 测试禁 inline prompt 字面量', (ctx) => {
  const dirs = [
    join(BACKEND_TESTS, 'unit'),
    join(BACKEND_TESTS, 'integration'),
  ];
  const out = [];
  const promptLiteralRe = /\bprompt\s*:\s*['"`]([^'"`\n]{15,})['"`]/;
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    const files = listFiles(dir, ['.ts', '.tsx'], { includeFixtures: ctx.includeFixtures });
    for (const file of files) {
      const content = readSafe(file);
      // In-scope: anything that exercises a real adapter against HAR/fixtures.
      const exercisesAdapter = /routeFromHAR|adapter\.execute\(|AdapterBundle|DoubaoWebAdapter|DeepSeekWebAdapter|ChatGptWebAdapter/.test(content);
      if (!exercisesAdapter) continue;
      // Allowed when the file loads queries.json directly.
      const loadsQueries = /fixtures\/scraping\/queries\.json|fromQueryFixture\(/.test(content);
      if (loadsQueries) continue;
      const lines = content.split(/\r?\n/);
      for (let i = 0; i < lines.length; i++) {
        const m = promptLiteralRe.exec(lines[i]);
        if (m) {
          out.push({
            rule: 'F3',
            file: relFromRoot(file),
            line: i + 1,
            message: `Inline prompt literal in adapter test: "${m[1].slice(0, 40)}…"`,
            fixHint: 'Reference tests/fixtures/scraping/queries.json by id; do not hard-code prompt text in test files.',
            snippet: lines[i].trim().slice(0, 120),
          });
        }
      }
    }
  }
  return out;
});

/* ========================================================================
 *  GROUP G · Pipeline Planner (Session 2) — PRD §4.2 / §4.10.3.A / DATA_MODEL §2.3
 * ======================================================================== */

const BACKEND_PRISMA = join(PROJECT_ROOT, 'backend', 'prisma');
const MIGRATIONS_DIR = join(BACKEND_PRISMA, 'migrations');
const PLANNER_DIR = join(BACKEND_SRC, 'platform', 'planner');

// G1: Intent × Engine × Locale matrix must stay at 23 explicit rows (PRD §4.10.3.A)
// Any drift to EXPECTED_EXPLICIT_ROW_COUNT without a matching PRD table update is
// a red flag — the constant is the row count contract.
registerRule('G1', 'G', 'planner-matrix-row-count-23 · Intent×Engine×Locale 矩阵必须锁 23 行', (ctx) => {
  const files = listFiles(BACKEND_SRC, ['.ts'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  const re = /EXPECTED_EXPLICIT_ROW_COUNT\s*=\s*(\d+)/;
  for (const file of files) {
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const m = re.exec(lines[i]);
      if (m && m[1] !== '23') {
        out.push({
          rule: 'G1',
          file: relFromRoot(file),
          line: i + 1,
          message: `EXPECTED_EXPLICIT_ROW_COUNT is ${m[1]}, must be 23 (PRD §4.10.3.A)`,
          fixHint: 'Update PRD §4.10.3.A matrix + MATRIX_ROWS + tests together; do not drop the 23 invariant.',
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// G2: topic-planner.ts / prompt-generator.ts must wire the category-purity guard.
// Dropping the call silently lets brand names leak into 品类 dimension content
// (decision #16 & PRD §4.2.1a). The rule is a structural require-token check.
registerRule('G2', 'G', 'planner-category-purity-guard-wired · 品类维度必经 category-purity 守卫', (ctx) => {
  const out = [];
  const requirements = [
    { basenamePattern: /topic-planner/, requiredToken: 'validateCategoryTopicPurity' },
    { basenamePattern: /prompt-generator/, requiredToken: 'validateCategoryPromptPurity' },
  ];
  const scanDir = (dir) => {
    if (!existsSync(dir)) return;
    const files = listFiles(dir, ['.ts'], { includeFixtures: ctx.includeFixtures });
    for (const file of files) {
      const base = file.split(sep).pop() || '';
      for (const { basenamePattern, requiredToken } of requirements) {
        if (!basenamePattern.test(base)) continue;
        const content = readSafe(file);
        if (!content.includes(requiredToken)) {
          out.push({
            rule: 'G2',
            file: relFromRoot(file),
            line: 0,
            message: `Planner file missing purity guard call: ${requiredToken}`,
            fixHint: `Import and invoke ${requiredToken} from ./category-purity.js before emitting 品类 dimension output.`,
          });
        }
      }
    }
  };
  scanDir(PLANNER_DIR);
  return out;
});

// G3: Session 2 Decision 1 — no new columns on query_executions for persona
// data. Persona rides in attempts.browser_profile JSONB (Adapter §6). Adding
// a persona_snapshot / agent_profile_id column silently re-introduces the
// denormalized duplicate we deliberately banned.
registerRule('G3', 'G', 'query-execution-no-persona-column · 禁在 query_executions 加 persona 列', (ctx) => {
  if (!existsSync(MIGRATIONS_DIR)) return [];
  const out = [];
  const sqlFiles = [];
  const walk = (p) => {
    for (const name of readdirSync(p)) {
      const full = join(p, name);
      let s;
      try { s = statSync(full); } catch { continue; }
      if (s.isDirectory()) {
        if (!ctx.includeFixtures && name === '__ci_fixtures__') continue;
        walk(full);
      } else if (name.endsWith('.sql')) {
        sqlFiles.push(full);
      }
    }
  };
  walk(MIGRATIONS_DIR);
  const bannedColumn = /\b(persona_snapshot|persona_profile|agent_profile_snapshot|agent_profile_id|persona_id)\b/;
  for (const file of sqlFiles) {
    const content = readSafe(file);
    // Only matters if the file touches query_executions at all.
    if (!/query_executions/i.test(content)) continue;
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip SQL comments
      if (/^\s*--/.test(line)) continue;
      if (bannedColumn.test(line)) {
        out.push({
          rule: 'G3',
          file: relFromRoot(file),
          line: i + 1,
          message: 'query_executions gained a persona column; Decision #26.C1 requires persona live in attempts.browser_profile',
          fixHint: 'Drop the column. Persist persona snapshot inside query_execution_attempts.browser_profile JSONB instead.',
          snippet: line.trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

// G4: planner modules (except the matrix itself) must derive engine lists
// from ENGINES / lookupMatrix(), not re-type `['doubao','deepseek','chatgpt']`
// inline. Duplicated literals drift when a 4th engine lands (see #21.F).
registerRule('G4', 'G', 'planner-no-hardcoded-engine-list · Planner 禁硬编码 3 家引擎数组字面量', (ctx) => {
  if (!existsSync(PLANNER_DIR)) return [];
  const files = listFiles(PLANNER_DIR, ['.ts'], { includeFixtures: ctx.includeFixtures });
  const out = [];
  // Array literal containing all 3 engine name strings in any order.
  const allThree = /\[[^\]]*['"]doubao['"][^\]]*['"]deepseek['"][^\]]*['"]chatgpt['"][^\]]*\]|\[[^\]]*['"]chatgpt['"][^\]]*['"]deepseek['"][^\]]*['"]doubao['"][^\]]*\]|\[[^\]]*['"]deepseek['"][^\]]*['"]doubao['"][^\]]*['"]chatgpt['"][^\]]*\]/;
  for (const file of files) {
    const base = file.split(sep).pop() || '';
    // Whitelist: the matrix file IS the source of truth and must enumerate.
    if (base === 'intent-engine-locale-matrix.ts') continue;
    const lines = readSafe(file).split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip comment lines — docs frequently name the 3 engines prose-style.
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;
      if (allThree.test(line)) {
        out.push({
          rule: 'G4',
          file: relFromRoot(file),
          line: i + 1,
          message: 'Hard-coded engine list duplicates intent-engine-locale-matrix.ts ENGINES',
          fixHint: 'Import ENGINES or derive via lookupMatrix(); a 4th engine should only need to edit the matrix.',
          snippet: line.trim().slice(0, 120),
        });
      }
    }
  }
  return out;
});

/* ---------------- Runner ---------------- */

function runAll({ includeFixtures = false, onlyRuleId = null } = {}) {
  const ctx = { includeFixtures };
  const report = [];
  for (const rule of rules) {
    if (onlyRuleId && rule.id !== onlyRuleId) continue;
    let violations = [];
    try {
      violations = rule.fn(ctx) || [];
    } catch (err) {
      violations = [
        {
          rule: rule.id,
          file: '(rule crashed)',
          line: 0,
          message: String(err && err.message ? err.message : err),
          fixHint: 'Fix the rule implementation in scripts/ci-check.mjs.',
        },
      ];
    }
    report.push({ id: rule.id, group: rule.group, description: rule.description, violations });
  }
  return report;
}

function printSummary(report) {
  const total = report.length;
  const failed = report.filter((r) => r.violations.length > 0);
  const groupStats = {};
  for (const r of report) {
    groupStats[r.group] = groupStats[r.group] || { pass: 0, fail: 0 };
    if (r.violations.length === 0) groupStats[r.group].pass++;
    else groupStats[r.group].fail++;
  }

  const colorReset = '\x1b[0m';
  const red = '\x1b[31m';
  const green = '\x1b[32m';
  const yellow = '\x1b[33m';
  const dim = '\x1b[2m';

  console.log('');
  console.log(`${dim}─────────── GENPANO Harness L1 ───────────${colorReset}`);
  console.log(`Total rules: ${total}    Failed: ${failed.length}`);
  for (const [g, s] of Object.entries(groupStats).sort()) {
    console.log(`  Group ${g}: ${green}${s.pass} pass${colorReset} · ${s.fail > 0 ? red : dim}${s.fail} fail${colorReset}`);
  }
  console.log('');

  if (failed.length === 0) {
    console.log(`${green}✓ All harness rules pass.${colorReset}`);
    return 0;
  }

  for (const r of failed) {
    console.log(`${red}✗ ${r.id}${colorReset} [${r.group}] ${r.description}`);
    for (const v of r.violations.slice(0, 10)) {
      const loc = v.line > 0 ? `${v.file}:${v.line}` : v.file;
      console.log(`    ${yellow}${loc}${colorReset}`);
      console.log(`      ${v.message}`);
      if (v.fixHint) console.log(`      ${dim}hint: ${v.fixHint}${colorReset}`);
      if (v.snippet) console.log(`      ${dim}> ${v.snippet}${colorReset}`);
    }
    if (r.violations.length > 10) {
      console.log(`    ${dim}… and ${r.violations.length - 10} more violations${colorReset}`);
    }
    console.log('');
  }
  return 1;
}

/* ---------------- Entrypoint (CLI only when invoked directly) ---------------- */

function isMain() {
  if (!process.argv[1]) return false;
  try {
    const entry = pathToFileURL(process.argv[1]).href;
    return import.meta.url === entry;
  } catch {
    return false;
  }
}

if (isMain()) {
  const report = runAll({ includeFixtures: FLAG_INCLUDE_FIXTURES, onlyRuleId: ruleFilter });
  if (FLAG_JSON) {
    const exitCode = report.some((r) => r.violations.length > 0) ? 1 : 0;
    process.stdout.write(JSON.stringify({ exitCode, report }, null, 2) + '\n');
    process.exit(exitCode);
  } else {
    const exitCode = printSummary(report);
    process.exit(exitCode);
  }
}

// Exported for selftest runner
export { rules, runAll };
