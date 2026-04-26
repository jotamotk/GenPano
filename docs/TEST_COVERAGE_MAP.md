# GENPANO Test Coverage Map

> **真相源**: `docs/TEST_STRATEGY.md` v1.1 §11 (P0/P1/P2 优先级清单)
> **创建日期**: 2026-04-26 (Plan K.1 闭合 `docs/CONSISTENCY_REPORT_2026_04_26.md` 发现 P0-7.1)
> **决策依据**: CLAUDE.md 决策 #18 (测试自动化 A++) + 决策 #21 (Review 修复闭环) + 决策 #29 (Python pivot 11 Session 重写)
> **目的**: 把 TEST_STRATEGY §11 P0/P1/P2 共 19 项测试优先级映射到具体 Session N + L1/L2/L3/L4 测试层 + 验收锚点, 让 Frank 能逐项追溯任一测试目标到落地 Session 与可执行命令.

---

## 0. 阅读约定

- **L 层定义**: L1 = Harness grep (脚本 ci-check.mjs) / L2 = Pytest 单测或 Vitest 单测 (单元算法层) / L3 = OpenAPI 契约 + HAR 回放 + Playwright 集成 / L4 = Playwright E2E + Visual Regression + Lighthouse a11y (浏览器侧端到端)
- **Session 命名**: Python pivot 后 11 个 Session 按 REPLAN_2026_04_26.md §4 列出, 4b' 已拆 4b'.1-4b'.4 共 14 个 Prompt 文件
- **状态**: ✅ = MVP 范围内交付 / 🔄 = 跨 Session 累积交付 / ❌ = Phase 2 / v1.1 延后
- **优先级阈值**: P0 必须 Phase Gate 卡死 / P1 警告但不卡 Phase Gate / P2 可推到下游 Session

---

## 1. P0 优先级 (10 项 · MVP 必交付, Phase Gate 卡死)

| # | TEST_STRATEGY §11 条目 | 主要 Session | L 层 | 验收锚点 (命令 / 文件) | 状态 |
|---|---|---|---|---|---|
| **P0-1** | Auth 完整性 (登录/登出/会话过期/silent refresh) | 4a' | L2 + L4 | `pytest backend/tests/auth/` 全绿 + Playwright spec `tests/e2e/auth.spec.ts` 6 步契约 | ✅ |
| **P0-2** | Admin Auth 与 RBAC | A0' | L1 + L2 + L3 | Harness D8/D9/D10 selftest + `pytest backend/tests/admin/auth/` ≥80% + L3 endpoint replay | ✅ |
| **P0-3** | Pipeline Topic→Prompt→Query 三层契约 | 2' | L2 | `pytest backend/tests/planner/` Vitest 等价 ≥80% + golden-beauty 13 例语义锚点 | ✅ |
| **P0-4** | Pipeline LLM Refinement 三档 (Topic refine / Prompt naturalize / Query rewrite) | 2.1' | L1 + L2 | Harness H1/H2/H3 selftest + canned LLM transport 65 新增 case | ✅ |
| **P0-5** | Adapter execute() Live + Account Pool + Cookie 持久化 | 1.2' | L2 + L3 | `pytest backend/tests/engines/` + 3 家引擎 routeFromHAR 回放 + 2 active accounts/engine | ✅ |
| **P0-6** | KG 冷启动 4 行业 + 关系边 | 1.5' | L2 | `pytest backend/tests/platform/discovery/` ≥80% + `seed:platform:dry` 端到端走通 | ✅ |
| **P0-7** | Citation 5 Tier + 三级归因 + URL 归一化 | 3' | L1 + L2 | Harness E1/E2/E3 selftest + `tldts` 归一化单测 + Tier DB seed 而非硬编码 | ✅ |
| **P0-8** | IA v2.0 13 sub-views 路由完整性 | 4b'.1 + 4b'.2 + 4b'.3 | L1 + L4 | Harness C9-C15 selftest + Playwright critical-path.spec.ts register→onboarding→/brand/overview→/brand/citations | ✅ |
| **P0-9** | CSV 导出 BOM + 8 exportType 字段字典 | 4b'.2 | L2 + L4 | Pytest CSV writer + Playwright BOM byte 验证 (0xEF/0xBB/0xBF) + 1024 byte 下限 | ✅ |
| **P0-10** | 11 Legacy 301 dual-layer (client + server) | 4b'.3 + 4b'.4 | L1 + L4 | Harness D4 selftest 抓 ≥11 重定向 + `vercel.json` redirects 段 + `curl -I` 11 路径回 301 | ✅ |

