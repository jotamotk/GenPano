# CI_BASELINE_ZERO.md — Session 0-rev Zero Baseline

> **Snapshot date**: 2026-04-21
> **Commit context**: post Session 0-rev scaffold (harness + fixtures + CI + Prisma + generated types)
> **Status**: **red by design** — baseline captures real frontend code that owning sessions (T6' / auth / T-topic) will fix. Harness itself is green (self-test 5/5); data contracts partially red against mock.

Zero baseline is the pre-session reference point. Before Session 1 starts, every violation listed here must be owned by a downstream session prompt. If a new violation appears in a later PR and it is **not** listed here, it is a regression, not a baseline issue.

---

## 1. L1 Harness · `scripts/ci-check.mjs`

**Rules registered**: 40 (A=6, B=7, C=16, D=7, E=4)
**Pass**: 30 rules · **Fail**: 10 rules · **Total violations**: 77 lines across those 10 rules

### Group-level counts

| Group | Scope | Pass | Fail |
|-------|------|------|------|
| A | i18n / 文案边界 | 2 | 4 |
| B | 图表契约 C1-C7 | 6 | 1 |
| C | V2 分析页契约 C9-C15 | 12 | 4 |
| D | 产品决策 / auth / 301 / MCP | 6 | 1 |
| E | Citation + KG | 4 | 0 |

### Failing rules and their fix owners

| Rule | Description | Sample file (first hit) | Fix owner session |
|------|------|------|------|
| **A1** | i18n-cjk-leak · JSX text 禁未经 `t()` 的 CJK | `frontend/src/components/charts/BrandTopicHeatmap.jsx:21` (JSDoc) + 34 more | T6' Wave-5 (清理 JSDoc / 注释内的 CJK 在 Harness 语义下，迁移至 i18n) |
| **A3** | `formatBrand` 唯一入口 | (pages 引用 `brand.name` 直读) | T6' Wave-5 |
| **A5** | 开发者约束措辞不进 i18n 字典 | (`messages/*.json` 早期遗留) | T6' Wave-5 |
| **A6** | interpolation `t(key, {values})` API 强制 | (`t(key, 'fallback')` 二路歧义) | T6' Wave-5 |
| **B1** | Sparkline default 必须 `'100%'` 字符串 | `frontend/src/components/charts/MiniSparkline.jsx:5` | T6' Wave-5 (C1 回归) |
| **C10-1** | 6 分析页必须 mount FilterBar | `pages/brand/BrandTopicsPage.jsx` 缺失 | T2' (页面迁移) |
| **C14-1** | h1/h2 禁 text-2xl+ (密度契约) | `pages/brand/BrandCitationsPage.jsx:58`、`BrandSentimentPage.jsx:127` | T6' Wave-5 (密度契约批量下压) |
| **C14-2** | 分析页 Card 禁 `p-[4-9]` | `BrandCitationsPage.jsx` × 8 / `BrandSentimentPage.jsx` × 2 + 5 more | T6' Wave-5 |
| **C14-3** | 根 div 禁 `space-y-[4-9]` | `BrandCitationsPage.jsx:53`、`BrandSentimentPage.jsx:121` | T6' Wave-5 |
| **D1** | Auth gate · `/brand /industry /reports` 必须 `RequireAuth` | `frontend/src/App.jsx` (整棵树未挂 RouteGuard) | Session 1 (Auth) |

**关键约束**: 上述 10 条均命中**真实代码**，不来自 `__ci_fixtures__/` 的 self-seeded violations。Frank 的 Session 0-rev 指令要求 "不得修 T6' 作业范围"，因此保持红色是正确状态。

---

## 2. L1 Harness Self-Test · `scripts/ci-harness-selftest.mjs`

```
✓ A1     caught 1 violation(s) in A1_cjk_leak
✓ B1     caught 1 violation(s) in B1_sparkline_literal
✓ C11-1  caught 2 violation(s) in C11_mentionrate_over1
✓ C14-1  caught 3 violation(s) in C14_h1_text3xl
✓ D4     caught 1 violation(s) in D4_missing_301

● selftest: PASS  (5 / 5 fixture expectations met)
```

**什么通过了 self-test 代表什么**: 这 5 条 grep 规则**至少能抓到自己种的 fixture**。Harness 不是纸面规则——当有人改 regex 导致它变瞎，selftest 会立刻失败。

**为什么只覆盖 5 条而不是 40 条**: Session 0-rev 仅交付 5 个 canonical fixtures (A/B/C/D/E 5 个 pillar 各 1 条)。剩余 35 条依赖**真实代码自然触发** (例如 D1 由 `App.jsx` 证明、C14 由 BrandCitationsPage 证明)。未来新增 harness 规则必须**同时**新增 fixture + 登记进 `EXPECTED_POSITIVES` 数组 (`ci-harness-selftest.mjs:42-48`)，否则规则无证可查。

---

## 3. L1 Data Contracts · `scripts/check-data-contracts.mjs`

7 条运行时断言 (grep 管不了关系型约束)。当前 **5 pass / 2 fail**。

| Assertion | Status | Notes / Fix owner |
|-----|-----|-----|
| DC1 · SOV "其他" ≤ 任一真实品牌片 (C3) | ✗ FAIL · `其他=7 > 资生堂=5` | T6' Wave-5 (mock.js SOV_DATA 调整) |
| DC2 · `BRANDS.ranking == rank-by-panoScore` (C7) | ✓ PASS | — |
| DC3 · `PRODUCTS.ranking == rank-by-panoScore` (C7) | ✓ PASS | — |
| DC4 · `mentionRate ∈ [0, 1]` BRANDS/PRODUCTS/TOPICS (C11) | ✓ PASS | — |
| DC5 · BCG 4 quadrants 每象限 ≥1 product | ✗ FAIL · `question=0, cash=0` | T6' Wave-5 (产品象限补齐) |
| DC6 · AUTHORITY_RADAR_DATA 5 tiers (0..4) | ✓ PASS | — |
| DC7 · `Project.primaryBrandId ∉ competitorBrandIds` | ✓ PASS | — |

DC1 / DC5 是 mock 数据层的结构性偏差，不是规则 bug，不归 Session 0 修。

---

## 4. L3 Coverage Gap · `scripts/coverage-gap-scan.mjs --write`

| Metric | Count | Note |
|-----|-----|-----|
| OpenAPI operations declared (`docs/openapi.yaml`) | 35 | 单一契约源 |
| Backend routes discovered (`backend/src/app/**`) | 0 | 零号基线，Session 1 开工前正确状态 |
| L3 contract test files | 0 | 同上 |
| **declaredNotImplemented** (spec-first gap) | **35** | 全部 — 100% baseline gap |
| **implementedNotDeclared** (undeclared route) | 0 | 不应出现，出现即 PR block |

Artifact: `docs/COVERAGE_GAP.json` (uploaded as CI artifact, non-blocking at zero baseline).

---

## 5. L2 / L4 — Session 0 未激活

| Layer | Scope | Zero-baseline behavior |
|-----|-----|-----|
| **L2** Vitest unit | `frontend/tests/unit/**` | 0 tests yet — suite passes trivially. OpenAPI type-gen drift check will block if `api-types.d.ts` falls out of sync (harness 校验 Job 2 step 5) |
| **L3** Contract / HAR | `frontend/tests/contract/**` | 0 tests yet (`gen-api-tests.ts` 已交付，但 Session 1 才开始填充)。CI 以 `continue-on-error` 运行 |
| **L4** Playwright E2E + Visual | `frontend/tests/e2e/**` | 0 tests yet. Playwright browsers 已 install，`npm run build` 可能尚未绿 (frontend 缺 Next.js — 本仓是 Vite) — Job 4 全部 `continue-on-error` |

Sessions 4-5 填充 L2/L3/L4 覆盖。

---

## 6. Known skips (intentional, not regression)

- **L4 e2e-visual** job 整段 `continue-on-error` — 无 baseline screenshot，Session 4 起才产生第一批
- **L3 contract** vitest — 文件为 `it.todo(...)`，干净通过但不验证任何约束
- **backend/** 尚无 Next.js — `backend/package.json` 已声明 `next@14.2.15` 但不安装 node_modules (Frank 要求 Session 0 不 install Next)
- **prisma migrate** 未运行 — `prisma format` + `prisma validate` 已绿 (37 models)，真正的 DB migrate 归 Session 2
- **`scripts/gen-api-tests.ts --dry-run`** 报告 drift 属于正常 (0 contract tests 对 35 ops)，Session 4 才开始消化

---

## 7. Artifact manifest (Session 0-rev 交付物)

### Harness & scripts (root `scripts/`)
- `ci-check.mjs` — 40 rules, 5 groups, ES module library + CLI dual-use (guard via `isMain()` + `pathToFileURL` parity)
- `check-data-contracts.mjs` — 7 relational assertions against `frontend/src/data/mock.js`
- `ci-harness-selftest.mjs` — 5 fixture expectations verifying harness regex liveness
- `coverage-gap-scan.mjs` — OpenAPI ↔ backend route gap report, always exit 0
- `gen-api-tests.ts` — L3 skeleton generator (`--dry-run` returns 1 on drift)

### Fixtures (`frontend/src/__ci_fixtures__/`)
- `A1_cjk_leak.cifixture.jsx`
- `B1_sparkline_literal.cifixture.jsx`
- `C11_mentionrate_over1.cifixture.js`
- `C14_h1_text3xl.cifixture.jsx`
- `D4_missing_301.cifixture.jsx`
- `README.md` (fixture policy)

### CI (`.github/workflows/ci.yml`)
- Job 1 `harness` — L1 harness + contracts + selftest + coverage gap (≤5 min)
- Job 2 `unit` — L2 Vitest + OpenAPI type-gen drift check (≤6 min)
- Job 3 `integration` — L3 contract vitest (≤6 min, `continue-on-error`)
- Job 4 `e2e-visual` — L4 Playwright install + build + best-effort (≤10 min, `continue-on-error`)

### Backend scaffold (`backend/`)
- `package.json` — Next.js 14.2.15, Prisma 5.22, Zod, Resend, Sentry, mixpanel, tldts, openapi-typescript
- `.env.example` — DATABASE_URL, DIRECT_URL, VOLC_API_KEY, RESEND_API_KEY, MIXPANEL_TOKEN, SENTRY_DSN, COST_ALERT_WEBHOOK, REDIS_URL, AUTH_JWT_SECRET, MCP_TOKEN_HMAC_SECRET, App URLs
- `prisma/schema.prisma` — **37 models** covering DATA_MODEL §1-§6 + Citation Tier (决策 #19) + DraftProject (决策 #21.D) + McpApiToken (决策 #21.E). `prisma validate` ✓
- `src/lib/api-types.ts` — generated from `docs/openapi.yaml` (1715 lines)

### Generated types
- `frontend/src/lib/api-types.d.ts` (1715 lines)
- `backend/src/lib/api-types.ts` (1715 lines)

---

## 8. How to reproduce this baseline

```bash
# From repo root (working directory resolved via scripts/ relative paths)
node scripts/ci-check.mjs               # exit 1, 10 failing rules, 77 violations
node scripts/check-data-contracts.mjs   # exit 1, 2 failing assertions
node scripts/ci-harness-selftest.mjs    # exit 0, 5/5 pass
node scripts/coverage-gap-scan.mjs --write  # exit 0, writes COVERAGE_GAP.json

# From frontend/
npm run gen:api-types                   # regenerates api-types.d.ts
npm run test:unit -- --run              # 0 tests, passes trivially

# From backend/ (DATABASE_URL + DIRECT_URL required; any dummy string works for format/validate)
DATABASE_URL='postgresql://u:p@localhost:5432/d' \
DIRECT_URL='postgresql://u:p@localhost:5432/d' \
  npx prisma validate                   # "The schema is valid 🚀"
npx prisma format                       # formats in place
```

---

## 9. What comes next (owning-session hand-off)

| Downstream session | Consumes this baseline by | Gate |
|------|------|------|
| **Session 1 · Auth** | Adds `<RequireAuth>` wrapping → **D1 flips to PASS** | must not break 30 other harness rules |
| **Session 2 · DB init** | Runs `prisma migrate dev` against schema.prisma, seeds `kg_industries` through `profile_groups` | introduces no drift on `api-types.d.ts` |
| **Session T2' / T3' · Page IA migration** | Creates `pages/brand/BrandTopicsPage.jsx` → **C10-1 flips to PASS** | keeps FilterBar import contract |
| **Session T6' Wave-5 · UI polish** | Fixes A1 / A3 / A5 / A6 / B1 / C14-1 / C14-2 / C14-3 / DC1 / DC5 | after this, harness should report **0 failing rules** against real code; only `__ci_fixtures__/` self-seeded violations remain (always red by design) |
| **Session 4 · L3/L4 fill-in** | `gen-api-tests.ts` 消化 35 OpenAPI ops; Playwright baseline screenshots 录入 | contract test files = OpenAPI ops count |

**Invariant 声明**: 本基线文件是 Frank "zero Frank intervention" (决策 #18) 的第一块锚点。任何让 baseline 倒退（红色条目变多或选项变少）的 PR 必须在描述里显式说明为何合理，否则 reviewer 打回。
