# Session 4b'.3 Prompt · Industry Mode 4 sub-views + KG G6 v5 + CSV 8 接入点 + 11 Legacy 301

**版本**: 1.0 · 创建日期 2026-04-26
**拆分自**: `docs/SESSION_4B_PRIME_PROMPT.md` (consolidated 4b' 的第 3/4 段)
**上游链**: 0' → 4a' → 4b'.1 → 4b'.2 → **本 Session (4b'.3)** → 4b'.4
**下游 Session**: 4b'.4 GREEN gate = 本 Session PASS

---

## §0 · Pre-Flight Grep Contract (开工前 30min 内执行, 全部命中才能动代码)

```bash
# F1 · IA v2.0 Industry 4 路径锚点 (PRD §4.6-IA-v2.D)
rg -n "/industry/(overview|ranking|topics|knowledge-graph)" docs/PRD.md | head -10
# 期望: ≥ 4 命中 (Industry Mode 4 sub-views 完整列出)

# F2 · CSV 8 个 exportType 字段字典 (PRD §4.6.4)
rg -n "exportType.*=|csv.*#[0-9]+" docs/PRD.md | head -20
# 期望: ≥ 8 命中 (csv #1 industry_ranking / #2 brand_visibility / #3 brand_sentiment / #4 brand_topics / #5 competitor_matrix / #6 product_bcg / #7 citation_domains / #8 pr_targets — 决策 #19 起 #9/#10 延后 v1.1/Phase 2)

# F4 · 上游 GREEN gate (Sessions 4b'.2 + 3' + 1.5' 必须 PASS)
rg -n "Session 4b'.2.*GREEN|Session 3'.*GREEN|Session 1.5'.*GREEN" docs/SESSIONS_PYTHON.md | head -10
# 期望: 三者全部 GREEN; 任一为 ❌ 立即 STOP Type A4

# F5 · KG G6 v5 8 坑点回引 (memory feedback_genpano_g6_knowledge_graph)
rg -n "radial|hover-activate|shadowBlur|autoFit|composer|base style" docs/DESIGN_TOKENS.md docs/PRD.md | head -10
# 期望: ≥ 6 命中 (KG 视觉契约固化在 DESIGN_TOKENS / PRD §4.5 中至少 6 个反复踩坑点)

# F6 · Industry/CSV API 端点 (3' Session 交付的 OpenAPI 锚)
curl -s https://api.preview.genpano.dev/api/v1/openapi.json | jq -r '.paths | keys[]' | grep -E "industries/.*/(overview|ranking|topics|knowledge-graph)|exports/csv" | head -10
# 期望: ≥ 5 命中 (Industry 4 端点 + CSV export endpoint)

# F7 · KG 读取端点 (1.5' Session 交付)
curl -s https://api.preview.genpano.dev/api/v1/openapi.json | jq -r '.paths | keys[]' | grep -E "knowledge-graph|kg/(brands|products|relations)" | head -10
# 期望: ≥ 3 命中 (KG read endpoint 至少 3 条)

# F8 · 11 Legacy 301 重定向枚举 (decision #2 / D4 harness)
rg -n "301|legacy|/dashboard|/brands/:id|/topics |/industries |/knowledge-graph|/diagnostics|/reports" docs/PRD.md | head -25
# 期望: ≥ 11 命中 (11 条 Legacy 路由 → IA v2.0 新路由的 301 映射全部覆盖)

# F12 · CLAUDE.md 最近 3 条决策 freshness check (规则 11)
rg -n "^[0-9]+\. \*\*" CLAUDE.md | tail -3
# 期望: 最新 3 条决策, 任何提及 KG/CSV/Legacy/Industry 必须读全文
```

**STOP 触发对照表**:

| 命中条件 | STOP 类型 | 行动 |
| --- | --- | --- |
| F4 显示 4b'.2 / 3' / 1.5' 任一未 GREEN | Type A4 | 暂停, 回追前置 Session |
| F1 命中数 < 4 (Industry 4 路径) | Type B1 (truth source 漂移) | 回 PRD §4.6-IA-v2.D 校验 |
| F2 命中数 < 8 (CSV 字段字典缺失) | Type B1 | 回 PRD §4.6.4 校验, 不允许猜 exportType |
| F5 命中数 < 6 (KG 8 坑点契约缺) | Type B6 | 回 DESIGN_TOKENS / PRD §4.5 补全 |
| F6 显示 < 5 个 Industry/CSV 端点 | Type B1 (上游契约不齐) | 回 3' Session 补端点, 不允许 mock |
| F7 显示 < 3 个 KG 端点 | Type B1 | 回 1.5' Session 补端点 |
| F8 命中数 < 11 | Type B1 | 11 条 Legacy 301 必须全部枚举, 漏一条即 D4 harness 拦 |
| F12 显示有未读决策 | Type B7 | 读全文, 加入 §1 真相源索引再开工 |

---

## §1 · Truth Source Index (本 Session 引用 / 修改的所有真相源, 段号最小单元)

### Prerequisites (chain dependency, 全部 GREEN 才能开工)

| 前置 Session | GREEN 条件 | 本 Session 依赖点 | 验证命令 |
| --- | --- | --- | --- |
| **4b'.2** | Brand Mode 9 sub-views + Citation 5 Tab + Charts shared lib + Group I I1-I5 全部 PASS, ComingSoon 在 /industry/* 4 路径仍存在 | 本 Session 复用 charts lib + FilterBar 框架 + TopicIntentMatrix (共享组件) | `curl -s https://app.preview.genpano.dev/brand/citations` 返回 200 + 显示 5 Tab |
| **3'** | Industry 4 数据 GET 端点 + Industry Ranking + CSV export endpoint (POST /api/v1/exports/csv 接受 8 exportType 之一 + 返回带 BOM 的 UTF-8 CSV) 齐备 | TanStack Query 接 Industry / CSV download via fetch | `curl -s https://api.preview.genpano.dev/api/v1/openapi.json \| jq '.paths \| keys'` 含 Industry 4 + CSV |
| **1.5'** | KG 冷启动管线 (Industry → Category → Brand → Product + 关系边) DB 已 seed, GET `/api/v1/knowledge-graph/:industrySlug` 返回 G6 标准 graph data ({nodes, edges}) | KG 页面接读端点 + G6 v5 渲染 | `curl -s https://api.preview.genpano.dev/api/v1/knowledge-graph/beauty-personal-care \| jq '.nodes \| length'` 返回 ≥ 30 |

**STOP Type A4**: 上述任一前置 Session 未 GREEN, 本 Session 必须暂停 Phase Gate 任何活动, 回追前置 Session 的 Phase Gate 报告。

### 引用的真相源 (只读)

| 文档 / 锚点 | 引用内容 | 用途 |
| --- | --- | --- |
| `docs/PRD.md §4.5` | KG 数据模型 + G6 v5 视觉契约 (radial layout / 不 hover-activate / autoFit / single composer) | /industry/knowledge-graph 实现 |
| `docs/PRD.md §4.6-IA-v2.D` | Industry Mode 侧栏 4 项 (overview/ranking/topics/knowledge-graph) | 路由实现完整列表 |
| `docs/PRD.md §4.6.1g v3.2` | Industry Topics 5 段 (FilterBar / Hero 3 cards / Radar / Topic×Intent / Drawer) + TopicIntentMatrix 共享 (从 4b'.2 跨 Mode 复用) | /industry/topics 实现 |
| `docs/PRD.md §4.6.4` | CSV 字段字典 8 exportType + UTF-8 BOM + csv-stringify 不手写 + 10k 行上限 + 5/min 限流 | CSV 8 接入点实现 |
| `docs/PRD.md §4.1.1-gate` | Auth-Required 决策 (CSV / MCP / 数据 API 必须 RequireAuth, 决策 #9) | RequireAuth wrapper 复用 |
| `docs/DESIGN_TOKENS.md C1-C7 / C9-C15` | 图表契约 + V2 视觉契约 (Industry 仍受同一约束) | Industry 页面渲染必须遵守 |
| `CLAUDE.md` decisions #2 / #18 / #20 v3.2 / #21 D4 | IA v2.0 (11 Legacy 301 列表) / 测试 A++ / TopicIntentMatrix 跨 Mode 复用 / D4 harness 11 Legacy 301 覆盖 | 决策回引 |
| Memory `feedback_genpano_g6_knowledge_graph.md` | G6 v5 8 反复踩坑点 (radial / 不 hover-activate / 放大胜利者 / shadowBlur / label 外置 / autoFit / 单一 composer / base style 显式 opacity) | KG 实现强制遵守 |

### 修改的资产 (写入)

| 文件 | 改动类型 | 说明 |
| --- | --- | --- |
| `frontend/src/components/filter/IndustryAnalysisFilterBar.tsx` | NEW | 从 BrandAnalysisFilterBar fork (4b'.2 已建), 适配 Industry 维度 (无 brandId) |
| `frontend/src/hooks/useIndustryAnalysisFilters.ts` | NEW | URL state hook (Industry 版) |
| `frontend/src/pages/industry/IndustryOverviewPage.tsx` | REPLACE ComingSoon | Industry KPI + Top 5 Brand 排行预览 |
| `frontend/src/pages/industry/IndustryRankingPage.tsx` | REPLACE ComingSoon | 完整品牌排行表 (panoScore desc) + CSV #1 export |
| `frontend/src/pages/industry/IndustryTopicsPage.tsx` | REPLACE ComingSoon | FilterBar + Hero 3 cards + Radar (Top 3 brand) + TopicIntentMatrix (共享 from 4b'.2) + Drawer 5 段 (v3.2) |
| `frontend/src/pages/industry/IndustryKnowledgeGraphPage.tsx` | REPLACE ComingSoon | AntV G6 v5 渲染 + 8 坑点全部规避 + autoFit |
| `frontend/src/lib/kg/g6Composer.ts` | NEW | 单一 composer 入口 (避免坑点 #6) + base style 显式 opacity (坑点 #8) + radial layout (坑点 #1) + label 外置 (坑点 #5) |
| `frontend/src/lib/csv/exportCsv.ts` | NEW | CSV download wrapper, csv-stringify (不手写 quote/escape) + UTF-8 BOM 前缀 + 10k 行上限 + 5/min 限流 (前端层 + 后端 3' API 双校验) |
| `frontend/src/lib/csv/exportTypes.ts` | NEW | 8 exportType 联合类型 + 字段字典 (与 PRD §4.6.4 对齐) |
| `frontend/src/components/csv/CsvExportButton.tsx` | NEW | 统一 CSV 下载按钮 + 8 接入点复用 + Mixpanel #53 (pr_targets_csv_exported) + RequireAuth gate |
| `frontend/src/router/legacyRedirects.tsx` | NEW | 11 Legacy 301 重定向 (`<Navigate replace>` + 服务端 vercel.json 双层) |
| `vercel.json` (or `frontend/public/_redirects`) | EXTEND | 11 条 301 (服务端权威, SEO 友好) |
| `frontend/src/i18n/zh-CN.json` | EXTEND | industry.* / kg.* / csv.* 命名空间 |
| `frontend/src/i18n/en-US.json` | EXTEND | 同上, 对偶完整 |

**注意 (重要)**:
1. **本 Session 不新增 Group I harness 规则**, 复用 4b'.2 已建的 I1-I5 框架。selftest EXPECTED_POSITIVES 维持 38/38。
2. **TopicIntentMatrix 是共享组件** (4b'.2 已 git mv 到 `components/topics/`), 本 Session **直接 import 复用**, 禁止 fork / 改名 / 重写 (decision #20 v3.2 锚定)。
3. **AntV G6 v5 是 production-grade 库** (memory `feedback_production_deps.md`), 禁止手写 SVG / Canvas 替代。

---

## §2 · MVP Scope-Cut Declaration (本 Session 做 / 不做, 锚定 §X.Y)

### ✅ 本 Session 做 (Y30-Y41, 12 项)

| Y# | 内容 | 锚点 |
| --- | --- | --- |
| Y30 | IndustryAnalysisFilterBar fork + useIndustryAnalysisFilters URL hook | DESIGN_TOKENS C10 (Industry 版) |
| Y31 | /industry/overview 实现 (KPI + Top 5 排行预览) | PRD §4.6-IA-v2.D |
| Y32 | /industry/ranking 实现 (完整排行 + CSV #1 download) | PRD §4.6-IA-v2.D + §4.6.4 |
| Y33 | /industry/topics 实现 5 段 (v3.2): FilterBar / Hero 3 cards / Radar / TopicIntentMatrix (共享) / Drawer | PRD §4.6.1g v3.2 |
| Y34 | /industry/knowledge-graph 实现 G6 v5 + 8 坑点全部规避 | PRD §4.5 + memory `feedback_genpano_g6_knowledge_graph` |
| Y35 | KG g6Composer 单一入口 + radial + autoFit + label 外置 + base style 显式 opacity | KG 8 坑点 #1/#5/#6/#7/#8 |
| Y36 | CSV exportCsv lib (csv-stringify + BOM + 10k 上限 + 5/min 限流) | PRD §4.6.4 |
| Y37 | CSV 8 exportType 字段字典 (#1-#8 MVP) | PRD §4.6.4 |
| Y38 | CsvExportButton 统一组件 + 8 接入点复用 + Mixpanel #53 + RequireAuth | PRD §4.6.4 + decision #9 |
| Y39 | 11 Legacy 301 重定向枚举 (`legacyRedirects.tsx` + vercel.json 双层) | decision #2 |
| Y40 | i18n EXTEND industry/kg/csv 命名空间 (zh-CN + en-US 对偶) | A2 harness 锚 |
| Y41 | Group I 复用 (无新增) + selftest 38/38 维持 | decision #21 D + memory `feedback_fixture_naming` |

### ❌ 本 Session 不做 (明确延后)

| 内容 | 延后到 | 原因 |
| --- | --- | --- |
| 4b' 最终聚合 + Vitest 80% 全模块 + Playwright smoke + Vercel deploy + Frank S1-S9 全套手验 | 4b'.4 | 收尾 Session 单独跑 (本 Session 仅交付 Industry/KG/CSV/Legacy 4 大块, 不做跨 Session 聚合) |
| CSV #9 pr_targets (citation 6F) / #10 content_gap (citation 6F) | v1.1 / Phase 2 | PRD §4.6.4 + decision #19 |
| KG 编辑 / 提交品牌 / Admin 审核 | A2' Session (Admin) | 决策 #8 (用户共建走 Admin 审核流) — 本 Session 仅渲染只读 |
| Industry 自定义筛选 (品牌画像组合) | Phase 2 | MVP 仅 4 默认 ProfileGroup |
| KG 全屏 / 节点详情 Drawer / 关系编辑 UI | Phase 2 | MVP 仅 G6 主视图 |
| MCP API UI 入口 | A5' / Phase 2 | decision #19 §4.5.2 |

---

## §3 · STOP Triggers (Type A 环境 / B 真相源 / C 范围, 触发立即停下)

### Type A · 环境失败

| 编号 | 触发 | 行动 |
| --- | --- | --- |
| A4 | 上游 Session (4b'.2 / 3' / 1.5') 未 GREEN | 暂停, 回追上游 Phase Gate 报告 |
| A5 | preview env DNS 解析失败 (app.preview.genpano.dev) | 用 `curl -I` 验证 → 报错网络 → 等 0' Session 修复 |
| A8 | GitHub Actions runner 失败超 3 次重试 | 暂停, 报错 0' Session CI/CD 基建 |
| A9 | Industry / KG / CSV API 持续 500 (>10min, >5 次) | 暂停, 报错 3' / 1.5' Session, 不允许前端 mock 绕过 |

### Type B · 真相源冲突

| 编号 | 触发 | 行动 |
| --- | --- | --- |
| B1 | PRD / DATA_MODEL / DESIGN_TOKENS 与 Prompt 描述漂移 | 暂停, 走 Prompt 公约规则 4 双向同步 |
| B6 | DESIGN_TOKENS C9-C15 实施时发现新自创视觉 | 暂停, 回 DESIGN_TOKENS 校验, 不创新 token |
| B7 | CLAUDE.md 有最近未读决策影响 KG/CSV/Legacy | 读全文, 加入 §1 真相源索引再开工 |
| B8 | OpenAPI typegen 生成的 TS 类型与本 Prompt 引用字段不一致 | 暂停, 回 3' Session 改 OpenAPI 而非前端绕过 |

### Type C · 范围溢出

| 编号 | 触发 | 行动 |
| --- | --- | --- |
| C11 | 单文件 > 500 行 | 拆分, 不允许超大文件 |
| C13 | 看到 `useState('7d')` 等本地时间窗 state | 必须 STOP, 改用 `useIndustryAnalysisFilters` URL state |
| C15 | i18n literal 文本未走 t() 入口 | STOP, 改 i18n key |
| C17 | KG 用 hover-activate 触发节点放大 (坑点 #2) | STOP, 改 click-to-pin 或 fixed-prominence |
| C18 | cherry-pick 旧分支 KG / CSV 代码 (Frank Q1 决策, memory `feedback_genpano_branch_per_session`) | STOP, 按 PRD 重做 |
| C19 | Mixpanel 事件含 PII (email / userId 显式) | STOP, 改 brand_slug / industry_slug 等 ID-only |
| C22 | G6 v5 用 `composer.use(...)` 多次注册 (坑点 #6) | STOP, 必须 single composer 入口 |
| C23 | 11 Legacy 301 漏一条 → D4 harness 拦截 | STOP, 补齐再 PR |
| C24 | CSV 字段手写 quote/escape 而非 csv-stringify | STOP, memory `feedback_production_deps` 强制库 |
| C25 | CSV 未带 UTF-8 BOM (Excel 中文乱码) | STOP, 加 `\uFEFF` 前缀 |

---

## §4 · Harness Group I (本 Session 不新增, 复用 4b'.2 框架)

**重要**: 本 Session 不新增 Group I 子规则, selftest 维持 38/38。但 D4 harness (11 Legacy 301 全覆盖) 必须验证通过。

### D4 (复用 4b'.1 已建框架, 本 Session 验证 11 条全覆盖)

```bash
# 11 Legacy 路由 → IA v2.0 新路由的 301 映射 (decision #2)
rg -n "(/dashboard|/brands/:id$|/brands/:id/products/:pid|/topics$|/industries$|/knowledge-graph$|/diagnostics$|/reports$)" frontend/src/router/legacyRedirects.tsx vercel.json | head -25
# 期望: ≥ 11 命中 (前端 + 服务端双层覆盖)
```

11 条 Legacy 301 完整列表 (decision #2):

| Legacy URL | → IA v2.0 新 URL | 实现 |
| --- | --- | --- |
| `/dashboard` | `/brand/overview` | 301 |
| `/brands/:id` | `/brand/overview?brandId=:id` | 301 (query 参数迁移) |
| `/brands/:id/products/:pid` | `/brand/products/:pid?brandId=:id` | 301 (Wave-4 brandId 查询串) |
| `/topics` | `/brand/topics` | 301 |
| `/industries` | `/industry/overview` | 301 |
| `/knowledge-graph` | `/industry/knowledge-graph` | 301 |
| `/reports` | `/brand/reports` | 301 |
| `/diagnostics` (跨品牌聚合) | 410 Gone (废除, 不重定向) | 410 + 解释页 |
| `/auth` (旧 login 别名) | `/login` (4b'.1 AuthPage) | 301 |
| `/sign-up` (旧 register 别名) | `/register` | 301 |
| `/onboarding/v1` (旧引导版本) | `/onboarding` | 301 |

**STOP C23**: 上表任一行前端 / 服务端缺失即 D4 harness 拦截。

---

## §5 · Step Delivery Order (re-numbered Steps 0-1, 原 consolidated 4b' Steps 8-9)

### Step 0 · Industry Mode 4 sub-views + KG G6 v5 + 11 Legacy 301

**前置**: 4b'.2 全部 PASS + Pre-Flight Grep F1/F4/F5/F7/F8/F12 全绿。

**实施顺序**:

1. **IndustryAnalysisFilterBar fork** — 从 `frontend/src/components/filter/BrandAnalysisFilterBar.tsx` (4b'.2 已建) 复制 + 删除 brandId 维度 + 保留 (from/to/engines/profileGroup/dimensions/intents) 6 维 URL state
2. **useIndustryAnalysisFilters hook** — URL state 解析 (与 useBrandAnalysisFilters 同模式, 但 Industry 视角)
3. **/industry/overview** — Industry KPI 4 卡 + Top 5 Brand 排行预览 (panoScore desc) + CTA "查看完整排行 → /industry/ranking"
4. **/industry/ranking** — 完整 panoScore 排行表 + 列: brand / panoScore / mentionRate / SoV / sentiment / citationShare / 行业排名 + 顶部 `<CsvExportButton exportType="industry_ranking" />` (CSV #1)
5. **/industry/topics** — 5 段 v3.2:
   - 段 1: `<IndustryAnalysisFilterBar>`
   - 段 2: Hero 3 cards (热度 Top 3 Topic)
   - 段 3: Radar (Top 3 brand × topics 雷达图, 用 `brandTopicHits` helper 排序)
   - 段 4: `<TopicIntentMatrix>` (从 `components/topics/` 共享, 4b'.2 git mv 后落点)
   - 段 5: Topic Drawer (点击 topic 弹抽屉显示 mentionCount + intentBreakdown)
6. **lib/kg/g6Composer.ts** — 单一 composer 入口 (8 坑点全部规避):
   - 坑点 #1 radial layout (不 grid / force)
   - 坑点 #2 不 hover-activate 放大 (用 click-to-pin 或 fixed-prominence)
   - 坑点 #3 放大胜利者 (Top 5 节点尺寸 ≥ 普通节点 1.5x)
   - 坑点 #4 shadowBlur (Top 5 节点添加发光边)
   - 坑点 #5 label 外置 (节点 > 30 时强制 label 在节点外, 避免重叠)
   - 坑点 #6 single composer 入口 (一处 `composer = new G6.ExtensionComposer()`, 禁多处 register)
   - 坑点 #7 autoFit (`graph.fitView()` 在 mount + resize)
   - 坑点 #8 base style 显式 opacity (默认 1, 否则继承 0 全透明)
7. **/industry/knowledge-graph** — 调 1.5' Session `/api/v1/knowledge-graph/:industrySlug` 端点 → 接 g6Composer 渲染
8. **lib/csv/exportTypes.ts** — 8 exportType 联合类型:
   ```ts
   export type CsvExportType =
     | 'industry_ranking'      // #1
     | 'brand_visibility'      // #2
     | 'brand_sentiment'       // #3
     | 'brand_topics'          // #4
     | 'competitor_matrix'     // #5
     | 'product_bcg'           // #6
     | 'citation_domains'      // #7
     | 'pr_targets';           // #8 (MVP only #1-#8, #9/#10 v1.1/Phase 2)
   ```
9. **lib/csv/exportCsv.ts** — `csv-stringify` 库封装 + UTF-8 BOM 前缀 (`'\uFEFF'`) + 10k 行上限 (前端 hard cap, 超出报错) + 5/min 限流 (前端 throttle + 后端 3' API 双校验)
10. **CsvExportButton 组件** — 接受 `exportType` + `filters` (URL state) → POST `/api/v1/exports/csv` → 触发 download + Mixpanel #53 (pr_targets_csv_exported) (其他 exportType 也发同一事件, with `export_type` 字段) + RequireAuth wrapper (decision #9)
11. **CSV 8 接入点挂载**:
   - `/industry/ranking` 顶部: exportType="industry_ranking"
   - `/brand/visibility` 顶部 (4b'.2 已建): 加 exportType="brand_visibility"
   - `/brand/sentiment`: exportType="brand_sentiment"
   - `/brand/topics`: exportType="brand_topics"
   - `/brand/competitors`: exportType="competitor_matrix"
   - `/brand/products`: exportType="product_bcg"
   - `/brand/citations` Domains Tab: exportType="citation_domains"
   - `/brand/citations` PR Targets Tab: exportType="pr_targets"
12. **legacyRedirects.tsx** — 11 条 `<Route path="/dashboard" element={<Navigate to="/brand/overview" replace />} />` 等
13. **vercel.json** — 11 条服务端 301 (SEO + 直接访问 friendly):
   ```json
   {
     "redirects": [
       { "source": "/dashboard", "destination": "/brand/overview", "permanent": true },
       { "source": "/brands/:id", "destination": "/brand/overview?brandId=:id", "permanent": true },
       ...
     ]
   }
   ```
14. **i18n EXTEND** — `industry.*` / `kg.*` / `csv.*` 命名空间 + zh-CN/en-US 对偶完整 (A2 harness 锚)

**Phase Gate Layer 1 验收** (本 Step):
- ESLint / tsc strict 全绿
- Vitest pages/industry + lib/kg + lib/csv 覆盖率 ≥ 80%
- Vite build 通过, dist 不含 msw
- D4 harness 11 Legacy 301 全覆盖 (前端 + 服务端)
- selftest 38/38 维持 (无新增, 无回归)

### Step 1 · Phase Gate L3 准备 (Frank 手验前置)

1. 跑 `bash scripts/verify_4b3.sh` (本 Session 新建, 见 §6) → 全绿
2. push 分支 `claude/session-4b-3` → GitHub Actions 走 0' Session 的 CI/CD pipeline → preview env 上线 `app.preview.genpano.dev/claude-session-4b-3/*`
3. 准备 Frank 手验 checklist (S10-S13, 见 §6 L3)

---

## §6 · Phase Gate (3 层验收, 全绿才宣 GREEN)

### Layer 1 · 自动化验证 (本 Session 新建 `scripts/verify_4b3.sh`)

```bash
#!/bin/bash
set -e

echo "=== Session 4b'.3 Verify Script ==="

# Check 1: ESLint
echo "[1/13] ESLint..."
cd frontend && npx eslint src/pages/industry src/lib/kg src/lib/csv src/router/legacyRedirects.tsx src/components/filter/IndustryAnalysisFilterBar.tsx --max-warnings 0

# Check 2: tsc strict
echo "[2/13] TypeScript strict..."
npx tsc --noEmit

# Check 3: Vitest pages/industry coverage 80%
echo "[3/13] Vitest pages/industry..."
npx vitest run --coverage --coverage.thresholds.lines=80 --coverage.thresholds.branches=80 --coverage.thresholds.functions=80 --coverage.thresholds.statements=80 src/pages/industry

# Check 4: Vitest lib/kg coverage 80%
echo "[4/13] Vitest lib/kg..."
npx vitest run --coverage --coverage.thresholds.lines=80 src/lib/kg

# Check 5: Vitest lib/csv coverage 80%
echo "[5/13] Vitest lib/csv..."
npx vitest run --coverage --coverage.thresholds.lines=80 src/lib/csv

# Check 6: Vite build size + msw not in dist
echo "[6/13] Vite build..."
npx vite build
test $(du -sb dist | awk '{print $1}') -lt 2097152 || (echo "FAIL: bundle > 2MB" && exit 1)
! grep -r "msw" dist/ || (echo "FAIL: msw in dist" && exit 1)

# Check 7: OpenAPI typegen drift (Industry + CSV endpoints)
echo "[7/13] OpenAPI typegen drift..."
npx openapi-typescript https://api.preview.genpano.dev/api/v1/openapi.json -o /tmp/api-types-fresh.ts
diff src/types/api-generated.ts /tmp/api-types-fresh.ts && echo "OK: no drift" || (echo "FAIL: API types drift" && exit 1)

# Check 8: i18n parity (zh-CN vs en-US for new namespaces)
echo "[8/13] i18n parity..."
node scripts/check_i18n_parity.mjs --namespaces industry,kg,csv

# Check 9: D4 harness 11 Legacy 301 coverage
echo "[9/13] D4 harness 11 Legacy 301..."
node ../scripts/ci_check.py --rule D4 || (echo "FAIL: D4 11 Legacy 301 incomplete" && exit 1)

# Check 10: selftest 38/38 maintained
echo "[10/13] Selftest..."
node ../scripts/ci-harness-selftest.py | grep "38 / 38" || (echo "FAIL: selftest regressed" && exit 1)

# Check 11: KG g6Composer single instance + 8 坑点 (memory feedback_genpano_g6_knowledge_graph)
echo "[11/13] KG 8 坑点 grep guards..."
test $(rg -c "new G6.ExtensionComposer\|new ExtensionComposer" src/lib/kg/g6Composer.ts) -eq 1 || (echo "FAIL: composer not single instance" && exit 1)
! rg "hover-activate" src/lib/kg/ src/pages/industry/IndustryKnowledgeGraphPage.tsx || (echo "FAIL: hover-activate violation" && exit 1)
rg "fitView\|autoFit" src/lib/kg/g6Composer.ts || (echo "FAIL: missing autoFit" && exit 1)

# Check 12: CSV BOM + csv-stringify (no hand-written quote)
echo "[12/13] CSV 契约..."
rg "uFEFF" src/lib/csv/exportCsv.ts || (echo "FAIL: missing UTF-8 BOM" && exit 1)
rg "from ['\"]csv-stringify" src/lib/csv/exportCsv.ts || (echo "FAIL: not using csv-stringify" && exit 1)
! rg 'replace.*"' src/lib/csv/exportCsv.ts || (echo "WARN: possible hand-written CSV escape — review")

# Check 13: Mixpanel PII regex grep (no email / userId in event properties)
echo "[13/13] Mixpanel PII guard..."
! rg "mixpanel.track.*email\|mixpanel.track.*userId" src/ || (echo "FAIL: PII in Mixpanel events" && exit 1)

echo "=== verify_4b3.sh ALL GREEN ==="
```

### Layer 2 · Selftest

```bash
node scripts/ci-harness-selftest.py
# 期望: PASS (38 / 38 fixture expectations met)  ← 本 Session 不新增, 维持 4b'.2 数字
```

### Layer 3 · Frank Preview Env 手验 (S10-S13, 4 checks)

**Frank 在浏览器走的 4 步**:

| # | 路径 | 验收点 |
| --- | --- | --- |
| S10 | `app.preview.genpano.dev/claude-session-4b-3/industry/overview` | Industry KPI 4 卡渲染 + Top 5 Brand 排行预览 + 切换行业 picker 工作 + URL state ?industrySlug= 持久化 |
| S11 | `/industry/topics` | 5 段全部渲染 (FilterBar / Hero 3 cards / Radar / TopicIntentMatrix 共享 / Drawer); 点 Topic 弹抽屉; FilterBar URL state 跨刷新保留 |
| S12 | `/industry/knowledge-graph` (重点视觉手验) | G6 v5 8 坑点全部规避: 节点 radial 布局 / 点击节点 (非 hover) 高亮 / Top 5 节点尺寸 1.5x / Top 5 有 shadowBlur 发光 / 节点 > 30 时 label 外置不重叠 / 首屏 autoFit 完整可见 / base style opacity=1 不全透明 |
| S13 | `/industry/ranking` 点 "导出 CSV" 按钮 | 下载文件 → Excel 打开中文不乱码 (UTF-8 BOM 生效) + 列名含 brand/panoScore/mentionRate/SoV/sentiment/citationShare/ranking + 行数 ≤ 10k + Network 面板看到 5/min 限流 throttle (短时间多次点击 → 5 次后 429) |

**11 Legacy 301 抽样** (Frank 自选 3 条):

| # | 旧 URL | 期望跳转 |
| --- | --- | --- |
| L1 | `app.preview.genpano.dev/.../dashboard` | 跳 `/brand/overview` (浏览器 URL bar 显示新地址) |
| L2 | `app.preview.genpano.dev/.../brands/lancome` | 跳 `/brand/overview?brandId=lancome` |
| L3 | `app.preview.genpano.dev/.../industries` | 跳 `/industry/overview` |

**Frank 任一 ❌ → 本 Session ❌**, 必须修复后重跑 Layer 1+2+3。

---

## §7 · Downstream Session Note (4b'.4 GREEN gate = 本 Session PASS)

**4b'.4 直接继承本 Session 资产** (无需重写, 无需 cherry-pick):

| 资产 | 4b'.4 用途 |
| --- | --- |
| `IndustryAnalysisFilterBar` + `useIndustryAnalysisFilters` | 4b'.4 跨 Mode E2E 测试覆盖 Industry 路径 |
| `lib/kg/g6Composer` | 4b'.4 visual regression baseline (KG 截图) |
| `lib/csv/exportCsv` + `lib/csv/exportTypes` | 4b'.4 CSV 8 接入点 E2E (Playwright 下载文件断言 BOM) |
| `CsvExportButton` | 4b'.4 跨 8 页面 visual baseline 复用 |
| `legacyRedirects.tsx` + `vercel.json` | 4b'.4 11 Legacy 301 E2E (Playwright follow-redirects) |
| `TopicIntentMatrix` (共享, 4b'.2 git mv) | 4b'.4 跨 Brand+Industry Mode visual diff (同组件 2 个 mount 点) |

**禁止行为** (4b'.4 实施时):
- ❌ 重写 g6Composer (8 坑点已固化, fork 立即触发 STOP B6)
- ❌ 重写 exportCsv (csv-stringify + BOM + 10k + 5/min 已锁定)
- ❌ cherry-pick 旧分支 KG / CSV 代码 (Frank Q1 决策, memory `feedback_genpano_branch_per_session`)

---

## Decision-Freshness Final Check (本 Session 收尾时再跑一次, 关闭回路)

- ✅ CLAUDE.md 决策 #2 (IA v2.0 + 11 Legacy 301 列表) 已读入并落 §1 / §4 / §6 L3
- ✅ CLAUDE.md 决策 #18 (测试自动化 A++) — 4b'.4 收尾跑 P0 10 项, 本 Session 仅 Vitest pages/industry/lib coverage
- ✅ CLAUDE.md 决策 #19 (Citation §4.2.7.F: CSV #9/#10 v1.1/Phase 2) 已读入并落 §2 ❌ list
- ✅ CLAUDE.md 决策 #20 v3.2 (TopicIntentMatrix 跨 Mode 复用) 已读入并落 §1 / §5 Step 0.5
- ✅ CLAUDE.md 决策 #21 D4 (11 Legacy 301 全覆盖 harness) 已读入并落 §4 / §6 L1 Check 9
- ✅ CLAUDE.md 决策 #25 (Prompt 公约 12 条) 已遵守 (规则 5 §1 真相源索引 / 规则 6 §X.Y 锚点 / 规则 10 §2 MVP scope-cut / 规则 11 §0 pre-flight grep / 规则 12 §3 STOP triggers)
- ✅ Memory `feedback_genpano_g6_knowledge_graph` 8 坑点已读入并落 §5 Step 0.6 + §6 L1 Check 11 + §6 L3 S12
- ✅ Memory `feedback_production_deps` 已读入 — KG 用 AntV G6, CSV 用 csv-stringify, 禁手写
- ✅ Memory `feedback_genpano_session_commit_rule` 已读入 — Session 宣绿后立即 commit, 不延后
- ❌ 注意: AntV G6 v5 在 production 环境的 KG 全量数据 (1000+ 节点) 性能未 4b'.3 验证 (memory `feedback_genpano_g6_knowledge_graph` 提到 layer 1 测试用 ≥30 节点) — 4b'.4 visual regression 时若发现性能问题, 需升级到 G6 worker mode (Phase 2)
- ❌ 注意: 11 Legacy 301 的 vercel.json 服务端层在 dev 环境不生效 (Vite dev server 不读 vercel.json), 仅 production preview 可验 → S10-S13 必须在 `app.preview.genpano.dev` 跑, 不在本地 5173 跑

---

**Session 4b'.3 Prompt END · 准备给 Claude Code 执行**
