# Session 4b'.4 Prompt · Group I Aggregate + Vitest 80% + Playwright Smoke + Vercel Production + MVP COMPLETE

**版本**: 1.0 · 创建日期 2026-04-26
**拆分自**: `docs/SESSION_4B_PRIME_PROMPT.md` (consolidated 4b' 的第 4/4 段, 终章)
**上游链**: 0' → 4a' → 4b'.1 → 4b'.2 → 4b'.3 → **本 Session (4b'.4)** → 🎯 **MVP COMPLETE**
**下游 Session**: 无 (MVP MVP-Phase 终点; v1.1 / Phase 2 由独立计划承接)

---

## §0 · Pre-Flight Grep Contract (开工前 30min 内执行, 全部命中才能动代码)

```bash
# F1 · IA v2.0 总路由集 (Brand 9 + Industry 4 = 13 路径全部存在于代码)
rg -n "path: '/(brand|industry)/" frontend/src/router/routes.tsx | wc -l
# 期望: ≥ 13 (Brand Mode 9 sub-views + Industry Mode 4 sub-views, 4b'.1/4b'.2/4b'.3 累计交付)

# F4 · 上游 GREEN gate (Sessions 4b'.3 + 0' 必须 PASS)
rg -n "Session 4b'.3.*GREEN|Session 0'.*GREEN" docs/SESSIONS_PYTHON.md | head -5
# 期望: 双方 GREEN; 任一为 ❌ 立即 STOP Type A4

# F9 · Playwright spec 目录 (4b'.1 已交付 spec dir 框架)
ls frontend/playwright/specs/*.spec.ts 2>/dev/null | wc -l
# 期望: ≥ 1 (4b'.1 框架就位)

# F10 · 视觉回归 baseline (toHaveScreenshot 是否已生成)
ls frontend/playwright/specs/*.spec.ts-snapshots/*.png 2>/dev/null | wc -l
# 期望: ≥ 0 (本 Session 首次跑会生成; 已存在的 baseline 走 diff 对照)

# F11 · Vercel 部署配置 (0' Session 交付)
test -f vercel.json && cat vercel.json | jq '.framework' 2>/dev/null
# 期望: "vite" (0' Session 已写入 framework=vite)

# F12 · CLAUDE.md 最近 3 条决策 freshness check (规则 11)
rg -n "^[0-9]+\. \*\*" CLAUDE.md | tail -3
# 期望: 最新 3 条决策, 任何提及 Vercel/Playwright/MVP-COMPLETE 必须读全文

# F13 · TEST_STRATEGY P0/P1/P2 优先级清单 (决策 #21.D)
rg -n "^P[012]-[0-9]+|priority.*P[012]" docs/TEST_STRATEGY.md | head -25
# 期望: ≥ 19 (P0 10 项 + P1 5 项 + P2 4 项 = 19 行优先级条目)

# F14 · 11 Legacy 301 客户端 + 服务端双层确认 (4b'.3 已交付)
rg -n "Navigate replace" frontend/src/router/legacyRedirects.tsx | wc -l
test -f vercel.json && cat vercel.json | jq '.redirects | length' 2>/dev/null
# 期望: 双方 ≥ 11 (客户端 React Router 11 条 + 服务端 vercel.json 11 条)
```

**STOP 触发对照表**:

| 命中条件 | STOP 类型 | 行动 |
| --- | --- | --- |
| F4 显示 4b'.3 / 0' 任一未 GREEN | Type A4 | 暂停, 回追前置 Session |
| F1 < 13 (IA v2.0 路由不齐) | Type B1 (truth source 漂移) | 回 4b'.1/4b'.2/4b'.3 各自 Phase Gate 复查 |
| F11 vercel.json 不存在 | Type A6 (基建缺失) | 回 0' 补 Vercel 基建, 不允许在 4b'.4 临时补 |
| F13 P0/P1/P2 列表不完整 | Type B7 | 回 TEST_STRATEGY §11 补全 |
| F14 任一层 < 11 | Type B1 | 11 条 Legacy 301 必须双层全覆盖, 否则 SEO + 直链双失效 |
| F12 显示有未读决策 | Type B7 | 读全文, 加入 §1 真相源索引再开工 |

---

## §1 · Truth Source Index (本 Session 引用 / 修改的所有真相源, 段号最小单元)

### Prerequisites (chain dependency, 全部 GREEN 才能开工)

| 前置 Session | GREEN 条件 | 本 Session 依赖点 | 验证命令 |
| --- | --- | --- | --- |
| **4b'.3** | Industry Mode 4 sub-views + KG G6 v5 8 坑点 + CSV 8 接入点 + 11 Legacy 301 dual-layer 全部交付, verify_4b3.sh 13 check 全绿, L3 Frank S10-S13 已确认 | 本 Session 在完整 IA v2.0 (Brand 9 + Industry 4) 上叠加聚合测试 + Playwright smoke + 生产部署 | `curl -s https://app.preview.genpano.dev/industry/knowledge-graph` 返回 200 + G6 canvas 渲染 |
| **0'** | CI/CD 基建 (GitHub Actions / Vercel project / DNS 配置 app.genpano.dev) 齐备, 自动 preview env per branch 工作 | Vercel 生产部署 + DNS 切换到 app.genpano.dev | Vercel CLI `vercel --prod` 在 0' Phase Gate 已 dry-run 通过 |