**P0 累计 Session 覆盖**: 4a' / A0' / 2' / 2.1' / 1.2' / 1.5' / 3' / 4b'.1 / 4b'.2 / 4b'.3 / 4b'.4 = 11 Session 中 11 项 (A1' 不参与 P0, 因 KG 质量审核归 P2).

**Phase Gate 卡点**: 任一 P0 项 ❌ → 对应 Session 不予 GREEN, 不可 merge 主分支, 不可推进下游 Session.

---

## 2. P1 优先级 (5 项 · 警告但不卡 Phase Gate)

| # | TEST_STRATEGY §11 条目 | 主要 Session | L 层 | 验收锚点 | 状态 |
|---|---|---|---|---|---|
| **P1-1** | UI 空错加载 三态 (skeleton / empty state / error fallback) | 4b'.1 + 4b'.2 | L4 | Playwright spec `tests/e2e/loading-states.spec.ts` 13 sub-views 抽 3 路抽样 | 🔄 (4b'.4 抽 3 路) |
| **P1-2** | Mixpanel 埋点 #1-#10 + #44-#46 + #50-#56 + #63-#65 + #70 | 4a' + 4b'.1-4 + 3' | L4 | Playwright network intercept Mixpanel POST + `eventName` 白名单 + PII 黑名单 | 🔄 (4b'.4 final assert) |
| **P1-3** | 跨引擎一致性 (3 引擎同 query 结果差异 < 阈值) | 1.2' | L3 | HAR 回放 3 家引擎相同 prompt → 提及率 / 情感 / citation 差异统计 | ✅ |
| **P1-4** | i18n zh-CN/en-US 对偶完整 | 4b'.1 | L1 + L4 | Harness A1/A2/A3 selftest + Playwright 中英切换 spec + formatBrand 唯一入口 | ✅ |
| **P1-5** | Cost 监控 (Planner 入队预算 + Adapter 调用费用累计) | 1.5' + 2' | L2 | Pytest `assignTiers` + `buildEnqueuePlan` 预算 cutoff + estimateCostUsd 单测 | ✅ |

**P1 累计 Session 覆盖**: 4b'.1 / 4b'.2 / 4a' / 4b'.4 / 3' / 1.2' / 2' / 1.5' = 8 Session (重叠 P0 大部分 Session).

**Phase Gate 处理**: P1 失败仅警告, 在 Phase Gate L3 walkthrough 段记入 §C 偏差登记, 不阻塞 GREEN 判定.

---

## 3. P2 优先级 (4 项 · 可推下游 Session)

| # | TEST_STRATEGY §11 条目 | 主要 Session | L 层 | 验收锚点 | 状态 |
|---|---|---|---|---|---|
| **P2-1** | Admin KG QA 5 层抽样 + Trust Score 11 边界 | A1' (Phase 2) | L2 | Pytest `admin/kg/qa/` 抽样算法 + Trust Score boundary 单测 | ❌ Phase 2 |
| **P2-2** | Admin Pipeline 监控面板 (Worker 队列深度 / 失败率 / 成本曲线) | A1' (Phase 2) | L4 | Playwright Admin spec, MVP 暂不交付 | ❌ Phase 2 |
| **P2-3** | MCP Server 3 工具 (genpano_get_citations / list_pr_targets / simulate_authority_boost) | 3' MVP 部分 + v1.1 完整 | L3 | OpenAPI 契约 + auth token 必带 + 3 工具回放 | 🔄 (3' MVP 1 工具 + v1.1 补 2) |
| **P2-4** | Visual Regression 全量 (52 baseline 全 13 sub-views × 4 viewport) | 4b'.4 | L4 | Playwright `visual-regression.spec.ts` 52 toHaveScreenshot baseline | ✅ |

