# GENPANO 测试策略 (Test Strategy)

> **版本**: v1.0 (2026-04-17)
> **目标读者**: Claude Code Session 执行者 + Frank (产品决策 / 冒烟验收)
> **上位文档**: `docs/HARNESS_ENGINEERING.md` §5 (方法论) · `docs/PRD.md` (需求真相源) · `docs/CLAUDE_CODE_SESSIONS.md` (实施计划)
> **核心理念**: **高度自动化 + Frank 0 日常介入**——CI 全绿即可合并, 发布前无需人工冒烟。

---

## 1. 目标与原则

### 1.1 量化目标 (Service Level Objective)

| 指标 | 目标 |
|---|---|
| 单次 PR CI 耗时 | **< 12 分钟** (含单元 + 集成 + E2E + 视觉回归) |
| Frank 日常测试介入 | **0 分钟 / PR** (CI 红才看) |
| 发布前人工冒烟 | **0 分钟** (视觉回归 + 关键链路 E2E 已覆盖) |
| 关键路径单元测试覆盖率 | **≥ 80%** (KPI 计算 / 解析器 / 管线) |
| 关键链路 E2E 覆盖率 | **6 条核心链路全覆盖** (§4.3) |
| 视觉回归 baseline 覆盖 | **≥ 40 张截图** (§4.4) |
| Harness grep 规则 | **≥ 30 条** (pre-commit + CI 双层) |

### 1.2 原则

1. **Co-located 测试**: `*.test.ts` 与源代码同目录, 不建中心化 `tests/` 大仓; 跨模块 E2E 与视觉回归集中在 `e2e/` 和 `visual/`
2. **单一真相源**: 所有 Harness grep 汇总到 `scripts/ci-check.mjs` 一个入口, pre-commit + CI 跑同一条命令
3. **确定性优先**: 外部依赖 (爬取 / LLM API) 用 HAR 录制回放, 不走真实网络——CI 稳定性 > 实时性
4. **AI 写测试, 人审意图**: Claude Code 每个 Session 产出测试代码, Frank 在 Phase Gate 只审 "测试意图是否对齐需求", 不审代码细节
5. **拒绝覆盖率游戏**: 不追 100% 覆盖率, 只追 "断了就崩" 的关键路径 ≥ 80%
6. **视觉是人类任务 → 自动化它**: Screenshot diff 替代人眼审 UI; Baseline 更新走 PR review 流程

---

## 2. 分层测试体系 (4 Layers)

```
┌──────────────────────────────────────────────────┐
│ L4: E2E + 视觉回归 (Playwright)    ~6 specs + 40 张 │   慢, 高置信
├──────────────────────────────────────────────────┤
│ L3: 集成 + 契约 (Vitest + HAR + OpenAPI)  ~80 tests │   中速
├──────────────────────────────────────────────────┤
│ L2: 单元测试 (Vitest)             ~200 tests       │   快, 聚焦
├──────────────────────────────────────────────────┤
│ L1: 静态 Harness (grep + schema lint)  ~30 规则    │   毫秒级
└──────────────────────────────────────────────────┘
```

### 2.1 L1 静态 Harness 层

**工具**: `scripts/ci-check.mjs` 汇总所有 grep + `prisma validate` + i18n key diff

**运行时机**: pre-commit hook + CI 第一步 (必须先过才跑其他层)

**覆盖规则** (Session 0 必须落齐 **38 条**, 后续 Session 仅可新增不可下线; 完整规则表与 fixHint 见 `scripts/ci-check.mjs` 注释 + `docs/CLAUDE_CODE_SESSIONS.md` Session 0 §5.3 A-E 五组):

| 组 | 规则编号 | 数量 | 主题 | PRD / Decision 出处 |
|---|---|---|---|---|
| A | A1-A6 | 6 | i18n / 文案边界 (CJK 泄漏 / 双语成对 / formatBrand / 开发约束 i18n / JSX / interpolation API) | §4.10.4a.D + §4.6.0a.D |
| B | B1-B7 | 7 | 图表契约 C1-C7 (Sparkline 100% / Recharts token / SoV 其他 / Sentiment toFixed / 锯齿模数 / Donut size / Ranking) | DESIGN_TOKENS.md C1-C7 |
| C | C9-1..C15-3 | 15 | V2 分析页契约 (heatmap 色带唯一 / FilterBar mount / mentionRate 0-1 / DonutChart 强制 / Quadrant sqrt+showLabels / 密度 / brandId from query) | §4.6-IA-v2.K-N + M.5/M.6 + O Wave-4 |
| D | D1-D7 | 7 | 产品决策契约 (Auth gate / logout 6 步 / Mixpanel PII / 11 个 301 redirect / 匿名 API / Onboarding draft route guard) | §4.1.1-gate + §4.1.1e + §4.11.5 + §4.6-IA-v2 |
| E | E1-E4 | 4 | Citation + KG 契约 (Tier 不硬编码 / tldts 归一化 / 诊断 mutex / pr_score 不硬编码) | §4.2.6 / §4.2.7 / 决策 #19 |
| **合计** | | **38** | | |

> **规则函数化要求**: 每条规则在 `scripts/ci-check.mjs` 内必须是具名函数 `ruleA1_i18nCjkLeak(projectRoot)` + `registerRule('A1', ...)`. 主入口循环调用. 禁止把多条规则塞进一个大 grep——未来下线规则只删一个函数 + 一行 register 调用。

