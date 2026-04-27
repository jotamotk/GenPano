# Session 4b'.2 Prompt · Brand Mode 9 sub-views + Citation 5 Tab + Charts shared lib

**版本**: 1.0 · 创建日期 2026-04-26
**拆分自**: `docs/SESSION_4B_PRIME_PROMPT.md` (consolidated 4b' 的第 2/4 段)
**上游链**: 0' → 4a' → 4b'.1 → **本 Session (4b'.2)** → 4b'.3 → 4b'.4
**下游 Session**: 4b'.3 GREEN gate = 本 Session PASS

---

## §0 · Pre-Flight Grep Contract (开工前 30min 内执行, 全部命中才能动代码)

```bash
# F1 · IA v2.0 Brand 9 路径锚点 (PRD §4.6-IA-v2.B)
rg -n "/brand/(overview|visibility|topics|sentiment|citations|products|competitors|diagnostics|reports)" docs/PRD.md | head -20
# 期望: ≥ 9 命中 (Brand Mode 9 sub-views 完整列出)

# F3 · DESIGN_TOKENS C9-C15 V2 视觉契约 (decision #20)
rg -n "^### C(9|10|11|12|13|14|15)\." docs/DESIGN_TOKENS.md | head -10
# 期望: 7 命中 (C9 Heatmap 不借 chart-N / C10 FilterBar 唯一出口 / C11 mentionRate [0,1] / C12 DonutChart size=180 / C13 Quadrant sqrt+showLabels / C14 V2 密度 / C15 ProductDetail brandId 查询串)

# F4 · 上游 GREEN gate (Sessions 4b'.1 + 3' + A1' 必须 PASS)
rg -n "Session 4b'.1.*GREEN|Session 3'.*GREEN|Session A1'.*GREEN" docs/SESSIONS_PYTHON.md | head -10
# 期望: 三者全部 GREEN; 任一为 ❌ 立即 STOP Type A4

# F6 · Brand API 端点 (3' Session 交付的 OpenAPI 锚)
curl -s https://api.preview.genpano.dev/api/v1/openapi.json | jq -r '.paths | keys[]' | grep -E "brands/.*/(overview|visibility|topics|sentiment|citations|products|competitors)" | head -10
# 期望: ≥ 7 命中 (3' 已交付 Brand 9 数据端点中至少 7 条 GET)

# F11 · Citation 全链路真相源 + 埋点 (PRD §4.2.6 + §4.2.7 + §4.11.4 S12)
rg -n "AiCitation|citation_share|citation_attribution_mismatch|content-gap|pr_score|attribution_mismatch_viewed" docs/PRD.md | head -15
# 期望: ≥ 8 命中 (Citation 5 Tab 完整描述 + 事件 #50-#56)

# F13 · BrandProductDetailPage brandId 查询串契约 (decision #20 Wave-4 / DESIGN_TOKENS C15)
rg -n "useSearchParams|brandId.*query string|/brand/products/:productId" docs/PRD.md docs/DESIGN_TOKENS.md | head -10
# 期望: ≥ 4 命中 (绝不能 useParams 解构 brandId)

# F12 · CLAUDE.md 最近 3 条决策 freshness check (规则 11)
rg -n "^[0-9]+\. \*\*" CLAUDE.md | tail -3
# 期望: 决策 #28/#29/#30, 任何提及 Brand/Citation/Heatmap/Quadrant 必须读全文
```

**STOP 触发对照表**:

| 命中条件 | STOP 类型 | 行动 |
| --- | --- | --- |
| F4 显示 4b'.1 / 3' / A1' 任一未 GREEN | Type A4 | 暂停, 回追前置 Session |
| F1 命中数 < 9 (Brand 9 路径) | Type B1 (truth source 漂移) | 回 PRD §4.6-IA-v2 校验, 不允许猜测路径 |
| F3 命中数 < 7 (C9-C15 缺失) | Type B6 (DESIGN_TOKENS 漂移) | 回 DESIGN_TOKENS.md 校验, 不允许新自创视觉 |
| F6 显示 < 7 个 Brand 端点 | Type B1 (上游契约不齐) | 回 3' Session 补端点, 不允许 4b'.2 mock 绕过 |
| F11 命中数 < 8 (Citation 描述不齐) | Type B1 | 回 PRD §4.2.6/§4.2.7 校验 |
| F13 命中数 < 4 | Type B6 | 回 DESIGN_TOKENS C15 校验 — 这是 productDetail 空白页根因 |
| F12 显示有未读决策 | Type B7 | 读全文, 加入 §1 真相源索引再开工 |