**STOP Type A4**: 上述任一前置 Session 未 GREEN, 本 Session 必须暂停 Phase Gate 任何活动, 回追前置 Session 的 Phase Gate 报告。
**STOP Type A6**: 0' 基建缺失 (vercel.json 不存在 / DNS 未配置 / GitHub Actions 工作流缺) — 本 Session 不可临时补基建, 必须回 0' 完成基建。

### 引用的真相源 (只读)

| 文档 / 锚点 | 引用内容 | 用途 |
| --- | --- | --- |
| `docs/PRD.md §4.6-IA-v2 全段` | IA v2.0 13 sub-views + 顶栏 pill toggle + 11 Legacy 301 + 5 KPI 不变 | Frank 全量 walkthrough 总章程 |
| `docs/PRD.md §4.11` | Mixpanel 埋点全表 (#1-#70+) — MVP 终验时事件全部触发 | Playwright smoke + Frank 手动确认 |
| `docs/TEST_STRATEGY.md §11` | P0 10 项 / P1 5 项 / P2 4 项 优先级清单, P0 必须 100% 测试覆盖 (L1-L4 任一层) | 聚合验证 + L3/L4 测试覆盖率审计 |
| `docs/TEST_STRATEGY.md §12` | fixture 命名 + F1-F3 harness (frontend self-seeded) | selftest 38/38 lock-in |
| `docs/TEST_STRATEGY.md v1.1 §13` | 38 规则血统表 (A1-A6 / B1-B7 / C9-C15 / D1-D10 / E1-E4 / F1-F4 + Group I 派生) | 终验 harness 完整性 audit |
| `docs/DESIGN_TOKENS.md C1-C15 全段` | 视觉契约 15 条 — Visual regression baseline 比对依据 | Playwright `toHaveScreenshot` |
| `CLAUDE.md` 决策 #2 / #18 / #20 / #21 / #25 | IA v2.0 / 测试 A++ / V2 分析页 / Review 修复闭环 / Prompt 公约 12 条 | 终验合规审计 |
| memory `feedback_genpano_session_commit_rule` | Session 结束即 commit + git tag + Phase Gate 报告 | MVP COMPLETE 收尾仪式 |
| memory `feedback_genpano_session_preview_env_2026_04_26` | 每 Session 必须 preview env 可点击产物 | L3 验证标准 |
| memory `feedback_production_deps` | 视觉回归只用 Playwright `toHaveScreenshot`, 禁第二家 (Percy/Chromatic) | 决策 #18 不变 |

### 修改 / 创建的真相源 (写)

| 文件 / 路径 | 变更类型 | 内容摘要 |
| --- | --- | --- |
| `frontend/playwright/specs/critical-path.spec.ts` | CREATE | 1 条关键路径 E2E: register → onboarding → /brand/overview → /brand/citations → CSV export download |
| `frontend/playwright/specs/visual-regression.spec.ts` | CREATE | toHaveScreenshot 覆盖 13 sub-views + 4 浏览器 width (375 / 768 / 1280 / 1920) |
| `frontend/playwright.config.ts` | UPDATE | reporters=[html, list] / retries=2 (CI) / browsers=[chromium, firefox, webkit] / fullParallel=true |
| `vercel.json` | UPDATE | 11 redirects (4b'.3 已写, 此处 lock-in) + headers (X-Frame-Options / CSP) + 区域=hkg1 (港 region 离豆包/DeepSeek 近) |
| `.github/workflows/ci.yml` | UPDATE | jobs: lint / typecheck / test (vitest --coverage) / build / playwright / deploy-preview / deploy-production (main only) |
| `scripts/verify_4b4.sh` | CREATE | 终验脚本: 跑 verify_4b1/4b2/4b3.sh 三条 + Vitest 全量 80% / Playwright smoke / Bundle size <2MB / Lighthouse a11y ≥90 / OpenAPI drift / harness selftest 38/38 |
| `RELEASE_NOTES_v1.0.md` | CREATE | MVP 1.0 发布说明: IA v2.0 13 sub-views / Citation 5 Tab / KG G6 v5 / CSV 8 export / 11 Legacy 301 / 38 harness / 测试 A++ |

**关键纪律**:

- **本 Session 不新增任何 Group I rules**: 38 harness selftest 在 4b'.2 锁定后, 4b'.3 / 4b'.4 不再加规则, 只验证持续生效
- **本 Session 不创建 ComingSoon 占位**: 13 sub-views 全部已实装, 任一仍是占位即 STOP Type B1
- **本 Session 不写新业务逻辑**: 仅做聚合测试 + Vercel 部署 + Frank L3 终验 + git tag 收尾
- **Playwright smoke 1 条 critical path 而非全量**: 决策 #18 PRD §11 P0 10 项不要求全部 E2E (L1-L4 任一层覆盖即可); 1 条 critical path 走最高商业价值流 (注册 → 首次价值 → 转化关键 CSV)

---

## §2 · MVP Scope-Cut Declaration (规则 10)

### ✅ 本 Session 做 (Y42-Y45 验收任务)

- **Y42 · Group I aggregate verification**: I1-I6 全部规则 active, harness selftest 38/38 GREEN, Group I 不再扩
- **Y43 · Vitest 全量聚合 80% coverage**: branches / lines / functions / statements 四线 80% 阈值, 跨 4b'.1/4b'.2/4b'.3 累计代码全部覆盖
- **Y44 · Playwright smoke 1 条 critical path**: register → onboarding step1-4 → /brand/overview KPI 5 → /brand/citations Tab 5 → CSV export download with BOM 验证 → 通过即 GREEN
- **Y45 · Visual regression baseline 13 sub-views × 4 width**: toHaveScreenshot 跑 13 路由 × {mobile-375 / tablet-768 / desktop-1280 / wide-1920} = 52 screenshots, 首次跑生成 baseline, 已存在 baseline 走 diff (>5% 像素差 STOP B9)
- **Y46 · Vercel 生产部署 + DNS**: `vercel --prod` + DNS 切到 app.genpano.dev (0' Session 已配置 records); Lighthouse a11y ≥ 90 / Performance ≥ 70 (Phase 2 优化到 ≥ 90)
- **Y47 · Layer 3 Frank S1-S13 final aggregate walkthrough**: 13 sub-views 全部点击 + 5 KPI 渲染 + Citation 5 Tab + KG G6 v5 + CSV 8 download + 11 Legacy 301 (3 条抽样 dashboard / brands/lancome / industries) + Mixpanel events 触发可见
- **Y48 · MVP COMPLETE git tag + RELEASE_NOTES_v1.0.md**: tag `mvp-1.0` 锁 main HEAD, RELEASE_NOTES 收录所有 Session 0' → 4b'.4 交付清单
- **Y49 · CLAUDE.md 决策 #30 写入**: "MVP Phase Complete (2026-04-XX) — IA v2.0 + 13 sub-views + 38 harness + 测试 A++ + Vercel prod + tag mvp-1.0", 引本 Session 4b'.4 Phase Gate 报告
- **Y50 · 决策 #25 规则 7 一致性回路**: 重跑本 §0 全部 grep + 验证 §1 真相源索引段号仍存在 + 偏差登记进 §C

### ❌ 本 Session 不做 (明确延后)

- **Phase 2 性能优化** (FCP < 1s / LCP < 2.5s 全绿) → 由 Phase 2 Performance Session 承接
- **Phase 2 全量 E2E 覆盖** (TEST_STRATEGY §11 P1 5 项 / P2 4 项 之 E2E) → 由 Phase 2 测试加固 Session 承接
- **MCP server + Citation 6 行动面 v1.1** (PRD §4.2.7 D-F: Authority Radar / Same-Group Acquisition / Simulator) → 由 v1.1 Session 5 承接
- **Phase 2 多 Project 显式暴露** (决策 #2: MVP 单 Project 隐身, Phase 2 ProjectPicker 显式) → 由 Phase 2 Session 承接
- **CSV #9 pr_targets / #10 content_gap** (决策 #19: v1.1/Phase 2 延后) → 不属本 Session
- **A1' Admin 用户管理 + A2' KG QA + A3' Alerts + A4' System Health + A5' Citation Tier CRUD + MCP Token** → A1'-A5' Sessions 独立交付 (Admin Phase 与 App Phase 解耦)
- **Phase 2 Mobile native app / SDK** → 不在 MVP 计划

---

## §3 · STOP Triggers (规则 12 三类 + 本 Session 专属)

### Type A · 环境失败 (基建 / 工具链)

- **A4** 上游 Session 4b'.3 / 0' 任一非 GREEN → 暂停, 回追上游 Phase Gate
- **A5** Vitest / Playwright / Vercel CLI 任一在 CI 中 non-zero exit → 检查日志, 修复后重跑 (≥3 次同样失败则 STOP, 上报)
- **A6** Vercel deploy 失败 (build error / 环境变量缺失 / DNS 验证不通过) → 回 0' Session 补基建, 4b'.4 不临时补
- **A8** preview env app.preview.genpano.dev 在 4b'.4 期间 5xx 持续超 10min → 暂停, 监控基建恢复
- **A9** Production 部署后 5xx > 1% (Vercel analytics) 超 5min → 立即 rollback 到上一个绿 commit, 不允许带 5xx 进入 MVP COMPLETE

### Type B · 真相源冲突 (PRD / DESIGN_TOKENS / CLAUDE.md)

- **B1** PRD §4.6-IA-v2 / TEST_STRATEGY §11 / DESIGN_TOKENS C1-C15 任一与本 Session 实现冲突 → 不修代码, 修文档为 source of truth, 同步 CLAUDE.md 决策记录
- **B6** 决策 #2 IA v2.0 13 sub-views 任一 sub-view 仍是 ComingSoon 占位 → 回 4b'.1/4b'.2/4b'.3 补完, 不在 4b'.4 临时实装
- **B7** CLAUDE.md 最近 3 条决策有未读 → 必须读全文加入 §1, 不允许跳过
- **B8** memory `feedback_*` 与本 Session 实现冲突 (例: feedback_production_deps 要求只用 Playwright, 实现却引入 Percy) → 修代码到 memory 一致, memory 是软真相源
- **B9** Visual regression baseline 与新 screenshot diff > 5% 像素差异且无意图 → 检查 4b'.1/4b'.2/4b'.3 是否引入未声明的视觉变更; 若变更合理则更新 baseline (`pnpm playwright test --update-snapshots`) + Frank 视觉确认

### Type C · 范围溢出 (本 Session 专属)

- **C11** 任一新文件 > 500 行 → 拆分; verify_4b4.sh / RELEASE_NOTES_v1.0.md 是文档不计代码限制
- **C13** Playwright spec 用 `await page.waitForTimeout(N)` 硬等待 → 改用 `page.waitForSelector` / `page.waitForResponse` (memory `feedback_production_deps` 衍生: 不写 brittle test)
- **C15** RELEASE_NOTES_v1.0.md 含中英任一硬编码 → MVP 1.0 发布说明用纯英文 markdown (海外开源 + Frank 国际版双用)
- **C19** 任一 Mixpanel event 携 PII (email / phone / IP) → 立即 STOP, 检查 4b'.1/4b'.2/4b'.3 埋点点位 (D6 harness 应已拦, 此处复检)
- **C26** Critical path E2E 覆盖不到关键转化 (注册 + onboarding + 5 KPI + Citation 5 Tab + CSV download 任一缺失) → 必须补; smoke 1 条覆盖最高价值流, 不可省
- **C27** Lighthouse a11y < 90 → 修 (alt 属性 / aria-label / 键盘可达 / contrast ≥ 4.5:1); 决策 #18 测试 A++ 隐含 a11y P0
- **C28** git tag mvp-1.0 在 main 非最新 commit 上 → 必须 tag 到 main HEAD, 否则 RELEASE_NOTES 与 production 部署 不一致
- **C29** RELEASE_NOTES 漏列 Session 0' → 4b'.4 任一 Phase Gate 交付 → 补全, MVP 1.0 须完整可追溯

---

## §4 · Harness (本 Session 不新增, 验证 38 持续生效)

**L3/L4 Phase Gate**: 本 sub-Session 验收追溯到 SESSION_4B_PRIME_PROMPT.md §4 L3/L4 Phase Gate 卡控 (Hard Fail), 详见 REPLAN_2026_04_26.md §5 4b' 行.

### 不新增 Group I 或其他规则

`scripts/ci-harness-selftest.mjs` EXPECTED_POSITIVES = 38 (4b'.2 锁定后不变):

```
A1-A6 (i18n/文案) = 6
B1-B7 (图表 C1-C7) = 7
C9-C15 (V2 分析页) = 7 (含 C15-1/2/3 共 9 子规则, 但归类按 7 大段)
D1-D10 (产品决策) = 10
E1-E4 (Citation + KG) = 4
F1-F4 (frontend/backend self-seeded) = 4 (含 F4-1/2/3 共 6 子规则, 归 4 大段)
Total Group A-F = 38
Group I (4b'.2 引入 I1-I5 + 4b'.1 引入 I6) = 6 (聚合到 38 总数内, 不另计)
```

### 验证规则持续生效 (本 Session 任务)

```bash
# 跑全 selftest, 期望 38/38 PASS
node scripts/ci-harness-selftest.mjs
# 期望输出: ● selftest: PASS  (38 / 38 fixture expectations met)

# 跑全 ci-check (主动扫所有规则)
node scripts/ci-check.mjs
# 期望: Group A/B/C/D/E/F + I 全部 GREEN

# 跑 data contracts (Node 关系约束)
npm run ci:data-contracts
# 期望: DC1-DC7 全 PASS
```

### Mixpanel + Vitest + Playwright + Coverage 终验完整性

| 验收点 | 命令 | GREEN 阈值 |
| --- | --- | --- |
| Vitest 单测全量覆盖 | `pnpm vitest --coverage --run` | branches/lines/funcs/statements ≥ 80% (跨 4b'.1+4b'.2+4b'.3 全部代码) |
| Playwright critical path | `pnpm playwright test specs/critical-path.spec.ts` | 1/1 PASS, 含 CSV download BOM 验证 |
| Visual regression 13 × 4 | `pnpm playwright test specs/visual-regression.spec.ts` | 52/52 baseline 一致 (或首跑生成 baseline) |
| Lighthouse a11y | `pnpm dlx @lhci/cli autorun` (CI 集成) | a11y ≥ 90 / performance ≥ 70 / best-practices ≥ 90 |
| Bundle size | `du -sk frontend/dist` | < 2MB (gzipped < 600KB) |
| Mixpanel events | Frank 手动在 Mixpanel dashboard 验证 | 5 KPI 加载触发 #1-#10, Citation Tab 切换 #50-#53, CSV download #53 (with export_type 字段) |

---

## §5 · Step Delivery (重新编号 Steps 0-2, 原 §5 Steps 10-12)

### Step 0 · 聚合 Vitest + Group I + Playwright smoke + Visual regression

**0.1** 验证 4b'.3 GREEN: `bash scripts/verify_4b3.sh` 13/13 全绿 (重跑); 不绿即 STOP Type A4

**0.2** 跑 Vitest 全量带 coverage:
```bash
cd frontend
pnpm vitest --coverage --run
```
产出 `coverage/index.html`; 检查 branches/lines/funcs/statements 是否全部 ≥ 80%; 如不达, 检查 4b'.1/4b'.2/4b'.3 各 lib 是否有未覆盖代码 (主要嫌疑: charts lib 边界 case / KG g6Composer 错误分支 / CSV 10k 行 cap 边界)

**0.3** 创建 `frontend/playwright/specs/critical-path.spec.ts`:
```typescript
// register → onboarding 4 step → /brand/overview KPI 5 → /brand/citations Tab 5 → CSV export
import { test, expect } from '@playwright/test';

test('MVP critical path: register → onboarding → /brand/overview → CSV export', async ({ page }) => {
  // Step 1: Register
  await page.goto('/register');
  await page.fill('[data-testid=email]', `test+${Date.now()}@example.com`);
  await page.fill('[data-testid=password]', 'Test1234567890!');
  await page.click('[data-testid=register-submit]');
  await expect(page).toHaveURL(/onboarding/);

  // Step 2: Onboarding 4 步
  // 选行业
  await page.click('[data-testid=industry-beauty-personal-care]');
  await page.click('[data-testid=onboarding-next]');
  // 选主品牌
  await page.click('[data-testid=brand-loreal]');
  await page.click('[data-testid=onboarding-next]');
  // 选竞品
  await page.click('[data-testid=competitor-estee-lauder]');
  await page.click('[data-testid=onboarding-next]');
  // 偏好
  await page.click('[data-testid=onboarding-finish]');

  // Step 3: /brand/overview 5 KPI 渲染
  await expect(page).toHaveURL(/\/brand\/overview/);
  await expect(page.locator('[data-testid=kpi-mention-rate]')).toBeVisible();
  await expect(page.locator('[data-testid=kpi-sov]')).toBeVisible();
  await expect(page.locator('[data-testid=kpi-sentiment]')).toBeVisible();
  await expect(page.locator('[data-testid=kpi-citation-share]')).toBeVisible();
  await expect(page.locator('[data-testid=kpi-industry-rank]')).toBeVisible();

  // Step 4: /brand/citations Tab 5 切换
  await page.click('[data-testid=nav-citations]');
  await expect(page.locator('[data-testid=tab-overview]')).toBeVisible();
  await page.click('[data-testid=tab-content-gap]');
  await page.click('[data-testid=tab-pr-targets]');
  await page.click('[data-testid=tab-competitor-decomp]');
  await page.click('[data-testid=tab-attribution]');

  // Step 5: CSV 下载 + BOM 验证
  const downloadPromise = page.waitForEvent('download');
  await page.click('[data-testid=csv-export-button]');
  const download = await downloadPromise;
  const path = await download.path();
  const fs = require('fs');
  const content = fs.readFileSync(path);
  expect(content[0]).toBe(0xEF);  // BOM byte 1
  expect(content[1]).toBe(0xBB);  // BOM byte 2
  expect(content[2]).toBe(0xBF);  // BOM byte 3
  // 文件 ≥ 1KB (非空)
  expect(content.length).toBeGreaterThan(1024);
});
```

**0.4** 创建 `frontend/playwright/specs/visual-regression.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

const ROUTES = [
  '/brand/overview', '/brand/visibility', '/brand/topics', '/brand/sentiment',
  '/brand/citations', '/brand/products', '/brand/competitors',
  '/brand/diagnostics', '/brand/reports',
  '/industry/overview', '/industry/ranking', '/industry/topics', '/industry/knowledge-graph'
];
const VIEWPORTS = [
  { name: 'mobile-375', width: 375, height: 812 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop-1280', width: 1280, height: 720 },
  { name: 'wide-1920', width: 1920, height: 1080 },
];

for (const route of ROUTES) {
  for (const vp of VIEWPORTS) {
    test(`visual: ${route} @ ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      // 假设已登陆 (storageState 复用 critical path 注册的 session)
      await page.goto(route);
      // 等待 KG canvas / chart 完成渲染
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot(`${route.replace(/\//g, '_')}_${vp.name}.png`, {
        maxDiffPixelRatio: 0.05,  // ≤5% 像素差容忍
        fullPage: true,
      });
    });
  }
}
```

**0.5** 跑 Playwright 全量:
```bash
pnpm playwright install --with-deps
pnpm playwright test
```
首跑生成 baseline (52 screenshots + 1 critical path); 已有 baseline 走 diff 对照, 任一 > 5% 即 STOP B9

**0.6** 跑 Lighthouse:
```bash
pnpm dlx @lhci/cli autorun --upload.target=temporary-public-storage
```
a11y < 90 即 STOP C27

**0.7** 跑 selftest + ci-check + data-contracts:
```bash
node scripts/ci-harness-selftest.mjs   # 期望 38/38 PASS
node scripts/ci-check.mjs              # 期望 Group A-F + I 全 PASS
npm run ci:data-contracts              # 期望 DC1-DC7 全 PASS
```

**0.8** 终验产出报告 `docs/SESSION_4B_4_VERIFICATION.md`: 列 Vitest coverage % + Playwright pass count + Lighthouse score + Bundle size + selftest 38/38 + harness drift 任 0

### Step 1 · Vercel 生产部署 + DNS + 监控

**1.1** 更新 `vercel.json`: 4b'.3 已写 11 redirects, 此处加 headers + region:
```json
{
  "framework": "vite",
  "redirects": [ /* 4b'.3 已写 11 entries, 不动 */ ],
  "headers": [
    { "source": "/(.*)", "headers": [
      { "key": "X-Frame-Options", "value": "DENY" },
      { "key": "X-Content-Type-Options", "value": "nosniff" },
      { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
      { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
    ]}
  ],
  "regions": ["hkg1"],
  "buildCommand": "pnpm build",
  "outputDirectory": "dist"
}
```

**1.2** 更新 `.github/workflows/ci.yml`: 添加 deploy-production job (main only):
```yaml
deploy-production:
  needs: [lint, typecheck, test, build, playwright]
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: actions/checkout@v4
    - uses: amondnet/vercel-action@v25
      with:
        vercel-token: ${{ secrets.VERCEL_TOKEN }}
        vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
        vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
        vercel-args: '--prod'
        scope: ${{ secrets.VERCEL_ORG_ID }}
```

**1.3** 手动跑 Vercel 部署 (CI 自动跑前先验证):
```bash
cd frontend
vercel link --yes
vercel --prod
```
等 build + deploy 完成 (~3min), 取生产 URL `https://app.genpano.dev`

**1.4** DNS 验证 (0' Session 已配置 records):
```bash
dig +short app.genpano.dev
# 期望: 返回 cname.vercel-dns.com 或 76.76.21.21
curl -I https://app.genpano.dev
# 期望: 200 + x-vercel-id 标头存在
```

**1.5** 11 Legacy 301 服务端验证 (生产):
```bash
for path in /dashboard '/brands/lancome' '/brands/lancome/products/123' /topics /industries /knowledge-graph /reports /auth /sign-up /onboarding/v1; do
  echo "=== $path ==="
  curl -sI "https://app.genpano.dev$path" | grep -E "HTTP|Location"
done
# 期望: 每条返回 301 + Location 指向新 IA v2.0 路由 (除 /diagnostics 是 410 Gone)
echo "=== /diagnostics ==="
curl -sI "https://app.genpano.dev/diagnostics" | grep -E "HTTP"
# 期望: 410
```

**1.6** Vercel Analytics 启用: dashboard 打开 Web Analytics + Speed Insights, 监控 5min 看 5xx rate < 0.1% / FCP < 2.5s

### Step 2 · Frank L3 终验 + MVP COMPLETE 收尾

**2.1** Frank 在生产 `https://app.genpano.dev` 跑全量 walkthrough:

| Scenario | 验证点 |
| --- | --- |
| **S1** 登录 | /login → email-first → /brand/overview |
| **S2** Onboarding | 新账号 → 4 step → 落地 /brand/overview |
| **S3** /brand/overview | 5 KPI 渲染 + Sparkline 100% 默认 + 顶栏 pill toggle 🎯 ⇌ 🌍 |
| **S4** /brand/visibility | BrandTopicHeatmap + FilterBar + URL state 同步 |
| **S5** /brand/topics | TopicIntentMatrix 共享组件 + 4-stat grid |
| **S6** /brand/sentiment | DonutChart size=180 + diverging heatmap |
| **S7** /brand/citations | 5 Tab 切换 + Authority Radar + Same-Group + Acquisition (v1.1 占位 OK) |
| **S8** /brand/products | BCG 四象限 + Sparkline grid + 表格; 点 product 卡 → /brand/products/:productId?brandId=:id 详情页 (Wave-4 query string) |
| **S9** /brand/competitors | Top 3 威胁卡 + 雷达 + 胜负 heatmap + Tier 2 矩阵 + Same-Group 卡 |
| **S10** /industry/overview | KPI + Top 5 品牌 |
| **S11** /industry/topics | 5 段 v3.2 + TopicIntentMatrix |
| **S12** /industry/knowledge-graph | G6 v5 8 坑点全验 (radial / click-pin / 1.5x scale / shadowBlur / label 外置 / autoFit / opacity=1 / single composer) |
| **S13** /industry/ranking | CSV 下载 → Excel 打开 BOM 正确 + UTF-8 中文不乱码 |
| **S-final** 11 Legacy 301 抽样 | dashboard / brands/lancome / industries 三条 → 浏览器自动 follow redirect 到新路由 + 历史栈 1 条不留 (replace) |

**2.2** Frank 在 Mixpanel dashboard 验证事件:
- #1-#10 路由切换事件触发
- #44/#45/#46 (旧 Empty State) 不应触发
- #50-#53 Citation Tab + CSV download 触发
- #63/#64/#65 + #70 Onboarding step completed 触发
- 任一 event 含 PII (email/phone/IP) → STOP Type C19, 回 4b'.1/4b'.2/4b'.3 复查

**2.3** 创建 `RELEASE_NOTES_v1.0.md`:
```markdown
# GENPANO MVP 1.0 · Release Notes
**Tag**: `mvp-1.0` · **Date**: 2026-04-XX · **Production**: https://app.genpano.dev

## What Shipped

### IA v2.0 (Brand Mode + Industry Mode)
- 13 sub-views (Brand Mode 9 + Industry Mode 4)
- Stripe-style pill toggle 🎯 ⇌ 🌍
- 11 Legacy 301 redirects (dual-layer: client React Router + server Vercel)

### Brand Mode 9 sub-views
- /brand/overview (5 KPI: mention-rate / sov / sentiment / citation-share / industry-rank)
- /brand/visibility (BrandTopicHeatmap + FilterBar URL state)
- /brand/topics (TopicIntentMatrix 共享组件 + 4-stat)
- /brand/sentiment (DonutChart + diverging heatmap)
- /brand/citations (5 Tab: Overview / Content Gap / PR Targets / Competitor Decomp / Attribution)
- /brand/products (BCG quadrant + Sparkline grid + table; detail via ?brandId= query string)
- /brand/competitors (Top 3 threat → Radar + Win/Loss heatmap + Tier-2 matrix + Same-Group card)
- /brand/diagnostics, /brand/reports

### Industry Mode 4 sub-views
- /industry/overview, /industry/ranking
- /industry/topics (v3.2 5-段 layout)
- /industry/knowledge-graph (AntV G6 v5: radial / click-pin / 1.5x scale / shadowBlur / label 外置 / autoFit / single composer)

### CSV Export (8 types)
- industry_ranking, brand_visibility, brand_sentiment, brand_topics, competitor_matrix, product_bcg, citation_domains, pr_targets
- UTF-8 BOM, csv-stringify (no hand-roll), 10k row hard cap, 5/min throttle

### Test A++ infrastructure
- 4 layers (L1 Harness 38 grep / L2 Vitest 80% coverage / L3 Frank L3 walkthrough / L4 Playwright critical path + visual regression 52 screenshots)
- Mixpanel events #1-#70+
- OpenAPI typegen drift detection
- Vercel preview env per branch + production deploy

### Stack
- Backend: FastAPI + SQLAlchemy 2.0 async + Alembic + Celery + Redis + Pydantic v2
- Frontend: Vite + React 18 + TypeScript strict + Tailwind + TanStack Query v5 + Recharts + AntV G6 v5
- CI: GitHub Actions (lint / typecheck / vitest / playwright / build / deploy)

## What's Deferred to v1.1 / Phase 2
- Citation 6 行动面 v1.1 (Authority Radar Acquisition events / Simulator)
- CSV #9 pr_targets / #10 content_gap (Phase 2 paid feature)
- MCP server + API token (A5' Session)
- Admin Phase A1'-A5'
- Mobile native + SDK
- Multi-Project explicit picker
```

**2.4** Git tag + push:
```bash
git checkout main
git pull origin main
git tag -a mvp-1.0 -m "MVP 1.0: IA v2.0 + 13 sub-views + 38 harness + Test A++"
git push origin mvp-1.0
git push origin main
```

**2.5** CLAUDE.md 决策 #30 写入 (本 Session 收尾的最后一步):
```markdown
30. **MVP Phase Complete (2026-04-XX)**: Sessions 0' / A0' / 4a' / 1' / 1.5' / 1.2' / 2' / 2.1' / 3' / 4b'.1-4 全部 GREEN, IA v2.0 13 sub-views 全部实装 (Brand Mode 9 + Industry Mode 4), 38 harness selftest 锁定, 测试 A++ (L1 grep + L2 Vitest 80% + L3 Frank walkthrough + L4 Playwright critical path + visual regression 52 screenshots), Vercel production 上线 https://app.genpano.dev, git tag mvp-1.0 锁定 main HEAD, RELEASE_NOTES_v1.0.md 收录全部交付清单. v1.1 Phase 2 由 Citation Action Surfaces (Authority Radar Acquisition / Simulator) + MCP Server + Admin Phase A1'-A5' 承接, 不在本决策范围.
```

**2.6** 决策 #25 规则 7 一致性回路: 重跑 §0 全部 grep + 验证 §1 真相源索引段号仍存在; 任何漂移登记到 §C 偏差段

**2.7** 偏差登记 (规则 3 强制): 列 C1/C2/... (例: Lighthouse performance 仅 75/90 未达 ≥ 90 — 接受 MVP 标准 ≥ 70, Phase 2 性能优化承接)

---

## §6 · Phase Gate (3 层 L1 / L2 / L3 终验)

### L1 · 自动化验证 (`bash scripts/verify_4b4.sh`)

**期望: 13 / 13 全 GREEN; 任一红即 STOP**

```bash
#!/bin/bash
# scripts/verify_4b4.sh · 4b'.4 终验脚本

set -e
cd "$(dirname "$0")/.."

echo "=== 1. 上游 verify_4b1/4b2/4b3 全量重跑 ==="
bash scripts/verify_4b1.sh
bash scripts/verify_4b2.sh
bash scripts/verify_4b3.sh

echo "=== 2. Vitest 全量 80% coverage ==="
cd frontend
pnpm vitest --coverage --run
# 验 coverage thresholds: branches/lines/functions/statements ≥ 80
node -e "
  const cov = require('./coverage/coverage-summary.json').total;
  ['branches','lines','functions','statements'].forEach(k=>{
    if (cov[k].pct < 80) { console.error(k+' '+cov[k].pct+'%'); process.exit(1); }
  });
  console.log('Vitest coverage: all 4 metrics >=80%');
"
cd ..

echo "=== 3. Playwright critical path ==="
cd frontend
pnpm playwright test specs/critical-path.spec.ts
cd ..

echo "=== 4. Playwright visual regression 52 screenshots ==="
cd frontend
pnpm playwright test specs/visual-regression.spec.ts
cd ..

echo "=== 5. Lighthouse a11y >= 90 ==="
cd frontend
pnpm dlx @lhci/cli autorun --upload.target=temporary-public-storage
# CI 应解析 a11y >= 90, 不绿在 dlx 内部 exit 非零
cd ..

echo "=== 6. Bundle size < 2MB ==="
SIZE=$(du -sk frontend/dist | awk '{print $1}')
if [ "$SIZE" -gt 2048 ]; then echo "Bundle $SIZE KB > 2MB"; exit 1; fi
echo "Bundle size: $SIZE KB OK"

echo "=== 7. msw not in production dist ==="
! rg -q "msw" frontend/dist/assets/*.js

echo "=== 8. OpenAPI typegen drift ==="
curl -sf https://api.preview.genpano.dev/api/v1/openapi.json -o /tmp/openapi-fresh.json
diff <(jq -S . /tmp/openapi-fresh.json) <(jq -S . frontend/src/api/openapi-snapshot.json) || (echo "OpenAPI drift"; exit 1)

echo "=== 9. Harness selftest 38/38 ==="
node scripts/ci-harness-selftest.mjs | grep "PASS  (38 / 38"

echo "=== 10. ci-check Group A-F + I 全 GREEN ==="
node scripts/ci-check.mjs

echo "=== 11. Data contracts DC1-DC7 ==="
npm run ci:data-contracts

echo "=== 12. 11 Legacy 301 客户端 + 服务端双层 ==="
test $(rg -c "Navigate replace" frontend/src/router/legacyRedirects.tsx) -ge 11
test $(cat vercel.json | jq '.redirects | length') -ge 11

echo "=== 13. RELEASE_NOTES_v1.0.md 存在 + 含 mvp-1.0 tag ==="
test -f RELEASE_NOTES_v1.0.md
rg -q "mvp-1.0" RELEASE_NOTES_v1.0.md

echo "=== ALL 13 CHECKS PASSED ==="
```

### L2 · Harness selftest (38/38 lock-in)

```bash
node scripts/ci-harness-selftest.mjs
```

期望: `● selftest: PASS  (38 / 38 fixture expectations met)`

### L3 · Frank 生产终验 (S1-S13 + S-final + Mixpanel + 11 Legacy 301)

**Frank 在 https://app.genpano.dev 完成**:
- ✅ S1-S13 walkthrough (上 §5 Step 2.1 表格 13 路由 + 各页核心交互)
- ✅ S-final 11 Legacy 301 抽样 (dashboard / brands/lancome / industries)
- ✅ Mixpanel events 触发 (5 KPI / Citation Tab / CSV / Onboarding 各类事件)
- ✅ Vercel Analytics 5xx < 0.1% / FCP < 2.5s 持续 5min

### Phase Gate 通过条件

L1 13/13 + L2 38/38 + L3 Frank 全部 ✅ → **MVP 1.0 GREEN, git tag mvp-1.0 + RELEASE_NOTES + CLAUDE.md 决策 #30 提交**

---

## §7 · Downstream Note (本 Session = MVP MVP-Phase 终点)

**本 Session 之后无下游 Session** (MVP Phase 完成):

- v1.1 Phase 2 工作由独立计划承接 (Citation 行动面 v1.1 / MCP server / Admin A1'-A5' / Phase 2 性能优化 / Mobile)
- Admin Phase 与 App Phase 解耦, A1' Admin 用户管理可在 MVP 1.0 上线后独立启动 (依赖 A0' GREEN, A0' 已交付)
- Frank 决策 v1.1 优先级 + Phase 2 时间表 由 `docs/PRODUCT_PLAN.md` 后续版本承载

**禁止**:
- 在 4b'.4 之后续推任何 "4b'.5" — MVP Phase 已完成
- 在 mvp-1.0 tag 之后修改 main 而不打新 tag (v1.1 必须 tag v1.1.0)
- RELEASE_NOTES_v1.0.md 之后追加 — 改用 RELEASE_NOTES_v1.1.md

---

## §C · 偏差登记 (规则 3, Session 完成时回填)

> 在 Phase Gate GREEN 时回填实施过程中与真相源不可调和的偏差; 编号 C1/C2/... 各偏差含: 决策点描述 / 真相源原表达 / 实施路径 / 理由 / 同步回 CLAUDE.md 决策 #30 备注。

(Phase Gate 完成后由实施 Claude Code 写入此段)

---

## §Z · Decision-Freshness Final Check (规则 11 收尾)

开工前 30min 内最后一次 grep 验证:

- ✅ CLAUDE.md 决策 #2 (IA v2.0 13 sub-views) 仍是真相源
- ✅ CLAUDE.md 决策 #18 (测试 A++) 仍是真相源
- ✅ CLAUDE.md 决策 #20 (V2 分析页 C9-C15) 仍是真相源
- ✅ CLAUDE.md 决策 #21 (Review 修复闭环 38 harness 5 组 A-E) 仍是真相源
- ✅ CLAUDE.md 决策 #25 (Prompt 公约 12 条) 仍是真相源
- ✅ memory `feedback_genpano_session_commit_rule` (Session 结束即 commit) 已遵守
- ✅ memory `feedback_genpano_session_preview_env_2026_04_26` (preview env 可点击) 已遵守
- ✅ memory `feedback_production_deps` (Playwright 唯一视觉回归) 已遵守

**已知接受的 trade-off**:
- ❌ Lighthouse Performance ≥ 90 不达 (MVP 接受 ≥ 70, Phase 2 性能 Session 承接)
- ❌ Playwright 全量 E2E 覆盖 P0 10 项不达 (MVP 1 条 critical path + 52 visual regression 已是 L4 充分证据, P0 由 L1+L2 主覆盖, P1/P2 E2E 延 Phase 2)
- ❌ 多语言 e2e (en-US 完整 walkthrough) 延 Phase 2 (MVP 中文为主, en-US 字典齐 + UI 切换可工作即接受)

---

🎯 **MVP COMPLETE 是 GENPANO 的发射点, 不是终点**. v1.1 / Phase 2 沿决策 #29 Python pivot + 决策 #30 MVP Phase Complete 双 anchor 继续推进.