> **历史 Bug 反向追溯**: 每条规则在 §13 "规则历史" 表格里登记一行: `(规则编号, 触发该规则的最早 PR 或 review markdown 链接, "preventive" 表示无历史 Bug 仅做前置预防)`. C5/C7/C13 都是真实 Bug 后增, A6/D7/E4 是预防性。

**落地**:
```js
// scripts/ci-check.mjs (骨架示例)
import { execSync } from 'node:child_process';
const rules = [
  { id: 'C1-sparkline-default', cmd: `grep -nE "(width|height)\\s*=\\s*[0-9]+\\s*[,}]" frontend/src/components/charts/MiniSparkline.jsx` },
  { id: '4.1.1e-return-to',     cmd: `grep -rnE "navigate\\(['\\\"']/auth['\\\"]\\)" frontend/src | grep -v "return_to"` },
  // ... 30+ 规则
];
const failures = rules.filter(r => { try { execSync(r.cmd); return true; } catch { return false; } });
if (failures.length) { console.error(failures); process.exit(1); }
```

### 新增 grep 规则（2026-04-20 决议衍生）

**G-01 Token 未定义兜底**
检查源码中是否引用了不存在的 CSS 变量：
```bash
grep -rnE 'var\(--[a-z0-9-]+\)' src/ | awk -F 'var\\(' '{print $2}' | awk -F ')' '{print $1}' | sort -u > /tmp/used.txt
grep -oE '^--[a-z0-9-]+' src/theme/tokens.css | sort -u > /tmp/defined.txt
comm -23 /tmp/used.txt /tmp/defined.txt
```
预期：空输出（所有引用的 token 均已定义）。

**G-02 API path 风格**
```bash
grep -rnE '/api/v1/[^"'\'']*\{[a-z]+\}' src/ docs/
```
预期：空输出（统一用 `:id` 风格，禁止 `{id}`）。

**G-03 /dashboard 301 redirect**
```bash
curl -sI http://localhost:3000/dashboard | head -5 | grep -q "301"
curl -sI http://localhost:3000/dashboard | grep -i "^Location:" | grep -q "/brand/overview"
```
预期：两条命令均成功退出码 0。

**G-04 Heatmap / Chart token 边界**（DECISIONS §15）
```bash
# Heatmap 组件不得使用 chart token
grep -rn "var(--color-chart-" src/components/heatmap/
# Chart 组件不得使用 heatmap token
grep -rn "var(--color-heatmap-" src/components/charts/
```
预期：空输出。

**G-05 ProfileGroupFilter 覆盖**（DECISIONS §3 衍生）
```bash
grep -l "ProfileGroupFilter" src/pages/BrandDetailPage.jsx src/pages/TopicsPage.jsx src/pages/DiagnosticsPage.jsx
```
预期：三个文件均命中。

**G-06 profileGroupId 单数禁用（Query 层）**（DECISIONS §3）
```bash
# ExecutableQuery 场景必须复数；BrowserProfile 作为 FK 的单数合法，故排除
grep -rnE 'profileGroupId[^s]' src/ | grep -vE 'BrowserProfile|browser_profiles|// FK|/\* FK'
```
预期：空输出。
> 语义边界：一个 BrowserProfile 只属于一个 ProfileGroup（FK 单数），但一条 ExecutableQuery 可由多个 ProfileGroup 之一满足（复数 `profileGroupIds: string[]`，`[]` 表示任意）。见 REVISION_DIFF §设计细节澄清 A。

**G-07 BrowserProfile.profileId 重命名**（DECISIONS §14）
```bash
grep -rn '\.profileId' src/
```
预期：空输出（已全部重命名为 `.instanceId`）。

**G-08 platform_queries DB 命名**（DECISIONS §18 D-P2-2）
```bash
grep -rn "platform_queries" src/ migrations/ docs/
```
预期：仅历史 CHANGELOG 允许，源码 / 新 SQL 为空。

### 2.2 L2 单元测试 (Vitest)

**工具**: Vitest + `@testing-library/react`

**覆盖范围**:

| 模块 | 关键测试点 | Session |
|---|---|---|
| KPI 计算 | 提及率 non-brand 口径 / SoV 分母 / 情感 0-1 vs 0-100 换算 / PANO Score 加权 | 3 |
| 解析器 | 品牌/产品 mention 提取 / 别名归一化 (去重音/小写/短别名消歧) | 1 |
| Prompt 生成 | Topic × Intent × Language 组合 / 引擎语言策略 (豆包中/ChatGPT 双语) | 2 |
| 数据契约 | MetricSnapshot / Diagnostics / Profile 等 Zod schema | 0 |
| Onboarding 逻辑 | 零 Project 态判断 / Empty State 路由 / T1-T9 触发 | 4a |
| 登出契约 | logout() 6 步严格顺序 / silent refresh Promise 缓存 | 4a |
| UI 组件 | PanoRing / WatchBrandButton 6 状态 / ProfileGroupFilter 降级 | 4b |
| 报告 Pipeline | 洞察 Stack L1/L2/L3 生成 / 三读者视角字段填充 | 4b |
| CSV Exporter | 8 个 exportType 字段字典 / UTF-8 BOM / 行数上限截断 | 4b |
| MCP Server | 5 tools × 3 resources 响应 schema | 3 |

**原则**: 关键路径 ≥ 80%; 框架/样板代码不测 (Prisma generated types 不测)

### 2.3 L3 集成 + 契约测试

#### 2.3.1 API 契约测试 (自动生成, Session 3 产出)

