#!/usr/bin/env node
/**
 * GENPANO · Data Contract Runtime Assertions (check-data-contracts.mjs)
 *
 * Decision #21.B — 7 runtime assertions that grep can't express.
 * Reads `frontend/src/data/mock.js` via dynamic import and validates
 * relational invariants. Exit 1 on any failure; 0 if all green.
 *
 * Bloodline: docs/DESIGN_TOKENS.md C3/C7.
 *
 * Assertions:
 *   DC1 — SOV_DATA "其他" (Others) must not be greater than any real brand slice
 *   DC2 — BRANDS.ranking must equal index+1 when sorted by panoScore DESC
 *   DC3 — PRODUCTS.ranking must equal index+1 when sorted by panoScore DESC
 *   DC4 — Any mentionRate literal across BRANDS / PRODUCTS / TOPICS must be in [0, 1]
 *   DC5 — PRODUCTS BCG matrix must have ≥1 product in each of 4 quadrants
 *   DC6 — AUTHORITY_RADAR_DATA must have exactly 5 tiers (0..4) with me/industryMedian/topCompetitor numeric
 *   DC7 — Every Project.primaryBrandId must NOT appear in its competitorBrandIds (closure disjoint)
 */

import { pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const PROJECT_ROOT = join(__filename, '..', '..');
const MOCK_PATH = join(PROJECT_ROOT, 'frontend', 'src', 'data', 'mock.js');

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

const FLAG_JSON = process.argv.includes('--json');

async function loadMock() {
  if (!existsSync(MOCK_PATH)) {
    console.error(`${RED}[data-contracts] mock.js not found at ${MOCK_PATH}${RESET}`);
    process.exit(2);
  }
  try {
    const mod = await import(pathToFileURL(MOCK_PATH).href);
    return mod;
  } catch (err) {
    console.error(`${RED}[data-contracts] failed to import mock.js:${RESET}`, err.message);
    process.exit(2);
  }
}

/* ---------------- Assertions ---------------- */

function dc1_sovOthersNotDominant(mock) {
  const { SOV_DATA } = mock;
  if (!Array.isArray(SOV_DATA) || SOV_DATA.length === 0) {
    return [{ message: 'SOV_DATA missing or empty' }];
  }
  const othersPatterns = /^(其他|其它|others?)$/i;
  const others = SOV_DATA.filter((d) => othersPatterns.test(String(d.name)) || othersPatterns.test(String(d.nameEn || '')));
  if (others.length === 0) return [];
  const maxOthers = Math.max(...others.map((d) => Number(d.value) || 0));
  const reals = SOV_DATA.filter((d) => !othersPatterns.test(String(d.name)) && !othersPatterns.test(String(d.nameEn || '')));
  const violations = reals
    .filter((d) => Number(d.value) < maxOthers)
    .map((d) => ({
      message: `SOV "其他"=${maxOthers} > 真实品牌 "${d.name}"=${d.value}. Others 不得超过任一真实片 (C3)`,
    }));
  return violations;
}

function dc2_brandsRankingMatchesPano(mock) {
  const { BRANDS } = mock;
  if (!Array.isArray(BRANDS) || BRANDS.length === 0) return [{ message: 'BRANDS missing or empty' }];
  const byIndustry = new Map();
  for (const b of BRANDS) {
    const k = b.industryId || '__no_industry__';
    if (!byIndustry.has(k)) byIndustry.set(k, []);
    byIndustry.get(k).push(b);
  }
  const violations = [];
  for (const [industryId, list] of byIndustry.entries()) {
    const sorted = [...list].sort((a, b) => Number(b.panoScore ?? 0) - Number(a.panoScore ?? 0));
    sorted.forEach((brand, idx) => {
      const expected = idx + 1;
      if (Number(brand.ranking) !== expected) {
        violations.push({
          message: `BRANDS[${brand.id}] industryId=${industryId} ranking=${brand.ranking}, expected ${expected} (panoScore=${brand.panoScore}) (C7)`,
        });
      }
    });
  }
  return violations;
}

function dc3_productsRankingMatchesPano(mock) {
  const { PRODUCTS } = mock;
  if (!Array.isArray(PRODUCTS) || PRODUCTS.length === 0) return [{ message: 'PRODUCTS missing or empty' }];
  // PRODUCTS mock uses a single global ranking pool (no industryId on products).
  const ranked = PRODUCTS.filter((p) => typeof p.ranking !== 'undefined' && p.ranking !== null);
  if (ranked.length === 0) return [];
  const sorted = [...ranked].sort((a, b) => Number(b.panoScore ?? 0) - Number(a.panoScore ?? 0));
  const violations = [];
  sorted.forEach((product, idx) => {
    const expected = idx + 1;
    if (Number(product.ranking) !== expected) {
      violations.push({
        message: `PRODUCTS[${product.id}] ranking=${product.ranking}, expected ${expected} (panoScore=${product.panoScore}) (C7)`,
      });
    }
  });
  return violations;
}

function dc4_mentionRateInRange(mock) {
  const { BRANDS = [], PRODUCTS = [], TOPICS = [] } = mock;
  const violations = [];
  const checkList = (list, labelPrefix) => {
    for (const item of list) {
      if (item == null || typeof item !== 'object') continue;
      const v = item.mentionRate;
      if (typeof v !== 'number') continue;
      if (!Number.isFinite(v) || v < 0 || v > 1) {
        violations.push({
          message: `${labelPrefix}[${item.id || item.name || '?'}].mentionRate=${v}, expected literal in [0, 1] (C11)`,
        });
      }
    }
  };
  checkList(BRANDS, 'BRANDS');
  checkList(PRODUCTS, 'PRODUCTS');
  checkList(TOPICS, 'TOPICS');
  return violations;
}

function dc5_bcgQuadrantCoverage(mock) {
  const { PRODUCTS = [] } = mock;
  if (PRODUCTS.length === 0) return [{ message: 'PRODUCTS missing or empty' }];

  // Quadrant heuristic: BCG × growth (y-axis) × share (x-axis), both from panoScore + mentionRate.
  // Star/Question/Cash/Dog via median split across PRODUCTS with both numerics.
  const eligible = PRODUCTS.filter(
    (p) => typeof p.panoScore === 'number' && typeof p.mentionRate === 'number',
  );
  if (eligible.length < 4) {
    return [{ message: `PRODUCTS with panoScore+mentionRate < 4 (=${eligible.length}); cannot form BCG grid` }];
  }

  const median = (arr) => {
    const sorted = [...arr].sort((a, b) => a - b);
    const m = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
  };
  const medShare = median(eligible.map((p) => p.panoScore));
  const medGrowth = median(eligible.map((p) => p.mentionRate));

  const quadrantCounts = { star: 0, question: 0, cash: 0, dog: 0 };
  for (const p of eligible) {
    const highShare = p.panoScore >= medShare;
    const highGrowth = p.mentionRate >= medGrowth;
    if (highShare && highGrowth) quadrantCounts.star++;
    else if (!highShare && highGrowth) quadrantCounts.question++;
    else if (highShare && !highGrowth) quadrantCounts.cash++;
    else quadrantCounts.dog++;
  }
  const missing = Object.entries(quadrantCounts)
    .filter(([, c]) => c === 0)
    .map(([q]) => q);
  if (missing.length === 0) return [];
  return [
    {
      message: `BCG matrix missing ≥1 product in quadrant(s): ${missing.join(', ')}. Counts=${JSON.stringify(quadrantCounts)} (C7/BCG)`,
    },
  ];
}

function dc6_authorityRadarCoverage(mock) {
  const { AUTHORITY_RADAR_DATA } = mock;
  if (!Array.isArray(AUTHORITY_RADAR_DATA)) return [{ message: 'AUTHORITY_RADAR_DATA missing' }];
  if (AUTHORITY_RADAR_DATA.length !== 5) {
    return [{ message: `AUTHORITY_RADAR_DATA has ${AUTHORITY_RADAR_DATA.length} tiers, expected 5 (Tier 0..4)` }];
  }
  const violations = [];
  const tierPattern = /Tier\s*([0-4])/;
  const seen = new Set();
  for (const row of AUTHORITY_RADAR_DATA) {
    const m = typeof row.tier === 'string' ? row.tier.match(tierPattern) : null;
    if (!m) {
      violations.push({ message: `AUTHORITY_RADAR_DATA row.tier="${row.tier}" does not contain Tier 0-4 token` });
      continue;
    }
    seen.add(m[1]);
    for (const key of ['me', 'industryMedian', 'topCompetitor']) {
      if (typeof row[key] !== 'number' || !Number.isFinite(row[key])) {
        violations.push({ message: `AUTHORITY_RADAR_DATA tier=${row.tier} missing numeric .${key}` });
      }
    }
  }
  const expected = new Set(['0', '1', '2', '3', '4']);
  for (const t of expected) {
    if (!seen.has(t)) violations.push({ message: `AUTHORITY_RADAR_DATA missing Tier ${t}` });
  }
  return violations;
}

function dc7_projectBrandDisjoint(mock) {
  const { PROJECTS = [] } = mock;
  const violations = [];
  for (const p of PROJECTS) {
    const pid = p.id || p.name || '?';
    const primary = p.primaryBrandId;
    const competitors = Array.isArray(p.competitorBrandIds) ? p.competitorBrandIds : [];
    if (!primary) {
      violations.push({ message: `PROJECT[${pid}] missing primaryBrandId` });
      continue;
    }
    if (competitors.includes(primary)) {
      violations.push({
        message: `PROJECT[${pid}].primaryBrandId=${primary} also appears in competitorBrandIds (must be disjoint)`,
      });
    }
  }
  return violations;
}

/* ---------------- Runner ---------------- */

const ASSERTIONS = [
  { id: 'DC1', description: 'SOV "其他" ≤ every real brand slice (C3)', fn: dc1_sovOthersNotDominant },
  { id: 'DC2', description: 'BRANDS.ranking = rank-by-panoScore DESC (C7)', fn: dc2_brandsRankingMatchesPano },
  { id: 'DC3', description: 'PRODUCTS.ranking = rank-by-panoScore DESC (C7)', fn: dc3_productsRankingMatchesPano },
  { id: 'DC4', description: 'mentionRate literal ∈ [0, 1] across BRANDS/PRODUCTS/TOPICS (C11)', fn: dc4_mentionRateInRange },
  { id: 'DC5', description: 'BCG 4 quadrants each ≥1 product', fn: dc5_bcgQuadrantCoverage },
  { id: 'DC6', description: 'AUTHORITY_RADAR_DATA has 5 tiers (0..4) with full numerics', fn: dc6_authorityRadarCoverage },
  { id: 'DC7', description: 'Project.primaryBrandId ∉ competitorBrandIds', fn: dc7_projectBrandDisjoint },
];

async function main() {
  const mock = await loadMock();
  const results = [];
  for (const a of ASSERTIONS) {
    let violations = [];
    try {
      violations = a.fn(mock) || [];
    } catch (err) {
      violations = [{ message: `assertion threw: ${err.message}` }];
    }
    results.push({ id: a.id, description: a.description, violations });
  }

  const totalViolations = results.reduce((sum, r) => sum + r.violations.length, 0);

  if (FLAG_JSON) {
    console.log(JSON.stringify({ ok: totalViolations === 0, results }, null, 2));
    process.exit(totalViolations === 0 ? 0 : 1);
  }

  console.log(`${DIM}──────── GENPANO · Data Contract Runtime (7 assertions) ────────${RESET}`);
  for (const r of results) {
    if (r.violations.length === 0) {
      console.log(`${GREEN}✓${RESET} ${r.id}  ${DIM}${r.description}${RESET}`);
    } else {
      console.log(`${RED}✗ ${r.id}${RESET}  ${r.description}`);
      for (const v of r.violations) {
        console.log(`    ${RED}· ${v.message}${RESET}`);
      }
    }
  }
  console.log(`${DIM}─────────────────────────────────────────────────────────────${RESET}`);
  if (totalViolations === 0) {
    console.log(`${GREEN}● data-contracts: PASS${RESET}  (7 / 7 assertions green)`);
    process.exit(0);
  }
  console.log(`${RED}● data-contracts: FAIL${RESET}  ${totalViolations} violation(s) across ${results.filter((r) => r.violations.length).length} / 7 assertions`);
  console.log(`${YELLOW}Fix hints: see docs/DESIGN_TOKENS.md C3/C7/C11${RESET}`);
  process.exit(1);
}

main();