**P2 累计 Session 覆盖**: A1' / 3' / 4b'.4 = 3 Session, 其中 A1' 是 Phase 2 整体延后, 3' 部分交付 + v1.1 补全, 4b'.4 完整交付.

**Phase Gate 处理**: P2 失败可在下一 Session 修复, 当前 Session 仍可 GREEN. 但若 v1.1 仍未交付, 触发 v1.1 Release Gate.

---

## 4. 反向索引 · Session → 测试责任清单

> 给 Claude Code 实施时快速查询某 Session 必须自证哪些 P0/P1/P2 项

### Session 0' (CI/CD 基建)
- **直接交付**: 无 P0/P1/P2 (基建 Session, 不直接对应测试项)
- **横切支撑**: 所有后续 Session 的 L1 (selftest) + L4 (Playwright) 都依赖 0' 交付的 ci-check / playwright.config.ts / .github/workflows/ci.yml
- **Phase Gate 自证**: ci-check 38 rule 注册中 ≥3 (基建初始) + Vercel preview 部署可访问

### Session A0' (Admin 认证)
- **P0 责任**: P0-2
- **P1 责任**: 无
- **P2 责任**: 无 (A1' 才有 P2-1/P2-2)
- **Phase Gate**: D8/D9/D10 selftest + `pytest backend/tests/admin/auth/` ≥80%

### Session 4a' (用户系统 + Onboarding)
- **P0 责任**: P0-1
- **P1 责任**: P1-2 (Mixpanel 埋点 #1-#10 + #63-#65 + #70 onboarding)
- **P2 责任**: 无
- **Phase Gate**: 6 步契约登出 + silent refresh 14min + draft Project 72h 过期 cleanup

### Session 1' (Adapter 框架 + 算法层)
- **P0 责任**: 无 (P0-5 是 1.2' 的 execute() live, 1' 只交付框架 + parser 算法 80% 覆盖)
- **P1 责任**: 无
- **P2 责任**: 无
- **Phase Gate**: 13 单测 ≥80% + Harness F1/F2/F3 selftest

### Session 1.5' (KG 冷启动)
- **P0 责任**: P0-6
- **P1 责任**: P1-5 部分 (estimateCostUsd 单测)
- **P2 责任**: 无
- **Phase Gate**: 10 单测 ≥80% + 4 行业 seed:platform:dry 端到端

### Session 1.2' (Adapter Live + 账号池)
- **P0 责任**: P0-5
- **P1 责任**: P1-3
- **P2 责任**: 无
- **Phase Gate**: Camoufox launch 全绿 + 3 家引擎 routeFromHAR + 鲁班 SMS live + 每引擎 ≥2 active 账号

### Session 2' (Planner 三层)
- **P0 责任**: P0-3
- **P1 责任**: P1-5 部分 (Planner 预算 cutoff 单测)
- **P2 责任**: 无
- **Phase Gate**: 9 单测 ≥80% + golden-beauty 13 例语义锚点 + Harness G1/G2/G3/G4 selftest

### Session 2.1' (Planner LLM Refinement)
- **P0 责任**: P0-4
- **P1 责任**: 无
- **P2 责任**: 无
- **Phase Gate**: 65 新增 case + Harness H1/H2/H3 selftest + canned LLM transport 全绿

### Session 3' (Citation + 分析引擎 + MCP MVP)
- **P0 责任**: P0-7
- **P1 责任**: P1-2 部分 (Mixpanel #50-#56)
- **P2 责任**: P2-3 (MVP 1 工具 / v1.1 补 2)
- **Phase Gate**: Harness E1/E2/E3 selftest + Tier DB seed + tldts 归一化 + 1 MCP 工具 OpenAPI 契约

### Session 4b'.1 (品牌总览 / 可见性 / Topics / 情感)
- **P0 责任**: P0-8 部分 (4 sub-views)
- **P1 责任**: P1-1 部分 (4 sub-views 三态) + P1-4 (i18n)
- **P2 责任**: 无
- **Phase Gate**: Harness C9/C10/C11/C12 selftest + IA v2.0 4 sub-views Playwright smoke

### Session 4b'.2 (Citations / Products / Competitors + CSV)
- **P0 责任**: P0-8 部分 (3 sub-views) + P0-9
- **P1 责任**: P1-1 部分 (3 sub-views 三态)
- **P2 责任**: 无
- **Phase Gate**: Harness C13/C14/C15 selftest + CSV BOM 验证 + 8 exportType 字段字典

### Session 4b'.3 (诊断 / 报告 + Industry Mode 4 sub-views + 11 Legacy 301)
- **P0 责任**: P0-8 部分 (6 sub-views) + P0-10 部分 (client React Router)
- **P1 责任**: P1-1 部分 (6 sub-views 三态)
- **P2 责任**: 无
- **Phase Gate**: Harness I1-I6 selftest + 11 Legacy 301 client 层 抽样

### Session 4b'.4 (聚合验证 + Vercel 生产部署 + MVP COMPLETE)
- **P0 责任**: P0-10 server 部分
- **P1 责任**: P1-1 抽 3 路 + P1-2 final assert
- **P2 责任**: P2-4
- **Phase Gate**: Vitest 80% 聚合 + Playwright critical-path + 52 visual regression + verify_4b4.sh 13-check + git tag mvp-1.0

### Session A1' (Admin KG QA + Pipeline 监控, Phase 2)
- **P0 责任**: 无
- **P1 责任**: 无
- **P2 责任**: P2-1 + P2-2
- **Phase Gate**: Phase 2 启动后另发 Release Gate

---

## 5. L 层覆盖矩阵

> 给 Frank 检阅时一眼看清每条测试项的 L 层分布, 验证 4 层测试 (决策 #18) 都被消化

| 优先级 | L1 (Harness) | L2 (单测) | L3 (契约+HAR) | L4 (E2E+Visual+a11y) |
|---|---|---|---|---|
| **P0-1** Auth 完整性 | - | ✅ | - | ✅ |
| **P0-2** Admin Auth/RBAC | ✅ | ✅ | ✅ | - |
| **P0-3** Planner 三层 | - | ✅ | - | - |
| **P0-4** LLM Refinement | ✅ | ✅ | - | - |
| **P0-5** Adapter Live | - | ✅ | ✅ | - |
| **P0-6** KG 冷启动 | - | ✅ | - | - |
| **P0-7** Citation | ✅ | ✅ | - | - |
| **P0-8** IA v2.0 路由 | ✅ | - | - | ✅ |
| **P0-9** CSV BOM | - | ✅ | - | ✅ |
| **P0-10** 11 Legacy 301 | ✅ | - | - | ✅ |
| **P1-1** UI 三态 | - | - | - | ✅ |
| **P1-2** Mixpanel 埋点 | - | - | - | ✅ |
| **P1-3** 跨引擎一致性 | - | - | ✅ | - |
| **P1-4** i18n 双语 | ✅ | - | - | ✅ |
| **P1-5** Cost 监控 | - | ✅ | - | - |
| **P2-1** Admin KG QA | - | ✅ | - | - |
| **P2-2** Admin Pipeline 面板 | - | - | - | ✅ |
| **P2-3** MCP Server | - | - | ✅ | - |
| **P2-4** Visual Regression 全量 | - | - | - | ✅ |

**4 层 healthy distribution**: L1 = 6 / L2 = 12 / L3 = 4 / L4 = 11 (有重叠), 与决策 #18 "Harness L1 + 单测 80% + 契约 + Visual" 4 支柱一致, 没有任何 L 层被忽略.

---

## 6. 一致性回路检查

> 决策 #25 规则 7: Session 收尾时反查一致性

每个 Session 实施 Claude Code 在 Phase Gate 收尾前必须:

1. **跑 grep**: `grep -E "P0-[1-9]" docs/TEST_COVERAGE_MAP.md` 找到本 Session 应承担的 P0 项
2. **逐项自证**: 把 §1 表格中本 Session 行的"验收锚点"列命令在终端跑一遍, 全绿才发 Phase Gate L3 邀请
3. **回写偏差**: 若任一锚点未达成, 在 Session Prompt §C 偏差登记记录 (是 v1.1 延后 / 是 Phase 2 / 是 P1/P2 接受)
4. **更新本表**: 若 Session 实施过程发现 P0/P1/P2 状态变化 (如 P2-3 v1.1 补 2 工具实际推到 v1.2), 同步更新本文件 §3 状态列 + §4 责任清单

---

## 7. 与 TEST_STRATEGY.md 真相源关系

- **本文件 = 索引**: §11 P0/P1/P2 19 项的 Session 映射 + L 层分布 + 反向责任清单
- **TEST_STRATEGY §11 = 真相源**: 测试项的语义定义 (做什么 / 验收什么 / 边界条件)
- **TEST_STRATEGY §9 = 异常场景矩阵** (本文件不重复, Session Prompt 引用)
- **TEST_STRATEGY §10 = Admin 测试矩阵** (A0' 和 A1' Prompt §1 引用, 见 Plan K.2)
- **TEST_STRATEGY §12 = fixture 命名 + F1-F3** (1' 和 1.2' Prompt 引用)
- **TEST_STRATEGY §13 = 38 规则血统表** (4b'.4 Phase Gate L1 selftest 锁定)

**禁止**: 本文件不重抄 TEST_STRATEGY §11 P0/P1/P2 的语义定义 (违反决策 #25 规则 1 "重抄禁止"), 只列 Session × L 层 × 验收锚点的映射表.

---

## 8. 维护规则

- **触发更新**: TEST_STRATEGY §11 任何 P0/P1/P2 增删改 → 本文件 §1-§4 同步更新
- **触发更新**: Session 拆分 / 合并 / 改名 → 本文件 §1-§4 Session 列同步
- **触发更新**: P0 项实施完成 → 本文件 §1 状态列 ❌ → ✅
- **触发更新**: P2 项推到 v1.1 / Phase 2 → 本文件 §3 状态列标 🔄 或 ❌, §4 反向索引同步
- **审计频率**: 每个 Session Phase Gate L3 收尾前由实施 Claude Code 跑 §6 一致性回路检查

---

## 9. 偏差登记 (Plan K.1 实施层面)

- **C1 (P2-3 MCP Server 跨 Session 交付)**: TEST_STRATEGY §11 把 MCP Server 列为单一 P2 项, 但实施跨 3' (MVP 1 工具) + v1.1 (补 2 工具). 本文件 §3 状态标 🔄 表示分段交付, 不视为 P2 失败. v1.1 Release Gate 时若 2 工具仍未补全, 才升级为 P2 阻塞.
- **C2 (P1-1 UI 三态在 4b'.4 抽样而非全量)**: TEST_STRATEGY §11 P1-1 原意是 13 sub-views 全量 UI 三态测试, 但 4b'.4 Playwright 预算限制只跑 3 路抽样 (loading-states.spec.ts 抽 /brand/overview / /brand/citations / /industry/overview). 余下 10 路 sub-views 三态依赖 4b'.1-4b'.3 各自 Phase Gate L3 walkthrough 时 Frank 视觉抽查. 本文件 §2 状态标 🔄 表示 4b'.4 抽 3 路 + L3 walkthrough 共同覆盖.
- **C3 (P2-1/P2-2 Phase 2 完全延后)**: A1' Session 整体推到 Phase 2, 本文件 §3 状态标 ❌, 不视为 MVP 缺陷. Phase 2 启动时另发 Release Gate, A1' 的 P2 责任在彼时单独 Phase Gate.

---

## 10. 后续动作 (给 Frank 验证)

1. **逐项 Frank 复核**: 用本文件 §1-§3 表格逐行确认 "主要 Session" 和 "L 层" 列与 Frank 心智模型一致, 偏差立即在 §9 偏差登记
2. **Plan K.2 触发**: 本文件 §4 A0' 和 A1' 责任清单确认后, 立刻按 Plan K.2 编辑 A0' 和 A1' Prompt §1 (Truth Source Index) 加入 TEST_STRATEGY §10 引用
3. **Final Validation**: 14 个 Session Prompt 全部存在 + 本文件 §1-§4 覆盖完整 + Plan K.2 完成 → Frank 视觉抽 3 个 Prompt 验证可直接给 Claude Code 跑

---

**本文件由 Plan K.1 (2026-04-26) 闭合 `docs/CONSISTENCY_REPORT_2026_04_26.md` 发现 P0-7.1 创建. 是 GENPANO MVP 测试策略落地到 11 Session × 14 Prompt 的官方索引.**