**工具**: `openapi.yaml` + `openapi-typescript` + `vitest` + `supertest`

**流程**:
```
openapi.yaml 定义 endpoint + schema
   ↓ (CI 前执行)
生成 TS 类型 + 自动测试 tests/api-contract/*.spec.ts
   ↓
每个 endpoint 自动测:
  - 合法请求 → 200 + 响应符合 schema
  - 缺参 → 400
  - 未授权 → 401 / 403
  - 资源不存在 → 404
  - schema 违规 → 500 或类型错误
```

**收益**: API 改动 → 只改 `openapi.yaml` → 测试自动更新, **零手写维护**

#### 2.3.2 管线集成测试 (HAR 回放, Session 1-2 产出)

**工具**: Playwright `page.routeFromHAR()` + Vitest

**Fixture 布局**:
```
fixtures/scraping/
├── doubao/美白精华推荐-info-morning.har
├── deepseek/平替面霜-commercial.har
├── chatgpt/skincare recommendation-info-zh.har
└── ... (约 48 个 HAR, 覆盖 3 引擎 × 4 意图 × 4 行业)
```

**一次录制流程**:
```bash
# 开发者手动跑一次真实爬取
RECORD_HAR=1 npm run scrape -- --engine doubao --prompt "美白精华推荐"
# 自动产出 fixtures/scraping/doubao/xxx.har, 提交到 git
```

**测试中回放**:
```ts
test('Pipeline E2E: Doubao 推荐精华 → 提及率计算', async ({ page }) => {
  await page.routeFromHAR('fixtures/scraping/doubao/美白精华推荐-info-morning.har');
  const response = await adapter.query('美白精华推荐');
  const mentions = await parser.extract(response);
  const mentionRate = await analytics.computeMentionRate([response]);
  expect(mentionRate).toBe(0.125);  // 1/8 query 命中
});
```

**收益**: CI 跑管线测试不走外网, 100% 确定性, 秒级完成

### 2.4 L4 E2E + 视觉回归 (Playwright)

#### 2.4.1 E2E 关键链路 (6 条, Session 5 收尾补全)

| # | 链路 | 跨 Session | 步数 |
|---|---|---|---|
| 1 | 数据采集链路: 爬取→解析→提及率→面板 KPI→CSV 导出, 6 处数字一致 | 1, 2, 3, 4b | ~10 |
| 2 | 零 Project 新用户引导: 注册 → E1 空态 → 建项目 → 5 KPI 渲染 | 4a, 4b | ~8 |
| 3 | 登出 & 跨标签同步: 两标签 → A 登出 → B 自动跳 `/` → 重登 → silent refresh | 4a | ~7 |
| 4 | 报告生成: 触发周报 → PDF 7 页 → 三读者视角齐全 → L3 Layer 只含锚点无剧本 | 4b | ~6 |
| 5 | i18n 双语完整切换: zh-CN → en-US, Alerts/Settings/品牌名/日期全部翻译 | 4a, 4b | ~8 |
| 6 | 埋点准确性: T1-T9 九条路径 → Mixpanel 47 事件无重复 + 0 PII 泄漏 | 4a | ~9 |

#### 2.4.2 视觉回归 Baseline (~40 张, Session 4b 产出)

**工具**: `@playwright/test` 内置 `expect(page).toHaveScreenshot()` (免费, 不用 Percy)

**Baseline 清单**:

| 页面 | 状态 | 张数 |
|---|---|---|
| DashboardPage | 零 Project 空态 / 有 Project 正常态 | 2 |
| BrandDetailPage | 4 子 Tab × 监控/未监控/未登录 3 态 | 12 |
| BrandProductDetailPage | 默认态 | 1 |
| TopicsPage | 4 层 drilldown | 4 |
| AuthPage | login / register / forgot | 3 |
| IndustryPage | 行业探索视图 | 1 |
| 报告 PDF | 7 页 | 7 |
| SessionExpiredModal | 弹出态 | 1 |
| ProjectCreateWizard (快路径 T9) | step 1-3 | 3 |
| DiagnosticDetail | L1/L2/L3 Stack 完整 | 3 |
| 移动端 (主要 3 页响应式) | 768px 断点 | 3 |

**更新流程**:
```bash
# 设计变更 → 1 行命令更新所有 baseline → PR 中 review diff 图
npx playwright test --update-snapshots
git diff tests/visual/__snapshots__/   # 看图片差异
```

---

## 3. A++ 四支柱 (对应 Phase 0-3 升级路径)

### Phase 0: 静态 Harness + 单元 + 数据契约 (Session 0 落地)

**落地产出**:
- `scripts/ci-check.mjs` (30+ Harness grep 汇总入口)
- `vitest.config.ts` + 首批单元测试样板
- `prisma validate` 挂 pre-commit
- `.husky/pre-commit` + `.github/workflows/ci.yml`
- `openapi.yaml` 初版骨架 (endpoint 定义, Session 3 补 schema)

**预计投入**: Session 0 内 3-4 小时

### Phase 1: HAR 录制回放 (Session 1 落地)

**落地产出**:
- `scripts/record-har.ts` (一键录制工具)
- `fixtures/scraping/` 目录结构
- 每个 Adapter 配套 HAR 回放测试
- CI 中禁用真实网络, 全部走 HAR

**预计投入**: Session 1 内 2-3 小时 (录制样本可后续增量补)

### Phase 2: OpenAPI 契约测试 (Session 3 落地)