---

## §1 · Truth Source Index (本 Session 引用 / 修改的所有真相源, 段号最小单元)

### Prerequisites (chain dependency, 全部 GREEN 才能开工)

| 前置 Session | GREEN 条件 | 本 Session 依赖点 | 验证命令 |
| --- | --- | --- | --- |
| **4b'.1** | App Shell + Topbar Mode pill + Sidebar + RouteGuard + AuthPage + OnboardingPage + SettingsPage 全部 PASS, ComingSoon placeholder 在 /brand/* 9 路径就绪 | 本 Session 把 ComingSoon 替换成真实页面 | `curl -s https://app.preview.genpano.dev/brand/overview` 返回 200 + 含 "ComingSoon" 字样 |
| **3'** | Brand 9 数据 GET 端点 + Citation API + Topic/Sentiment/Product 聚合端点齐备, OpenAPI 发布 | TanStack Query 接真实端点 / openapi-typescript 重新生成类型 | `curl -s https://api.preview.genpano.dev/api/v1/openapi.json \| jq '.paths \| keys'` 含 Brand 9 端点 |
| **A1'** | Citation Tier 5 级权重 (1.0/0.7/0.4/0.15/0) DB seed 完成, GET `/api/v1/citations/tiers` 返回非空 + 4b'.1 i18n key `citation.tier.0`-`tier.4` 注册 | Citation 5 Tab 渲染 tier badge / Authority Radar 5 维 | `curl -s https://api.preview.genpano.dev/api/v1/citations/tiers \| jq '. \| length'` 返回 5 |

**STOP Type A4**: 上述任一前置 Session 未 GREEN, 本 Session 必须暂停 Phase Gate 任何活动, 回追前置 Session 的 Phase Gate 报告。**绝不**用 mock/stub 绕过缺失的真实端点。

### 引用的真相源 (只读)

| 文档 / 锚点 | 引用内容 | 用途 |
| --- | --- | --- |
| `docs/PRD.md §4.2.5` | Brand Topics 第 1 层 (TopicIntentMatrix 共享 / brandTopicHits / Heatmap) | /brand/topics 实现 |
| `docs/PRD.md §4.2.6 A-H` | Citation 原始层真相源 (AiCitation+CitationDomainAuthority schema / 5 Tier / 3 级归因 / citation_share 公式 / PANO A 公式 / source_loss T-14d diff) | Citation Overview Tab 数据消费 |
| `docs/PRD.md §4.2.7 A-H` | Citation 6 条行动面 (归因诊断 / 内容策略 content-gap / 外联 PR / 竞品解构 / Simulator 延后 / MCP) | Citation 5 Tab 拆分 (Overview/Domains/Content-Gap/PR-Targets/Competitor-Citations) |
| `docs/PRD.md §4.6-IA-v2.B` | Brand Mode 侧栏分析组 7 + 运营组 2 = 9 项 | 路由实现完整列表 |
| `docs/PRD.md §4.6-IA-v2.K-N + M.5/M.6` | V2 视觉统一 + Tier 2 引用域覆盖矩阵 + Same-Group | /brand/competitors 实现 |
| `docs/PRD.md §4.6-IA-v2.O` | BrandProductDetailPage brandId 查询串契约 (Wave-4) | /brand/products/:productId?brandId= 实现 |
| `docs/PRD.md §4.7.0-a / §4.8.2 / §4.8.6` | Report 深化框架 (insight Stack + 三读者视角) | /brand/diagnostics + /brand/reports 视角声明 |
| `docs/PRD.md §4.11.4 S12` | Citation 埋点 #50-#53 (MVP) + #54-#56 (v1.1 延后) | Mixpanel 接入 |
| `docs/DESIGN_TOKENS.md C1-C7` | 图表契约 (Sparkline 100% / 引擎色 / SoV 其他 / sentiment %整数 / 锯齿模数 / Donut size=180 / BRANDS.ranking) | Charts 共享库实现 |
| `docs/DESIGN_TOKENS.md C9-C15` | V2 视觉契约 (Heatmap 不借 chart-N / FilterBar / mentionRate [0,1] / DonutChart 强制 / Quadrant / 密度 / ProductDetail brandId) | 全 Brand Mode 必须遵守 |
| `CLAUDE.md` decisions #2 / #15 / #16 / #17 / #18 / #19 / #20 / #21 D / #25 | IA / 提及率 non-brand / Filter Bar / 测试 A++ / Citation 全链路 / V2 视觉 / Wave-4 / Review 修复 / Prompt 公约 | 决策回引 (本 Session 读完才动代码) |

