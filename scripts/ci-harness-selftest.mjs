#!/usr/bin/env node
/**
 * GENPANO · Harness Self-Test (ci-harness-selftest.mjs)
 *
 * Decision #21.C — harness is not paper. Every grep rule must prove it can
 * catch a real violation, or the rule itself is broken.
 *
 * Approach:
 *   1. Import { rules, runAll } from ci-check.mjs.
 *   2. Run with includeFixtures=true against the entire codebase, which
 *      includes `frontend/src/__ci_fixtures__/` (self-seeded violations).
 *   3. For every rule id that has a registered fixture mapping, assert that
 *      at least one of its violations points to the fixture dir.
 *   4. Report missing-proof rules (no fixture or fixture didn't trigger).
 *
 * Exit 0 if every expected-positive rule produced a fixture hit; else exit 1.
 *
 * Fixture-to-rule map: Session 0-rev seeded 5 canonical fixtures (A/B/C/D/E),
 * Session A0 added D8/D9/D10, Session 1 added F1/F2/F3, Session 2 adds
 * G1/G2/G3/G4. Rules without a mapping are not asserted here — their
 * correctness is proven by real code in the repo eventually catching a real
 * violation. Selftest is a dead-canary check, not 100% coverage.
 */

import { runAll, rules } from './ci-check.mjs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const PROJECT_ROOT = join(__filename, '..', '..');
const FIXTURES_REL = ['frontend', 'src', '__ci_fixtures__'].join('/');

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

/**
 * Each entry: { ruleId, fixtureFileMarker } — marker is a substring that must
 * appear in the violation's `file` path. All 5 Session 0-rev fixtures below.
 */
const EXPECTED_POSITIVES = [
  { ruleId: 'A1', fixtureMarker: 'A1_cjk_leak', description: 'CJK 中文直接出现在 JSX 文本节点' },
  { ruleId: 'B1', fixtureMarker: 'B1_sparkline_literal', description: 'MiniSparkline width/height 数字 literal' },
  { ruleId: 'C11-1', fixtureMarker: 'C11_mentionrate_over1', description: 'mentionRate literal ≥ 1' },
  { ruleId: 'C14-1', fixtureMarker: 'C14_h1_text3xl', description: '<h1 className="text-3xl"> 违反密度契约' },
  { ruleId: 'D4', fixtureMarker: 'D4_missing_301', description: 'App.jsx 缺 11 条 legacy redirects 之一' },
  { ruleId: 'D8', fixtureMarker: 'D8_hardcoded_jwt_secret', description: 'ADMIN_JWT_SECRET 字面量赋值 (非 process.env)' },
  { ruleId: 'D9', fixtureMarker: 'D9_bcrypt_cost_8', description: 'bcrypt.hash cost=8 (低于 12)' },
  { ruleId: 'D10', fixtureMarker: 'D10_cookie_samesite_lax', description: 'Admin cookie sameSite: "lax"' },
  { ruleId: 'F1', fixtureMarker: 'F1_playwright_bare_import', description: '适配器直接 import playwright chromium' },
  { ruleId: 'F2', fixtureMarker: 'F2_har_bearer_leak', description: 'HAR fixture 含未脱敏 Bearer / Set-Cookie / refresh_token' },
  { ruleId: 'F3', fixtureMarker: 'F3_inline_prompt', description: 'Adapter 测试内联 prompt 字面量' },
  { ruleId: 'G1', fixtureMarker: 'G1_matrix_row_count_wrong', description: 'EXPECTED_EXPLICIT_ROW_COUNT 偏离 23' },
  { ruleId: 'G2', fixtureMarker: 'G2_purity_guard_missing', description: 'topic-planner 缺 validateCategoryTopicPurity 调用' },
  { ruleId: 'G3', fixtureMarker: 'G3_persona_column', description: 'query_executions 迁移加了 persona 列' },
  { ruleId: 'G4', fixtureMarker: 'G4_hardcoded_engines', description: 'Planner 硬编码 3 家引擎数组字面量' },
];

async function main() {
  const allRuleIds = rules.map((r) => r.id);
  const results = runAll({ includeFixtures: true });

  const missingRules = [];
  const passedExpectations = [];
  const failedExpectations = [];

  for (const exp of EXPECTED_POSITIVES) {
    if (!allRuleIds.includes(exp.ruleId)) {
      missingRules.push(exp.ruleId);
      continue;
    }
    const rule = results.find((r) => r.id === exp.ruleId);
    const hits = (rule?.violations || []).filter((v) => String(v.file || '').includes(exp.fixtureMarker));
    if (hits.length >= 1) {
      passedExpectations.push({ ...exp, hitCount: hits.length });
    } else {
      failedExpectations.push({
        ...exp,
        totalViolations: rule?.violations?.length ?? 0,
        sampleFiles: (rule?.violations || []).slice(0, 3).map((v) => v.file),
      });
    }
  }

  console.log(`${DIM}──────── GENPANO · Harness Self-Test ────────${RESET}`);
  console.log(`${DIM}Rules registered: ${rules.length}${RESET}`);
  console.log(`${DIM}Fixture expectations: ${EXPECTED_POSITIVES.length}${RESET}`);
  console.log(`${DIM}Fixture dir: ${FIXTURES_REL}${RESET}`);
  console.log('');

  for (const p of passedExpectations) {
    console.log(`${GREEN}✓${RESET} ${p.ruleId.padEnd(8)} caught ${p.hitCount} violation(s) in ${p.fixtureMarker}  ${DIM}${p.description}${RESET}`);
  }
  for (const f of failedExpectations) {
    console.log(`${RED}✗ ${f.ruleId.padEnd(8)}${RESET} did NOT catch ${f.fixtureMarker}  ${DIM}${f.description}${RESET}`);
    console.log(`    ${DIM}rule ran, total violations=${f.totalViolations}; sample files=${JSON.stringify(f.sampleFiles)}${RESET}`);
    console.log(`    ${YELLOW}→ either the fixture is missing/empty, or the rule regex is broken${RESET}`);
  }
  for (const rid of missingRules) {
    console.log(`${RED}✗ expected rule ${rid} is not registered in ci-check.mjs${RESET}`);
  }

  console.log('');
  const ok = failedExpectations.length === 0 && missingRules.length === 0;
  if (ok) {
    console.log(`${GREEN}● selftest: PASS${RESET}  (${passedExpectations.length} / ${EXPECTED_POSITIVES.length} fixture expectations met)`);
    process.exit(0);
  }
  console.log(
    `${RED}● selftest: FAIL${RESET}  ${failedExpectations.length + missingRules.length} expectation(s) unmet`,
  );
  console.log(`${YELLOW}Hint: fixtures live at ${FIXTURES_REL}/, each file must deliberately violate the rule it targets.${RESET}`);
  process.exit(1);
}

main().catch((err) => {
  console.error(`${RED}selftest crashed:${RESET}`, err);
  process.exit(2);
});