**落地产出**:
- `openapi.yaml` 完整 schema (30+ endpoints)
- `scripts/gen-api-tests.ts` (自动生成 `tests/api-contract/*.spec.ts`)
- CI 中跑自动生成的测试

**预计投入**: Session 3 内 4-5 小时

### Phase 3: 视觉回归 baseline (Session 4b 落地)

**落地产出**:
- `tests/visual/*.spec.ts` (~40 张 baseline)
- CI 中 screenshot diff 失败 → 自动上传 diff 到 PR comment
- `docs/VISUAL_REGRESSION_GUIDE.md` (如何看 diff 图 / 如何更新 baseline)

**预计投入**: Session 4b 内 3-4 小时

### Phase 4: CI 自愈循环 (MVP 不做, 预留接口)

Claude Code Action 目前在 beta. MVP 跳过, 留 `.github/workflows/ci-autofix.yml` 骨架文件 + TODO 注释. 等工具稳定后 (预计 2026 Q3) 激活.

**激活后效果**: CI 失败 → Claude agent 自动读日志 → 改代码 → 重 push → 再跑 CI. 日常 PR 80% 失败可自愈.

---

## 4. CI 工作流设计

### 4.1 GitHub Actions 拓扑

```yaml
# .github/workflows/ci.yml
name: CI
on: [pull_request, push]
jobs:
  harness:       # L1 静态, ~30 秒
    steps: [checkout, install, run: npm run check:harness]
  unit:          # L2 单元, ~90 秒
    needs: harness
    steps: [checkout, install, run: npm run test:unit]
  integration:   # L3 集成 + HAR + API 契约, ~3 分钟
    needs: harness
    steps: [checkout, install, run: npm run test:integration]
  e2e:           # L4 E2E + 视觉回归, ~6 分钟
    needs: [unit, integration]
    steps: [checkout, install, playwright install, run: npm run test:e2e]
```

**并行策略**: harness 独立跑最快先反馈; unit 和 integration 并行; e2e 等前两层绿再跑

**总 CI 耗时目标**: < 12 分钟

### 4.2 本地 pre-commit hook

```bash
# .husky/pre-commit
npm run check:harness   # ~3 秒, grep
npm run lint            # ~5 秒, ESLint --cache
npm run test:unit -- --changed   # ~10 秒, 只跑受影响测试
```

pre-push hook 可选加 `npm run test:integration`, 但默认不强制——push 频繁不应被长测阻塞.

### 4.3 失败通知

- PR 中 CI 失败 → GitHub Action 自动在 PR 评论列出 "失败的 Harness 规则 + 失败的测试名 + 失败的视觉 diff 图"
- `docs/CI_FAILURE_PLAYBOOK.md` (Session 5 产出): 每种失败类型的常见原因 + 修复方向

---

## 5. 按 Session 落地时间线

| Session | 测试产出 | 预计投入 |
|---|---|---|
| **Session 0** | ci-check.mjs 骨架 + Vitest + Playwright 配置 + husky + .github/workflows/ci.yml + openapi.yaml 骨架 | 3-4h |
| **Session 1** | HAR 录制脚本 + 爬取 Adapter 单测 + HAR 回放集成测试 | 2-3h |
| **Session 1.5** | KG 构建单测 + 品牌别名匹配单测 + LLM 响应 HAR fixture | 2h |
| **Session 2** | Prompt 生成单测 + 管线集成测试 (Topic → Prompt → Query) | 2h |
| **Session 3** | KPI 计算单测 + 诊断引擎单测 + openapi.yaml 完整 + 契约测试自动生成 | 4-5h |
| **Session 4a** | 登出契约单测 + Onboarding E2E + Mixpanel 事件 schema 验证 | 3h |
| **Session 4b** | UI 组件快照 + Visual Regression baseline ~40 张 + 报告生成单测 | 3-4h |
| **Session 5** | 6 条 E2E 关键链路补全 + docs/CI_FAILURE_PLAYBOOK.md + docs/VISUAL_REGRESSION_GUIDE.md + Phase 4 CI 自愈骨架 | 4h |
| **总计** | | **约 23-27 小时, 分散在 MVP 4 周内** |

---

## 6. 反模式 (明确不做)

| 反模式 | 为什么不做 |
|---|---|
| 追 100% 代码覆盖率 | 边际成本指数增长, Solo 维护不起 |
| 手写 API 测试 (不用 OpenAPI 生成) | 30 个 endpoint × 每个 5 case = 150 条手写测试, 维护地狱 |
| E2E 全覆盖所有页面 | Playwright 脆弱, 只测 6 条关键跨 Session 链路, 其余走 unit + visual |
| 视觉测试用 Percy/Chromatic 付费服务 | Playwright 内置 screenshot diff 足够, 免费 |
| Mutation testing (Stryker) | 跑一次 30-60 分钟, MVP 不值得 |
| 引入第二个测试框架 (如 Jest 并存) | 一套就够, 统一用 Vitest |
| 爬取测试走真实 ChatGPT | 外部 API 每天回答不一样, CI 假阳性, 必须 HAR 回放 |
| 单独写 "测试用例清单" Excel/Word | Solo 不维护, 每个 Session 测试小节已经是执行规范 |
| 追求"测试驱动开发 TDD" | Solo+AI 开发速度优先, 测试作为验收门槛即可 |
| 人工冒烟清单 (发布前手动走 20 条) | 视觉回归 + E2E 已覆盖, 人工只做设计感受判断 |

---

## 7. Phase Gate 测试审查清单