### 修改的资产 (写入)

| 文件 | 改动类型 | 说明 |
| --- | --- | --- |
| `frontend/src/lib/charts/Sparkline.tsx` | NEW | Recharts 封装 + C1 100% 默认 + B1 harness 锚点 |
| `frontend/src/lib/charts/DonutChart.tsx` | NEW | C12 size=180 强制 + B6 harness 锚点 |
| `frontend/src/lib/charts/CompetitorQuadrantChart.tsx` | NEW | C13 sqrt + showLabels + bubbleRadius=[8,24] 默认 |
| `frontend/src/lib/charts/BrandTopicHeatmap.tsx` | NEW | C9 sequential 色带 (mentionRate) + diverging 色带 (sentiment) + 不借 chart-N |
| `frontend/src/lib/charts/AuthorityRadar.tsx` | NEW | Citation Authority Radar 5 维 |
| `frontend/src/lib/charts/Tier2CoverageMatrix.tsx` | NEW | M.5 我 + Top 3 竞品 × 8 权威域 + color-mix intensity |
| `frontend/src/lib/charts/index.ts` | NEW | barrel export |
| `frontend/src/components/filter/BrandAnalysisFilterBar.tsx` | NEW | C10 唯一出口 + URL state (?from=&to=&engines=&profileGroup=&dimensions=&intents=) |
| `frontend/src/hooks/useBrandAnalysisFilters.ts` | NEW | URL state hook (禁本地 useState) |
| `frontend/src/pages/brand/BrandOverviewPage.tsx` | REPLACE ComingSoon | 5 KPI (提及率/SoV/情感/引用份额/行业排名) |
| `frontend/src/pages/brand/BrandVisibilityPage.tsx` | REPLACE ComingSoon | FilterBar + BrandTopicHeatmap |
| `frontend/src/pages/brand/BrandTopicsPage.tsx` | REPLACE ComingSoon | FilterBar + 4-stat grid + TopicIntentMatrix (共享组件 from 0') |
| `frontend/src/pages/brand/BrandSentimentPage.tsx` | REPLACE ComingSoon | FilterBar + DonutChart + diverging Heatmap |
| `frontend/src/pages/brand/citations/CitationOverviewTab.tsx` | NEW | citation_share + PANO A + source_loss diagnostic |
| `frontend/src/pages/brand/citations/CitationDomainsTab.tsx` | NEW | Tier 1-4 域聚合 + Tier 表 (DB seed 不硬编码) |
| `frontend/src/pages/brand/citations/CitationContentGapTab.tsx` | NEW | mentioned − attributed 反向差 + 页面类型对比 |
| `frontend/src/pages/brand/citations/CitationPrTargetsTab.tsx` | NEW | pr_score 排序 + Tier 2 覆盖矩阵 + KOL Shannon entropy |
| `frontend/src/pages/brand/citations/CitationCompetitorTab.tsx` | NEW | Authority Radar + Same-Group + Acquisition (v1.1 stub) |
| `frontend/src/pages/brand/BrandCitationsPage.tsx` | REPLACE ComingSoon | 5 Tab Router 容器 + Mixpanel #50-#53 |
| `frontend/src/pages/brand/BrandProductsPage.tsx` | REPLACE ComingSoon | BCG (sort 不 reduce) + Sparkline Grid + 表格 + 关系 (4 区, 不是 7 区) |
| `frontend/src/pages/brand/BrandProductDetailPage.tsx` | NEW | C15 useSearchParams('brandId') 强制 + 降级而非空白 |
| `frontend/src/pages/brand/BrandCompetitorsPage.tsx` | REPLACE ComingSoon | Top 3 威胁卡 + 雷达 + 胜负 Heatmap + M.5 + M.6 |
| `frontend/src/pages/brand/BrandDiagnosticsPage.tsx` | REPLACE ComingSoon | Insight Stack L1/L2/L3 + 三读者声明 |
| `frontend/src/pages/brand/BrandReportsPage.tsx` | REPLACE ComingSoon | JSON 只读容器 (PDF 渲染延后) |
| `frontend/src/i18n/zh-CN.json` | EXTEND | brand.* / citation.* / chart.* 命名空间 |
| `frontend/src/i18n/en-US.json` | EXTEND | 同上, 对偶完整 (A2 harness 锚) |
| `scripts/ci_check.py` Group I | EXTEND | I1/I2/I3/I4/I5 五条 cifixture |
| `scripts/ci-harness-selftest.py` | EXTEND | EXPECTED_POSITIVES 33 → 38 |
| `frontend/src/__ci_fixtures__/I1_*.cifixture.tsx` | NEW | I1 Sparkline literal width 违规 fixture |
| `frontend/src/__ci_fixtures__/I2_*.cifixture.tsx` | NEW | I2 sentiment text-3xl 文字百分比违规 (禁 DonutChart) |
| `frontend/src/__ci_fixtures__/I3_*.cifixture.tsx` | NEW | I3 mentionRate literal ≥ 1 违规 |
| `frontend/src/__ci_fixtures__/I4_*.cifixture.tsx` | NEW | I4 useState('7d') 绕 URL 违规 |
| `frontend/src/__ci_fixtures__/I5_*.cifixture.tsx` | NEW | I5 BrandProductDetailPage useParams 解构 brandId 违规 |
| `scripts/verify_4b2.sh` | NEW | Phase Gate L1 自动化验证脚本 |
| `playwright/brand-flow.spec.ts` | NEW | E2E (Brand Mode 完整一遍 click-through, 不含 KG) |

### 版本注意事项 (12 条, 严格按 4b'.1 已锁版本)

1. **React 19 hooks**: useSearchParams 仍来自 react-router-dom v6.x, 不要误用 next/navigation 模式
2. **Recharts v2 API**: ResponsiveContainer 必须包裹所有 chart, width/height 用 % 而非 px (C1 锚点)
3. **TanStack Query v5**: useQuery({ queryKey, queryFn }) 而非 v4 的 useQuery(key, fn)
4. **i18next v23**: t(key, { brand, count }) 传 values 对象 (decision #20 第 8 点 i18n interpolation API)
5. **Mixpanel browser SDK**: track 永远走 lib/mixpanel.ts 唯一入口, 禁直接 import mixpanel-browser 在 page 里
6. **TS 5.6 strict**: 禁 `any`, 所有 API 类型必须从 openapi-typescript 生成的 types 来
7. **Tailwind v3.4+**: 用 token (text-xs / text-[13px] / p-3 / space-y-3 = C14 V2 密度), 禁自定义 hex
8. **CSS color-mix**: M.5 Tier 2 矩阵 intensity 用 color-mix() 不要 rgba/hsla 手算 (浏览器原生)
9. **AntV G6 v5**: **不在本 Session 引入** (KG 在 4b'.3)
10. **Playwright v1.4x**: brand-flow.spec.ts 仅 1 条 click-through, 不做 visual snapshot (延 4b'.4)
11. **msw v2**: 禁进 production bundle (4b'.1 已锁), 本 Session 不再 stub Brand 端点 (走真实 3' API)
12. **openapi-typescript 5.x**: 重新生成 types (Brand 9 + Citation 5 端点入), drift 检测进 verify_4b2.sh

---

## §2 · MVP Scope-Cut Declaration (做 / 不做 双列表, 决策 #25 规则 10)

### ✅ 本 Session **做** (Y15-Y29)

| ID | 项目 | PRD/DESIGN 锚点 |
| --- | --- | --- |
| **Y15** | Charts 共享库 (Sparkline / DonutChart / CompetitorQuadrantChart / BrandTopicHeatmap / AuthorityRadar / Tier2CoverageMatrix) | DESIGN_TOKENS C1-C13 |
| **Y16** | BrandAnalysisFilterBar + useBrandAnalysisFilters URL state hook | DESIGN_TOKENS C10 / decision #17 |
| **Y17** | /brand/overview 5 KPI 卡 (提及率/SoV/情感/引用份额/行业排名) | PRD §4.6-IA-v2.B / decision #15 |
| **Y18** | /brand/visibility FilterBar + BrandTopicHeatmap (sequential 色带) | DESIGN_TOKENS C9 |
| **Y19** | /brand/topics FilterBar + 4-stat grid + TopicIntentMatrix (共享自 0') | PRD §4.2.5 / decision #20 v3.2 |
| **Y20** | /brand/sentiment FilterBar + DonutChart size=180 + diverging Heatmap | DESIGN_TOKENS C12 / C9 |
| **Y21** | /brand/citations 5 Tab Router 容器 + Mixpanel #50/#51 | PRD §4.6.1b / §4.11.4 S12 |
| **Y22** | Citation Overview Tab (citation_share + PANO A + source_loss diagnostic) | PRD §4.2.6.A-H |
| **Y23** | Citation Domains Tab (Tier 1-4 + Tier 表 from API) | PRD §4.2.6 + decision #19 (禁硬编码) |
| **Y24** | Citation Content-Gap Tab (mentioned − attributed + 页面类型) | PRD §4.2.7.B |
| **Y25** | Citation PR-Targets Tab (pr_score 排序 + Tier 2 矩阵 + KOL entropy) | PRD §4.2.7.C |
| **Y26** | Citation Competitor Tab (Authority Radar + Same-Group) | PRD §4.2.7.D |
| **Y27** | /brand/products BCG 4 区 + ProductDetail brandId 查询串 (C15) | PRD §4.6-IA-v2.O / DESIGN_TOKENS C15 |
| **Y28** | /brand/competitors Top 3 威胁卡 + 雷达 + 胜负 Heatmap + M.5 + M.6 | PRD §4.6-IA-v2.M.5/M.6 |
| **Y29** | /brand/diagnostics + /brand/reports 视角声明 + JSON 只读 | PRD §4.7.0-a / §4.8.2 / §4.8.6 |
| **harness** | Group I I1-I5 (5 cifixture) + selftest 33 → 38 | decision #21 C |

### ❌ 本 Session **不做** (列出延期目标 + 锚点)

| 项目 | 延期到 | 锚点 |
| --- | --- | --- |
| Industry Mode 4 sub-views | 4b'.3 | PRD §4.6-IA-v2.D |
| Industry KG (AntV G6 v5) | 4b'.3 | memory `feedback_genpano_g6_knowledge_graph` 8 坑点 |
| 11 Legacy 301 redirects | 4b'.3 | decision #2 / Plan I |
| CSV 导出 (#1-#10 含 Citation #9/#10) | 4b'.3 | PRD §4.6.4 / decision #19 |
| Citation Simulator 独立页 (/brands/:id/simulator) | v1.1 | PRD §4.2.7.E |
| Citation Acquisition 事件流 | v1.1 | PRD §4.2.7.D |
| MCP API 3 工具 UI 入口 | A5' / Phase 2 | PRD §4.5.2 + decision #21 E |
| Report PDF 渲染 (7 页) | Phase 2 | PRD §4.7.0-a |
| /brand/* visual regression baseline | 4b'.4 | TEST_STRATEGY §3.1 |
| 跨 Brand 全 E2E (含 KG) | 4b'.4 | TEST_STRATEGY §3.4 |
| Lighthouse + Vercel deploy | 4b'.4 | decision #18 |

---

## §3 · STOP Triggers (Type A 环境 / B 真相源 / C 范围, decision #25 规则 12)

### Type A · 环境失败 (强制暂停, 不允许绕过)

| ID | 触发条件 | 行动 |
| --- | --- | --- |
| **A4** | 上游 Session (4b'.1 / 3' / A1') 任一未 GREEN | 暂停, 回追前置 Session, 不允许 mock |
| **A5** | DNS app.preview.genpano.dev 不通 | 暂停, 回追 0' Vercel infra |
| **A8** | GitHub Actions 跑 verify_4b2.sh 失败但本地通过 | 暂停, 不允许 force-push 或 commit retry |
| **A9** | 真实 Brand API 端点返回 500 持续 ≥ 5min | 暂停, 回追 3' Session, 不允许 msw 顶替 |

### Type B · 真相源冲突 (回 PRD/DESIGN_TOKENS 校验)

| ID | 触发条件 | 行动 |
| --- | --- | --- |
| **B1** | F1 / F6 / F11 命中数低于阈值 | 回 PRD §4.6-IA-v2.B / §4.2.6 / §4.2.7 校验 |
| **B6** | F3 / F13 命中数低于阈值 | 回 DESIGN_TOKENS C9-C15 校验 |
| **B7** | F12 显示有未读决策提及 Brand/Citation/Chart | 读全文, 加入 §1 真相源索引再开工 |
| **B8** | OpenAPI 类型生成产生 TS 编译失败 (端点删字段) | 暂停, 回追 3' Session 修字段, 不允许在 frontend 单边降级 |

### Type C · 范围溢出 (拒绝越界 + 触发 scope 重谈)

| ID | 触发条件 | 行动 |
| --- | --- | --- |
| **C11** | 单 .tsx 文件 > 500 行 | 强制拆分, 不允许大文件 |
| **C13** | 任何 page 出现 useState('7d') / useState 时间窗 (绕 URL state) | 立即重写为 useBrandAnalysisFilters, 这是 I4 harness 拦截点 |
| **C15** | 任何 .tsx 出现中文/英文 literal 直写 (非 i18n key) | 立即抽 i18n, 这是 A1 harness 拦截点 |
| **C18** | 想 cherry-pick frontend/ 旧 React 18 代码 | 拒绝, 全 Python pivot 后从 0 重写 |
| **C19** | Mixpanel.track 出现 PII (email / 用户名 / IP) | 立即改 email_domain, decision #21 D 红线 |
| **C20** | Citation Tier 权重数字 (1.0/0.7/0.4/0.15) 出现在 .tsx 硬编码 | 立即改走 useQuery(['/api/v1/citations/tiers']), decision #19 红线 |
| **C21** | BrandProductDetailPage 出现 `const { brandId } = useParams()` | 立即改 useSearchParams, 这是 I5 harness 拦截点 + Wave-4 教训 |

---

## §4 · Harness Group I (本 Session 新增 5 条 + cifixture self-seeded)

**L3/L4 Phase Gate**: 本 sub-Session 验收追溯到 SESSION_4B_PRIME_PROMPT.md §4 L3/L4 Phase Gate 卡控 (Hard Fail), 详见 REPLAN_2026_04_26.md §5 4b' 行.

### I1 · `chart-sparkline-no-literal-width-percent`

- **范围**: `frontend/src/**/*.{tsx,jsx}` 排 `__ci_fixtures__/`
- **正则**: `<Sparkline\s+[^>]*width=["']\d` (literal 数字 width prop) OR `<Sparkline\s+[^>]*\bheight=["']\d`
- **白名单**: `lib/charts/Sparkline.tsx` (实现内可写 default)
- **fixture**: `__ci_fixtures__/I1_sparkline_literal_width.cifixture.tsx` 写 `<Sparkline width="200" />` 触发拦截

### I2 · `sentiment-must-use-donutchart`

- **范围**: `frontend/src/pages/brand/**/*.tsx`
- **正则**: basename 含 `sentiment` 时, 文件必须 import `DonutChart` from `@/lib/charts`; 不得出现 3 个 `text-3xl` 文字百分比 (`text-3xl[\s\S]{1,200}%`)
- **fixture**: `__ci_fixtures__/I2_sentiment_text3xl.cifixture.tsx` 用 3 个 `<div className="text-3xl">75%</div>` 写情感分布

### I3 · `mention-rate-literal-must-be-decimal`

- **范围**: `frontend/src/**/*.{tsx,ts}` + `mock/**`
- **正则**: `mentionRate\s*[:=]\s*(\d+(\.\d+)?)` 抓 capture, 数字 ≥ 1 触发
- **白名单**: `__tests__/`
- **fixture**: `__ci_fixtures__/I3_mention_rate_literal.cifixture.tsx` 写 `mentionRate: 16.2` 触发 (修复 1620% bug)

### I4 · `brand-analysis-filter-must-use-url-state`

- **范围**: `frontend/src/pages/brand/**/*.tsx` 排 `BrandReportsPage.tsx` (read-only JSON 容器)
- **正则**: `useState\(['"](7d|14d|30d|90d|1y)['"]\)` (任一时间窗 literal 进 useState)
- **fixture**: `__ci_fixtures__/I4_filter_local_state.cifixture.tsx` 写 `const [range, setRange] = useState('7d')` 触发

### I5 · `brand-product-detail-must-use-searchparams-brandid`

- **范围**: `frontend/src/pages/brand/BrandProductDetailPage.tsx`
- **正则**: `const\s*\{\s*brandId\s*\}\s*=\s*useParams` (禁解构 brandId from useParams)
- **fixture**: `__ci_fixtures__/I5_product_detail_useparams_brandid.cifixture.tsx` 写 `const { brandId, productId } = useParams()` 触发 (Wave-4 教训锚点 / DESIGN_TOKENS C15)

### selftest 期望

`scripts/ci-harness-selftest.py` EXPECTED_POSITIVES: **33 → 38** (本 Session 加 I1/I2/I3/I4/I5 五条)。本 Session GREEN 的硬条件: `python scripts/ci-harness-selftest.py` 输出 `selftest: PASS  (38 / 38 fixture expectations met)`。

---

## §5 · Step Delivery Order (2 步, 续 4b'.1 步骤号)

### Step 0 (原 §5 Step 6) · Charts 共享库 + FilterBar

```bash
# 不需要 npm install 新依赖, 4b'.1 已锁 recharts / @tanstack/react-query
# 创建 lib/charts/* 6 个组件 + lib/charts/index.ts barrel
# 创建 components/filter/BrandAnalysisFilterBar.tsx + hooks/useBrandAnalysisFilters.ts
# Vitest unit test 覆盖 lib/charts/* 80% 阈值 (用 @testing-library/react)
```

**验收**: 
- `npm run vitest -- lib/charts` 全绿
- `npm run lint` 0 warning
- DESIGN_TOKENS lint 检查 (verify_4b2.sh) 通过 — 0 hex color, 全 token

### Step 1 (原 §5 Step 7) · Brand Mode 9 sub-views + Citation 5 Tab + Group I

```bash
# 9 个 page 替换 ComingSoon → 真实组件
# 5 个 Citation Tab 拆 (Overview / Domains / Content-Gap / PR-Targets / Competitor)
# 1 个 ProductDetail 页 (C15 contract 严格)
# i18n key 注册 (zh-CN.json + en-US.json 对偶完整)
# Mixpanel #50/#51/#52/#53 接入 (Citation 4 事件)
# Group I I1-I5 添加 + 5 cifixture self-seeded
# selftest 跑 38/38 通过
```

**验收**:
- `npm run vitest` 全绿 (含 page-level smoke test 至少每页 1 条)
- `python scripts/ci_check.py I1 I2 I3 I4 I5` 5 条规则 PASS
- `python scripts/ci-harness-selftest.py` 38/38
- `npx playwright test brand-flow.spec.ts` 1 条 E2E 通过 (Brand 9 sub-view click-through)

---

## §6 · Phase Gate (L1 自动 / L2 selftest / L3 Frank 真机)

### Layer 1 · `bash scripts/verify_4b2.sh` (12 项自动检查)

```bash
#!/usr/bin/env bash
# scripts/verify_4b2.sh - Session 4b'.2 Phase Gate L1 verifier
set -euo pipefail

echo "→ [1/12] ESLint" && npm run lint --silent
echo "→ [2/12] tsc strict" && npx tsc --noEmit
echo "→ [3/12] Vitest pages/brand/* + lib/charts/* coverage 80%" && \
  npm run vitest -- --coverage --coverage.include='src/pages/brand/**' --coverage.include='src/lib/charts/**' --coverage.thresholds.lines=80 --coverage.thresholds.branches=80
echo "→ [4/12] Vite build size + msw not in prod" && \
  npm run build && \
  test "$(stat -c%s dist/assets/*.js | sort -n | tail -1)" -lt 2097152 && \
  ! grep -r "msw" dist/ 2>/dev/null
echo "→ [5/12] OpenAPI typegen drift" && \
  npx openapi-typescript https://api.preview.genpano.dev/api/v1/openapi.json -o /tmp/types-fresh.ts && \
  diff src/lib/api/types.ts /tmp/types-fresh.ts
echo "→ [6/12] i18n parity zh-CN === en-US key count" && \
  test "$(jq 'paths | length' src/i18n/zh-CN.json | wc -l)" = "$(jq 'paths | length' src/i18n/en-US.json | wc -l)"
echo "→ [7/12] Group I (I1-I5) PASS" && \
  python scripts/ci_check.py I1 I2 I3 I4 I5
echo "→ [8/12] selftest 38/38" && \
  python scripts/ci-harness-selftest.py | grep "38 / 38"
echo "→ [9/12] Playwright brand-flow" && \
  npx playwright test brand-flow.spec.ts
echo "→ [10/12] Lighthouse a11y on /brand/overview, /brand/citations, /brand/products" && \
  npx lighthouse https://app.preview.genpano.dev/brand/overview --only-categories=accessibility --output=json | jq '.categories.accessibility.score >= 0.9'
echo "→ [11/12] DESIGN_TOKENS lint (no raw hex)" && \
  ! grep -rE "#[0-9a-fA-F]{3,6}" src/pages/brand/ src/lib/charts/
echo "→ [12/12] Mixpanel 0 PII (no email / no userId raw)" && \
  ! grep -rE "track\([^)]*\b(email|userId|user_id|fullName|phone)\b[^)]*[^_]\)" src/

echo "✅ verify_4b2.sh PASS"
```

### Layer 2 · `python scripts/ci-harness-selftest.py` (38 cifixture self-seeded)

期望输出: `● selftest: PASS  (38 / 38 fixture expectations met)`

### Layer 3 · Frank 真机走查 (preview env app.preview.genpano.dev/<branch>)

| 检查 ID | 路径 / 操作 | 期望 |
| --- | --- | --- |
| **S4** | `/brand/overview` | 5 KPI 卡渲染真实数据 (来自 3'); 提及率显示百分比格式 (1620% bug 不能复现); FilterBar 改时间范围 → URL ?from/&to 同步, 数据刷新 |
| **S5** | `/brand/visibility` + `/brand/sentiment` | FilterBar 切换 dimensions=品类 → Heatmap 重渲; Sentiment 用 DonutChart 不是 3 个 text-3xl |
| **S6** | `/brand/products` → click 单产品 | URL 变 `/brand/products/:productId?brandId=:brandId`; 详情页**不空白**, 显示 GEO 数据; 删 ?brandId 后产品名 fallback `product.brand` 但不崩 |
| **S7** | `/brand/citations` 5 Tab 切换 | URL ?tab=overview / domains / content-gap / pr-targets / competitor 五种值都生效; Mixpanel debug 看到 #50/#51/#52/#53 事件触发, 属性只含 `brand_slug` 不含 email |
| **S8** | `/brand/competitors` | Top 3 威胁卡 → 选中 → Authority Radar 5 维 + 胜负 Heatmap + M.5 Tier 2 矩阵 (8 列) + M.6 Same-Group 卡显式说明 "母集团叙事 vs 兄弟品牌 SoV" |
| **S9** | `/brand/diagnostics` + `/brand/reports` | Diagnostics 显示 Insight Stack L1/L2/L3 三段 + 三读者声明; Reports 显示 JSON 只读容器 (PDF 延后, 文案讲清) |

---

## §7 · Downstream Session Note (4b'.3 GREEN gate = 本 Session PASS)

4b'.3 (Industry Mode + KG + CSV + 11 Legacy 301) 将复用本 Session 的:

- `lib/charts/*` 全部组件 (KG 单独用 AntV G6 v5, Heatmap 复用 BrandTopicHeatmap → 在 Industry Topics 重命名为 共享组件)
- `BrandAnalysisFilterBar` (将 fork 出 `IndustryAnalysisFilterBar` 共享 hook)
- `useBrandAnalysisFilters` (作为 useIndustryAnalysisFilters 模板)
- TopicIntentMatrix (本 Session Y19 已落, 4b'.3 在 /industry/topics 二次复用 — decision #20 v3.2)
- TanStack Query API client (扩 Industry 4 端点)
- formatBrand helper (从 4b'.1 继承)
- Mixpanel helper (从 4b'.1 继承, 4b'.3 加 Industry / KG / CSV 事件)
- ci_check.py Group I 框架 (4b'.3 不加新 harness, 4b'.4 才聚合)

**绝不**重写 / 不并行重构 / 不 cherry-pick 这些已落地资产。

---

## Decision-Freshness Final Check (Session 收尾时跑, 决策 #25 规则 7)

- [ ] §0 7 条 grep 全部命中阈值
- [ ] §1 上游 Prerequisites 三 GREEN 已 curl 验证
- [ ] §1 引用真相源段号未漂移 (PRD/DESIGN_TOKENS 段号仍存在)
- [ ] §2 Y15-Y29 全部 ✅ 完成 (15 项)
- [ ] §2 N 项目延后清单未跨界进入本 Session
- [ ] §4 Group I I1-I5 + selftest 38/38
- [ ] §5 Step 0 (Charts) → Step 1 (Pages) 顺序未跳
- [ ] §6 L1 verify_4b2.sh 12/12 PASS + L2 selftest + L3 Frank S4-S9 6 项

**已知偏差** (登记于 CLAUDE.md 决策 #28+ 偏差段):

- [ ] **C1**: Citation Simulator (PRD §4.2.7.E) + Acquisition 事件流 (PRD §4.2.7.D 后段) 延后 v1.1, 本 Session 不实现 (与 PRD 标记一致)
- [ ] **C2**: MCP API 3 工具 (genpano_get_citations / list_pr_targets / simulate_authority_boost) UI 入口延后 A5' / Phase 2, 但 Citation 5 Tab 数据契约已对齐 MCP 工具读路径 (A5' 时无须改 frontend)

---

**End of Session 4b'.2 Prompt** · 拆分自 `docs/SESSION_4B_PRIME_PROMPT.md` · 上游 4b'.1 GREEN / 3' GREEN / A1' GREEN · 下游 4b'.3 等本 Session GREEN