每个 Phase Gate 人类 Review 时, Frank 只审以下 5 条, 不审代码:

- [ ] 本 Session 产出的测试文件数量是否合理 (对照 §5 时间线表)
- [ ] Harness grep 是否覆盖本 Session 引入的新约束 (对照 §2.1 规则表)
- [ ] 关键路径单测覆盖率 ≥ 80% (GitHub Actions 自动报告)
- [ ] 本 Session 的 E2E 链路 / Visual baseline 是否已提交 (若该 Session 负责)
- [ ] CI 在主分支是否全绿

若任一项 ❌, Phase Gate 不通过, 回 Session Prompt 补测试.

---

## 8. 变更流程

本文档是"测试契约的单一真相源". 如需修改:

1. 任何 Session 若要新增/修改 Harness 规则 → PR 同时更新本文档 §2.1 规则表 + `scripts/ci-check.mjs`
2. 任何 Session 若要新增 Visual baseline → PR 同时更新本文档 §2.4.2 清单
3. 反模式条目的豁免 → 必须在 PR 描述中说明豁免理由 + 链接到 Frank 明确授权
4. 覆盖率目标调整 → 需 Frank review + 更新 §1.1 SLO 表

---

## 9. 异常场景覆盖矩阵 (新增 2026-04-21)

> **为什么单列此节**: Review 2026-04-21 §3 指出"边界/异常覆盖零散散落在各 Session, 没有一处汇总能让 Claude Code 一眼看到'哪些异常必须被覆盖'". 本节是**异常路径的单一索引**, Session 0-5 的 L2/L3/L4 测试任务必须覆盖这里的每一行, 且 Harness 中有规则能把漏测拦下来.

### 9.1 认证 & 会话异常 (§4.1.1 / §4.1.1e)

| 场景 | 覆盖层 | 测试文件 (Session) | Harness 兜底 |
|---|---|---|---|
| 未登录访问 `/brand/*` | L4 E2E + L1 D1 | `e2e/auth-gate.spec.ts` (S4a) | D1 `auth-gate-route-guard` |
| 未登录访问 `/brands/:id` (legacy 直链) | L4 E2E + L1 D5 | 同上 | D5 `brand-detail-legacy-301` |
| Access Token 即将过期 15min 静默刷新 | L3 契约 | `tests/integration/auth-silent-refresh.test.ts` (S4a) | — (业务逻辑) |
| Refresh Token 过期 30d 硬登出 | L3 + L4 | `e2e/session-expired-modal.spec.ts` (S4a) | — |
| 登出顺序错 (mixpanel.reset 早于 track) | L1 D2 | Harness 静态 | D2 `logout-6-step-order` |
| BroadcastChannel 不存在浏览器 (Safari <16) | L2 单测 | `useLogout.test.ts` (S4a) | — |
| AuthIdentifierLookup < 400ms 回包 (防枚举) | L3 | `auth-identifier-lookup.test.ts` (S4a) | — |
| 并发登录 (多标签) 同 session 踢出 | L4 E2E | `e2e/multi-tab-logout.spec.ts` (S4a) | — |

### 9.2 数据管线异常 (§4.2 / ADAPTER_CONTRACT §6)

| 错误码 | 覆盖层 | Fixture | 预期行为 |
|---|---|---|---|
| CF_BLOCKED | L3 HAR 回放 | `tests/fixtures/adapters/{engine}/cf-blocked.har` | 降级 API Adapter, 记录 retry_count 到内存不落库 |
| COOKIE_EXPIRED | L3 HAR | `cookie-expired.har` | 账号标记 EXPIRED, 触发自动 re-login (CN 引擎) 或人工告警 (海外) |
| CAPTCHA_REQUIRED | L3 HAR | `captcha-required.har` | 3 级 CAPTCHA 策略: L1 图形 OCR → L2 2Captcha 付费 → L3 人工告警队列 |
| PAGE_CRASHED | L3 | `page-crashed.har` | Playwright `page.isClosed()` 检测, 重启 context |
| PROXY_DEAD | L3 | `proxy-dead.har` | 调度器跳过该节点, `proxy_nodes.health = 'dead'`, 告警 |
| NO_ACCOUNT_AVAILABLE | L2 单测 | `no-account-available.fixture.json` | Query 状态 → PENDING (非 FAILED), 等待账号池恢复再重放 |
| EXTRACT_EMPTY | L3 HAR | `extract-empty.har` | 标记为 UI 变更风险, Trust Score -10 但不算爬取失败 |
| TIMEOUT | L3 | `timeout.har` | 指数退避重试 (3 次), 最终失败记录 timeout_ms 分布 |
| **0-node fallback** (整个代理池全挂 / Ninja Clash 订阅源不可达) | L3 集成 | `tests/integration/proxy-zero-node.test.ts` (S1) | 调度器暂停所有海外 Worker, 降级到国内引擎继续产出, 告警 Frank |
| **账号 pre-warm 失败** (批量 cookie 注入全挂) | L3 | `account-prewarm-failure.test.ts` (S1) | 不影响现有活跃账号, 后台 retry 队列 |

### 9.3 数据完整性 / 边界值异常 (§4.2 / §4.5 / §4.7)

| 场景 | 覆盖层 | 测试 (Session) | 预期 |
|---|---|---|---|
| Sentiment 分数正好 0.5 (tiebreak) | L2 单测 | `sentiment-tiebreak.test.ts` (S3) | PRD §4.2.x 固化规则: `score >= 0.55` 为 positive, `<= 0.45` 为 negative, 中间为 neutral (不是 0.5) |
| 品牌名多语言匹配歧义 (短别名 "C" 撞一堆) | L2 | `brand-alias-normalize.test.ts` (S1.5) | 短别名 ≤2 字符必须带 context 锚点, 否则跳过 |
| 提及率分子分母 non-brand 口径 (§4.2.x) | L2 | `mention-rate-non-brand.test.ts` (S3) | 分母仅统计 `topic.dimension='品类'`, 分子同域 |
| SoV "其他" 大于最大真实品牌片 (C3) | L1 B3 + runtime | `check-data-contracts.mjs` | mock 数据运行时断言 |
| BRANDS.ranking 与 panoScore 降序不一致 (C7) | L1 B7 + runtime | 同上 | 同上 |
| Citation Tier 0 (未知域名) 占比 > 40% | L2 + L3 | `citation-tier-distribution.test.ts` (S3) | 告警但不 block (UI 显示 Unknown 标签) |
| citation_source_loss 与 attribution_mismatch 同时触发 | L1 E3 | Harness 静态 | 互斥, 同函数同 response 禁共存 |
| kg_mined_relations 置信度累积 < 阈值 | L2 | `kg-relation-confidence.test.ts` (S1.5) | 不入库 `kg_brand_relations`, 留在 mined 区待观察 |
| Onboarding 草稿 Project (72h) 过期 | L2 | `draft-project-expiry.test.ts` (S4a) | 定时任务清理 |

### 9.4 UI 空态 / 部分失败 / Loading (§4.6 + §4.8)

| 场景 | 覆盖层 | Fixture | 期望组件 |
|---|---|---|---|
| 零 Project (未 Onboarding) | L4 E2E + Route Guard | `EMPTY_STATE_FIXTURES.NO_PROJECT` | 强制 302 `/onboarding`, 无 App shell |
| 有 Project 但零 Response | L4 Visual | `NO_RESPONSES_YET` | `<EmptyState>` + "数据采集中, 12 小时内回" + skeleton 趋势图 |
| Brand 零提及 | L4 Visual | `BRAND_ZERO_MENTIONS` | KPI 卡 "—" + Empty CTA "调整监测语种 / 添加别名 / 扩 Topic 范围" |
| 某引擎全挂 (豆包 down) | L4 Visual | `PARTIAL_FAIL_SOME_ENGINES_DOWN` | EngineFilterBar 该引擎灰 + tooltip "暂不可用 · 12h 后重试" |
| ProfileGroup 样本不足 | L2 + L4 Visual | `PROFILE_GROUP_UNDER_SAMPLED` | `<ProfileGroupSampleWarning>` + 显示"样本 N < 阈值, 结果仅供参考" |
| Loading 骨架态 | L4 Visual | `INITIAL_FETCH` | Skeleton UI, 500ms 后仍未回落 progressive 态 |
| API 500 | L4 E2E | `ERROR_STATE_FIXTURES.API_500` | 顶部红色 Banner + "重试" 按钮 + Sentry 自动上报 |
| Rate Limited 429 | L4 E2E | `RATE_LIMITED_429` | Toast "请求过于频繁, {retryAfter}s 后重试" + 禁用操作 |

### 9.5 成本 / 配额异常 (§4.9 新增)

| 场景 | 覆盖层 | 测试 | 期望 |
|---|---|---|---|
| 单日 LLM 成本突增 > 200% | L2 单测 | `cost-spike-alert.test.ts` (S3) | 触发 PagerDuty 告警 + 暂停 Topic 扩容 |
| 单次 response token 超长 (> 16K) | L2 | `long-response-truncation.test.ts` (S3) | 截断存 raw_truncated, 警告标签 |
| ai_responses.cost_usd 缺失 (adapter 未记) | L1 harness + L2 | Session 1 新增 grep | Adapter 层 AFTER hook 强制写入 |
| 代理节点账单超额 (Ninja Clash 订阅) | L3 集成 | `proxy-quota.test.ts` (S1) | 降级到备用订阅 + Admin 告警 |

### 9.6 Admin 特有异常 (ADMIN_SESSIONS)

详见本文档 §10 Admin 测试矩阵.

---

## 10. Admin 测试矩阵 (新增 2026-04-21)

> **背景**: Review §2 指出 ADMIN_SESSIONS A2.2/A2.3/A2.4/A3 均缺测试任务. 本节作为 Admin 侧测试契约, ADMIN_CLAUDE_CODE_SESSIONS.md 各 Session 的 "## 测试任务" 小节必须回链到本表.

### 10.1 Admin 测试分层覆盖

| Admin Session | 功能域 | L1 Harness | L2 单测 | L3 集成 / HAR | L4 E2E / Visual |
|---|---|---|---|---|---|
| **A0** Admin 脚手架 + Auth | Admin RBAC + Allow-list | admin-allowlist-env, admin-rbac-role-enum | roleGate.test.ts | admin-login-otp.test.ts (HAR) | admin-login.spec.ts + baseline |
| **A1** KG 审核 | kg_brand_submissions 审核 + merge | kg-change-type-enum, kg-merge-dry-run | kg-merge-algorithm.test.ts | kg-submission-flow.test.ts | admin-kg-review.spec.ts |
| **A2** 爬虫调度 + HAR 回放 | 代理池 + 账号池 + 调度器 | adapter-har-must-sanitize, har-routeFromHAR-usage | proxy-scheduler.test.ts, account-quarantine.test.ts | har-replay-all-adapters.test.ts (routeFromHAR fixture) | admin-scheduler-dashboard.spec.ts |
| **A2.2** HAR routeFromHAR 专项 | 回放正确性 | (inherits above) | — | `har-golden-replay.test.ts` 9 错误码各 1 | admin-har-replay-ui.spec.ts |
| **A2.3** KG 操作 change_type | 事件枚举扩展 | kg-change-type-enum (扩 MERGE/SPLIT/DEMOTE/RECLASSIFY) | kg-audit-log.test.ts | — | — |
| **A2.4** QA 分层抽样 | 质量抽检 | qa-sample-stratify-min | qa-sampler.test.ts (5 层覆盖) | qa-campaign-e2e.test.ts | admin-qa-dashboard.spec.ts |
| **A3** Trust Score + 幻觉检测 | 引擎置信度跟踪 | trust-score-formula, hallucination-detector-threshold | trust-score.test.ts, hallucination-detect.test.ts | trust-trend-ingest.test.ts | admin-trust-dashboard.spec.ts |
| **A4** 运营看板 | 告警 / 成本 / 活跃 | admin-metrics-tokenized | kpi-aggregator.test.ts | — | admin-metrics.spec.ts + baseline |
| **A5 (新增)** Citation Tier CRUD + MCP Token | Tier 参数服务 + Token 签发 | citation-tier-seed-required, mcp-token-bearer-only, mcp-token-jwt-exp | tier-crud.test.ts, mcp-token-issue.test.ts | mcp-token-bearer-contract.test.ts (OpenAPI 契约) | admin-tier-crud.spec.ts, admin-mcp-token.spec.ts |

### 10.2 Admin 特有异常场景

| 场景 | 覆盖层 | 测试 |
|---|---|---|
| 账号被封进隔离池 (quarantine) | L3 集成 (A2) | `account-quarantine-7d-cool-off.test.ts` |
| CAPTCHA 人工队列堆积 > 阈值 | L4 E2E + Visual (A2) | `admin-captcha-queue-overflow.spec.ts` |
| KG merge 冲突 (两个品牌都有强证据) | L2 (A1) | `kg-merge-conflict.test.ts` — 必须进人工审核队列, 禁自动 merge |
| Trust Score 单引擎降至 <0.5 | L2 + L4 (A3) | `trust-score-engine-degrade.test.ts` + visual 告警横幅 |
| Citation Tier 权重调整后溯源 (回溯重算) | L3 (A5) | `tier-retroactive-recompute.test.ts` |
| MCP Token revocation 广播 | L3 (A5) | `mcp-token-revoke-broadcast.test.ts` — JWT 黑名单必须 60s 内全节点生效 |
| Admin allow-list 环境变量缺失 | L1 + L2 (A0) | fail-fast + `adminBootstrap.test.ts` |

---

## 11. 测试优先级 / 缺失扫描检查表 (新增 2026-04-21)

Session 5 最后必须跑一次该检查表, 任何 ❌ 阻塞 MVP 发布.

### 11.1 P0 必须 (红线, 缺失即不 launch)

- [ ] Harness 38 条规则全绿 (`npm run ci:harness`)
- [ ] 7 条数据契约全绿 (`npm run ci:data`)
- [ ] 5 份 `__ci_fixtures__/` 自种违规全红 (`npm run ci:harness:selftest`)
- [ ] 6 条 E2E 关键链路全绿 (注册 / Onboarding / 登出 / Brand 总览查看 / CSV 导出 / MCP 调用)
- [ ] 40+ 视觉 baseline 已就位, diff < 100px 阈值
- [ ] §9.1-§9.6 异常场景矩阵每行至少 1 个测试引用且 CI 跑通
- [ ] §10.1 Admin 表格每 Admin Session 至少 L1+L2+L3 覆盖 (L4 可延后 MVP+1)
- [ ] OpenAPI 契约从 `openapi.yaml` 自动生成, 未手写 `.d.ts`
- [ ] HAR fixture 脱敏 Harness 过绿 (Session 1 F 组新增)
- [ ] Mixpanel PII 红线 (D3) 覆盖所有 track() 出口

### 11.2 P1 应该 (缺 1 条发布但 72h 内补齐)

- [ ] 国际化覆盖矩阵 zh-CN / en-US 双语成对 (A2) 无缺键
- [ ] Brand Mode 6 分析页密度契约 (C14-1..3) 全绿
- [ ] Onboarding 草稿过期清理定时任务有单测
- [ ] 成本突增告警 (§9.5) 端到端链路跑通一次
- [ ] Admin Trust Score 幻觉检测单测 (A3) ≥ 5 case

### 11.3 P2 可延后 (MVP+1 补)

- [ ] Phase 4 CI 自愈 (Claude Code Action)
- [ ] Mutation testing (Stryker) 试跑
- [ ] MCP Token revocation 广播的灰度测试
- [ ] Admin Visual baseline 全覆盖 (当前仅关键页面)

### 11.4 缺失检测脚本 `scripts/coverage-gap-scan.mjs`

Session 5 产出, 扫 3 件事:

1. 本文档 §9 每行是否至少一个测试文件引用 (grep `testFile.test.ts` 反查)
2. `scripts/ci-check.mjs` 实际 register 规则数是否 ≥ 本文档 §2.1 声明数
3. `openapi.yaml` 每端点是否至少 1 条契约测试

跑法: `node scripts/coverage-gap-scan.mjs` → exit 1 if any gap. CI 里 `npm run ci` 末尾追加此步.

---

## 12. 数据契约 fixture 命名规范 (新增 2026-04-21)

### 12.1 `frontend/src/data/fixtures/` 状态 fixture

- 文件名: `{STATE}_FIXTURES.js`, export 命名对象, 禁 default export
- 每份 fixture 必须标注 `@pairs-to` 指向 §9 异常矩阵行号, 例: `// @pairs-to §9.4 BRAND_ZERO_MENTIONS`
- Session 4b Visual baseline 必须消费至少 6 份空态 fixture (覆盖 §9.4 全表)

### 12.2 `tests/fixtures/adapters/` HAR fixture

- 目录结构 `{engine}/{scenario-slug}.har` (slug 用 kebab-case, 最多 4 词)
- 配 `{engine}/{scenario-slug}.expected.json` 声明期望解析结果 (`ScrapingResult` 或 `ScrapingError`)
- 录制脚本 `scripts/record-har.ts` 必须自动脱敏 `Authorization / Cookie / Set-Cookie / x-real-ip / x-forwarded-for / refresh_token / bearer`
- CI 新增 harness (Session 1 F 组):
  - F1 `har-no-auth-leak` · 扫 `tests/fixtures/**/*.har` 确保无 `"Authorization": "Bearer `
  - F2 `har-no-cookie-leak` · 同上扫 Cookie/Set-Cookie
  - F3 `har-no-ip-leak` · 扫 `x-real-ip|x-forwarded-for` (仅允许 `0.0.0.0` 占位)

### 12.3 `tests/fixtures/contract/` 契约 fixture

- OpenAPI 驱动: `{endpoint-slug}.request.json` + `{endpoint-slug}.response.json` + `{endpoint-slug}.error-{code}.json`
- Session 3 自动生成, 基于 `openapi.yaml` 的 schema example 字段

---

## 13. 规则历史 & 触发起源 (新增 2026-04-21)

> **为什么**: 一条 Harness 规则诞生必有其 Bug, 否则它不该存在. 下线规则时要能看见"它拦住过什么", 再决定是否真的安全下线.

| 规则 | 起源 | 链接 / 备注 |
|---|---|---|
| C1 Sparkline 100% 默认 | 2026-04-17 Sparkline 给数字像素导致父 flex 容器塌陷 | review/chart-bug-report.md (若缺建空) |
| C4 sentiment toFixed(2) | 2026-04-17 Frank 看到 "0.82" 误以为置信度 | 同上 |
| C5 sparkline 锯齿模数 | 2026-04-17 i % N === 0 ? ±V : 0 生成的波形太像假数据 | 同上 |
| C7 BRANDS ranking | 2026-04-17 mock BRANDS ranking 与 panoScore 不一致; **2026-04-21 Review 再次发现 [1,2,3,5,7,8,4,6] 违规, Session 0 强制修** | REVIEW_2026_04_21.md §5 |
| C9-1..2 Heatmap token 边界 | 2026-04-20 Wave-4 Frank 指出色带语义被 chart token 借用 | — |
| C10-1..2 Filter Bar mount | 2026-04-20 Frank 9 问第 1/4 点 (跨 sub-view 状态丢失) | — |
| C11-1 mentionRate 小数域 | 2026-04-20 1620% bug | — |
| C12-1..2 Donut 强制 | 2026-04-20 Frank 嫌 text-3xl 三个百分比死板 | — |
| C13-1..3 Quadrant sqrt/showLabels | 2026-04-20 气泡霸屏 400px | — |
| C14-1..3 密度 | 2026-04-20 分析页太松散 | — |
| C15-1..3 brandId from query | **2026-04-20 Wave-4 真正固化点**: 点产品进详情页看 "暂无数据" | DECISIONS §20 |
| A6 i18n interpolation API | 2026-04-20 `{brand} · 共 {count} 款产品` literal 泄漏 | — |
| D1 Auth gate | 2026-04-20 决策 #9 反转 | — |
| D2 logout 6 步 | 2026-04-17 §4.1.1e I | — |
| D3 Mixpanel PII | 2026-04-16 §4.11.5 红线 | — |
| D4-D5 301 redirect | 2026-04-20 IA v2 11 个 legacy 301 | — |
| D6 匿名 API ban | 2026-04-20 决策 #9 | — |
| D7 Onboarding draft route guard | 2026-04-20 决策 #10 | — |
| E1 Citation Tier 不硬编码 | 2026-04-17 §4.2.6 决策 #19 | — |
| E2 tldts | 2026-04-17 同上 | — |
| E3 Alert 互斥 | 2026-04-17 同上 | — |
| E4 pr_score 不硬编码 | **2026-04-21 Review 新增 (预防性)** | REVIEW_2026_04_21.md |

每次 Session 新增 Harness 规则必须 append 一行到本表.

---

**文档版本记录**:
- v1.0 (2026-04-17 Frank + Claude): 初版. 定义 L1-L4 分层 + A++ 四支柱 + 按 Session 时间线.
- **v1.1 (2026-04-21 Review pass)**: 规则总数 30 → 38 明确 (A-E 五组); §2.1 表格按组重写; 新增 §9 异常覆盖矩阵 (6 大类) + §10 Admin 测试矩阵 (含新 A5) + §11 测试优先级检查表 + §12 fixture 命名规范 + §13 规则历史表. 删旧 §5 时间线表的 Session 时数估算行, 改放 `docs/CLAUDE_CODE_SESSIONS.md`.
