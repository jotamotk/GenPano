# Session Prompts 一致性审查报告 (2026-04-26)

## 审查范围

**11 个 Session Prompts** 全量扫描 (Path B 一致性检查):
- Session 0' / A0' / 4a' (基础设施 + Auth)
- Session 1' / 1.5' / 1.2' (Pipeline 后端)
- Session 2' / 2.1' (Planner)
- Session 3' / A1' (Analytics + Admin)
- Session 4b' (Frontend IA v2.0 + MVP 完成)

**对照真相源**: PRD.md / ADMIN_PRD.md / TEST_STRATEGY.md / DATA_MODEL.md / ADAPTER_CONTRACT.md / DESIGN_TOKENS.md / CLAUDE.md / MEMORY.md

**审查方式**: 5 个并行 Agent (Agent 1 / 2 / 3a / 3b / 3c) 各负责 2-3 个 Session, 输出 ~70 条 drift 项, 本报告做综合 + 优先级排序。

---

## 一、关键发现 (Critical Finding)

### **P0-A · 修订版 (2026-04-26 验证后) · CLAUDE.md anchor 决策已补齐**

**初版 P0-A 已作废**. 初版误判 "CLAUDE.md 冻结在 #28, 决策 #29-#40 仅存在于 MEMORY.md, 11 Sessions 全部引用 #29-#40 会被 Decision #25 规则 1 拦截". **Explore agent 验证后实际情况**:

**(1) CLAUDE.md 实际包含决策 #26 / #27 / #28 完整正文** (lines 299 / 355 / 384), 不是只到 #25. 初版 agent 报告口径错误.

**(2) 11 Session Prompts 全部引用 `docs/REPLAN_2026_04_26.md` 作主真相源, 不引用 "决策 #29-#40" 数字编号** — `grep -r "决策 #29" docs/SESSION_*_PRIME_PROMPT.md` 零命中, "决策 #30/#31/#32/#33/#34/#35/#36/#37/#38/#39/#40" 同样零命中. **不存在断链问题**.

**(3) CLAUDE.md 正文实际唯一缺陷**: 决策 #28 末尾 C2 段在 line 418 截断 (`tsc --noEmit 才暴` mid-sentence). 已完成补齐 (修复操作于 2026-04-26 commit).

**(4) 已新增决策 #29 anchor 决策**: 指向 `docs/REPLAN_2026_04_26.md` 作 2026-04-26+ Python pivot 工作的真相源, 含 4 项 cross-cutting 决策 (A: REPLAN 真相源锚定 / B: 11 Session Prompt 已交付 / C: preview env 横切要求 / D: 分支策略). **不再** 在 CLAUDE.md 内逐项展开 #30-#40 (避免 ~3300 行膨胀), 替代方案是 REPLAN_2026_04_26.md 单文件 442 行集中承载 11 Session 规格.

**修复状态**: ✅ 已完成 (2026-04-26 修复). CLAUDE.md 决策 #28 截断尾巴补齐 + 决策 #29 anchor 添加. 11 Session Prompts 不需改动 (因从未引用 #29-#40 数字编号).

**残留 P0 仍需修**: P0-3 (常量冲突) / P0-4 (Session 4b' 内部结构) / P0-5 (§0 grep contract) / P0-6 (Session 间依赖) / P0-7 (测试覆盖映射). 见下文.

---

## 二、P0 修复清单 (24 项, 必须修)

### **P0-1 · CLAUDE.md 决策 #29-#40 backfill** (上述 P0-A, 影响 11 Sessions)

### **P0-2 · 工具链 / Infra 真相源**

| # | Drift | 影响 Session | 修复 |
|---|---|---|---|
| 2.1 | `REPLAN_2026_04_26.md` 文件存在性未验证, 11 Prompts 全引用 | 全部 11 | grep 确认存在; 不存在则 Frank 创建 §4 "11 Session 列表" |
| 2.2 | `SESSION_PROGRESS.md` 文件存在性未验证 | 0', 4b' | 同上 |
| 2.3 | `ADMIN_PRD_B_PIPELINE.md` / `ADMIN_PRD_C_KG.md` 分卷文件存在性未验证 | A1' | grep 确认; CLAUDE.md 顶部目录树已列, 但未实地核查 |
| 2.4 | `CI-CD.md` 真相源被 Session 0' 引用, 但是新文件 | 0' | Session 0' 自己产出, 此处需确认 §4.X 的最终段号 |

### **P0-3 · 跨 Session 常量冲突**

| # | Drift | 冲突项 | 修复 |
|---|---|---|---|
| 3.1 | `REFRESH_TOKEN_TTL_SECONDS` | A0' = 7 天 (604800s) vs 4a' = 30 天 (2592000s) | Admin 端短 TTL (敏感操作) + User 端长 TTL (用户体验) 是合理的; 但需在 A0' / 4a' Prompt §1 显式声明"Admin TTL ≠ User TTL", 避免 Claude Code 误以为漂移 |
| 3.2 | 测试命令 | Session 1' §4 混用 `pytest` 和 `uv run pytest` | 全部 Session 统一为 `uv run pytest` (Python pivot 后用 uv 管理); Session 1' 修 |
| 3.3 | Harness selftest 计数 | Sessions 2'/2.1' 写 "15→19→22 expectations" 但未交代 baseline 来源 | §0 必须列出 "本 Session 前 selftest 期望值 = N, 本 Session 后 = N + Δ, Δ 明细"; Sessions 2'/2.1' 修 |
| 3.4 | Harness Group 编号 | Session 4b' 引入 I1-I6 (6 条新规则) 但未声明前置 baseline | Session 4b' §0 列出 "selftest 22 → 28 (+I1..I6)"; 修 §0 |

### **P0-4 · Session 4b' 内部结构** (5 项)

| # | Drift | 修复 |
|---|---|---|
| 4.1 | DESIGN_TOKENS.md C9-C15 段头不规范 (内联 prose 无 `### C9` 标题) | Session 4b' 开工第 0 步先重组 DESIGN_TOKENS.md, 把 C9-C15 改为标准 H3 段头, 让 grep 能精确定位 |
| 4.2 | 11 条 Legacy 301 重定向未枚举 | Session 4b' §3 列出 11 条具体 from→to 表 (引决策 #2 / IA v2.0) |
| 4.3 | M1/M2/M3/M4 Milestone 划分未明 | §2 增 M1=shell+auth, M2=brand-mode 9 pages, M3=industry+CSV, M4=E2E+verify+deploy 四段 |
| 4.4 | Session 4b' 单 Session 范围过大 (合理工作量 = 4 个子 Session) | 建议拆 4b'.1 / 4b'.2 / 4b'.3 / 4b'.4, 每个 1-2 天独立 PR + preview env |
| 4.5 | I1-I6 6 条 harness 与 self-evidencing fixture 配对未明 | §6 必须列出 6 个 cifixture.tsx 的具体路径 |

### **P0-5 · §0 Pre-Flight Grep Contract 自证强度不足**

5 个 Sessions (2', 2.1', 3', A1', 4b') 的 §0 grep 命令"自证太弱", 即 Claude Code 即使所有 grep 失败仍能继续 — 违反 Decision #25 规则 2。

| # | Session | 修复 |
|---|---|---|
| 5.1 | 2' | §0 增 "若 grep 1-3 任一无输出则 STOP Type B + 报告 Frank" 显式动作行 |
| 5.2 | 2.1' | 同上, 加 "若 #27 不在 CLAUDE.md 出现则 STOP" |
| 5.3 | 3' | 同上, 加 PRD §4.5.x MCP server 段号 grep |
| 5.4 | A1' | 同上, 加 ADMIN_PRD §5.6.1 (3 角色 CHECK) grep |
| 5.5 | 4b' | 同上, 加 DESIGN_TOKENS C9-C15 段头存在性 grep |

### **P0-6 · Sessions 间的依赖声明不全**

| # | Drift | 影响 | 修复 |
|---|---|---|---|
| 6.1 | Session 2.1' 依赖 Session 2' 的 `topic-pool.ts` 接口 但 §1 未列 | 2.1' | §1 加 "前置 Session 2' 必须 phase-gate 通过, 接口 `generatePlatformPlan({llm}: ...)` 已就绪" |
| 6.2 | Session 3' MCP server 依赖 Session A5 (Citation Tier CRUD + Token 签发) 但 A5 在 11 Sessions 列表中无 | 3' | 决策 #21.E 把 A5 列出来了, 但本次 Python pivot 11 Sessions 没排 A5; Frank 需决定: (a) A5 拆入 A1' (b) 单建 A5' (c) 推到 Phase 2 |
| 6.3 | Session 4b' 依赖 Session 3' API + A1' Admin token 签发 | 4b' | §1 加双依赖声明 |

### **P0-7 · 测试覆盖矩阵未对齐 TEST_STRATEGY.md v1.1**

| # | Drift | 修复 |
|---|---|---|
| 7.1 | TEST_STRATEGY §11 P0 10 项 / P1 5 项 / P2 4 项, 但 11 Sessions 没逐一映射 | 创建 `docs/TEST_COVERAGE_MAP.md`, 每条 P0-P2 映射到 Session N + 测试类型 (L1-L4) |
| 7.2 | TEST_STRATEGY §10 Admin-specific 7 异常, A0' / A1' Prompt 未引用 | A0' / A1' §1 真相源索引加 TEST_STRATEGY §10 [引用] |

---

## 三、P1 修复清单 (20 项, 推荐修)

### **P1-1 · Decision #25 规则 5 真相源索引格式不统一**

部分 Prompt §1 用 `PRD §X.Y [引用]` 标记完整, 部分只写 `见 PRD §X.Y`。建议全部 11 Sessions 统一为 `[引用] / [修改] / [新增]` 三标签格式。

| 影响 Sessions | 修复 |
|---|---|
| 1', 1.5', 2', 2.1' | §1 改 `[引用] / [修改]` 格式 |

### **P1-2 · §4 STOP Trigger Type A/B/C 模板未一致填充**

Decision #25 规则 12 要求每 Session §4 列 Type A (环境失败) / Type B (真相源冲突) / Type C (范围溢出) 三类 STOP, 部分 Sessions 只写了 Type A 一两条。

| Session | 缺失 | 修复 |
|---|---|---|
| 0' | Type C 缺 | 加 "若 §4 列出的 12 步执行顺序漂移到第 13 步 → STOP" |
| 1.5' | Type B 缺 | 加 "若 LLM 调用预算 >50/industry → STOP Type B" |
| 2' | Type A 缺 | 加 "若 InMemoryKgRepositories 测试装备未就绪 → STOP" |
| 4b' | Type B 缺 | 加 "若发现 DESIGN_TOKENS C9-C15 段头未规范化 → STOP 先修 token doc" |

### **P1-3 · Phase Gate 验收标准过宽**

部分 Prompt §6 写 "Phase Gate: 全绿 / 基本可用" 等模糊标准, 没给具体验收条款。

| Session | 修复 |
|---|---|
| 4a' | §6 加 5 项: (a) 注册 → 邮箱验证 → 登录全链路 (b) Onboarding 4 步草稿 72h 过期 (c) DraftProject Prisma model 字段齐 (d) RequireAuth route guard 拦截 (e) 埋点 #63-#70 已发 |
| A1' | §6 加 5 项: (a) 3 角色 RBAC 矩阵 (b) Audit log 30 天保留 (c) Invitation flow (d) Force password change (e) Reauth gate 30min 窗口 |

### **P1-4 · 决策 #25 规则 7 (Session 完成时反查) 未显式提示**

11 Sessions 的 Phase Gate 都没把"反查 §1 真相源是否仍成立"作为收尾步骤。

修复: 每 Session §6 末尾加 "Phase Gate 第 N+1 项: 反查规则 2 grep 命令仍输出预期结果 + §1 列的真相源段号未漂移; 若漂移按规则 3 登记偏离"。

### **P1-5 · Sessions 2'/2.1' Harness 自证 fixture 路径不显式**

Sessions 2'/2.1' §6 提到 "fixture 加 G1-G4 / H1-H3", 但没列具体文件路径 (e.g. `backend/src/__ci_fixtures__/G1_matrix_row_count_wrong.cifixture.ts`)。修复: 列全 7 条 fixture 路径。

### **P1-6 · 6-Enum response_source 列表 (决策 #28.G C3) 引用不全**

| Session | 缺失 | 修复 |
|---|---|---|
| 1' | response_source 6 枚举未引用 | §1 加 "见 CLAUDE.md #28.G C3" |
| 1.2' | 同上 | 同上 |
| 3' | 同上 (Analytics 读 ai_responses) | 同上 |

### **P1-7 · MVP Scope-Cut Declaration (规则 10) 双列表格式**

部分 Sessions §2 没用"做 / 不做"双列表, 而是单列表 + prose 混写。

| Session | 修复 |
|---|---|
| 1.2' | §2 拆双列表 (做: Camoufox + 3 引擎 + Luban + auto-register; 不做: ChatGPT auto-register + Phase 2 反检测升级) |
| 3' | §2 拆双列表 (做: 5 KPI + MCP server + CSV; 不做: Citation Tier CRUD + Simulator + Phase 2 PR Score) |
| A1' | §2 拆双列表 |

---

## 四、P2 修复清单 (15 项, 可接受)

### **P2 范畴**: 不影响 Claude Code 开工的格式 / 文档美化问题

- 中英文混排不一致 (统一用中文 + 关键术语英文)
- 段号引用从 `PRD §4` 改 `PRD §4.6.1b` (规则 6, 但部分无具体子段时可保留宽段号)
- §3 ASCII 数据流图 / 架构图缺失 (有助于阅读但非必须)
- 各 Session §8 "下一步" 段引用其他 Session 编号但未确认时间表
- Markdown 表格列宽不一致 (纯美观)

详细 15 项见各 Agent 原始报告, 此处省略。

---

## 五、Cross-Cutting 建议 (5 条)

### **Cut-1 · 统一 Decision Tracker 文档**

新建 `docs/DECISION_LOG.md`, 把 CLAUDE.md 决策 #1-#40 + MEMORY.md 全部决策合并成单一索引, 每条带:
- 决策号
- 日期
- 主题
- 真相源段号 (PRD/ADMIN_PRD/DATA_MODEL etc.)
- Session 引用列表 (反向索引)
- 状态 (active / superseded / phase-2)

未来任何 Session Prompt §1 真相源索引只需引用 `DECISION_LOG #N`, 不再各自维护决策列表。

### **Cut-2 · 验证 docs/ 文件存在性**

跑一条 grep 自检确认:
- `docs/REPLAN_2026_04_26.md`
- `docs/SESSION_PROGRESS.md`
- `docs/ADMIN_PRD_B_PIPELINE.md`
- `docs/ADMIN_PRD_C_KG.md`
- `docs/CI-CD.md`
- `docs/TEST_COVERAGE_MAP.md` (P0-7 新增)
- `docs/DECISION_LOG.md` (Cut-1 新增)

不存在的文件标记为 P0 阻塞 (Frank 创建 / 我代写 stub)。

### **Cut-3 · 11 Sessions Milestone 时间表对齐**

REPLAN §4 应有 11 Sessions 的时间表 (Wave/Phase 划分), 但本次未实地核查。建议:
- Wave 1 (基础设施): 0' / A0' / 4a' (1-2 周)
- Wave 2 (Pipeline): 1' / 1.5' / 1.2' (2-3 周)
- Wave 3 (Planner): 2' / 2.1' (1 周)
- Wave 4 (Analytics): 3' / A1' (1-2 周)
- Wave 5 (Frontend): 4b' (拆 4 子 Session, 2-3 周)

总计 ~7-11 周到 MVP 完成, 与决策 #29 Python pivot 后的 4 周 MVP 估计有差距 — 需 Frank 重估。

### **Cut-4 · Session 4b' 必须拆分**

Session 4b' 单 Session 覆盖 9 brand pages + 4 industry pages + auth + onboarding + CSV + i18n + harness + E2E + visual baseline + preview deploy, 工作量 = 4 个 Session。强烈建议拆:

- **4b'.1**: App shell + Auth pages + Onboarding (3-5 天)
- **4b'.2**: Brand Mode 9 子页面 + filter bar + heatmap (5-7 天)
- **4b'.3**: Industry Mode 4 页 + CSV export + i18n + KG visualization (3-5 天)
- **4b'.4**: E2E Playwright + Visual baseline + Preview deploy + Phase Gate (2-3 天)

每个子 Session 独立 PR + preview env (符合决策 #30)。

### **Cut-5 · Decision #25 规则 11 Pre-Send Freshness Check 未在任何 Prompt 体现**

规则 11 要求发 Prompt 前 30min 跑 3 条 grep 检查 CLAUDE.md / docs/auto-memory / migration 新增项。这次 11 Prompts 创建时是否做了? — 推断**没做**, 否则 P0-A (CLAUDE.md #29-#40 缺失) 会被发现。

修复路径: Frank 在把任一 Prompt 交给 Claude Code 前, 我代跑 3 条 grep 验证, 输出 "freshness check report" 进 Prompt §1 footer。

---

## 六、修复执行顺序建议

按 "拦最致命 → 让 Claude Code 能开工" 顺序:

1. **P0-A** (CLAUDE.md backfill #29-#40) → 30min 手工 / 我代写
2. **Cut-2** (验证 docs/ 文件存在性) → 5min grep
3. **P0-2** (引用文件不存在则建 stub) → 30-60min
4. **P0-3** (常量冲突 + 测试命令统一) → 15min 修 3 个 Prompt
5. **P0-4** (Session 4b' 拆 + DESIGN_TOKENS 重组) → 1-2h
6. **P0-5** (5 Sessions §0 自证强化) → 30min
7. **P0-6** (依赖声明) → 30min
8. **P0-7** (TEST_COVERAGE_MAP.md 新建) → 1-2h
9. **P1-1 ~ P1-7** (20 项, 批量改) → 2-3h
10. **P2** (15 项, 可放后续 PR) → 后续

**总修复时间估计**: 6-10h, 一天内可全部关闭。

---

## 七、决策点 (Frank 需拍板)

下列 4 项需 Frank 决策:

### **D1 · A5 (Citation Tier CRUD + MCP Token) 归属**
决策 #21.E 列了 A5 Session, 但本次 Python pivot 11 Sessions 没排 A5。选项:
- (a) 把 A5 deliverable (Tier CRUD UI + Token CRUD) 拆入 A1' (推荐, 若 A1' 工作量允许)
- (b) 新建 A5' Session, 11 Sessions 变 12
- (c) 推到 Phase 2 (但 Session 3' MCP server 需要 Token 签发, 这条路不通)

**建议**: (a), 把 Tier 表 CRUD 进 A1' Tab "参数管理", Token 签发进 A1' Tab "API Token 管理"。

### **D2 · Session 4b' 是否拆 4 子 Session**
拆: 工作量更准, 每个 1-3 天独立 PR + preview env (符合 #30)
不拆: 保持 11 Sessions 总数, 但 Session 4b' 风险高 (>2 周不收口)

**建议**: 拆。理由: (a) 4 个 preview env 比 1 个 mega-PR 更易自验 (b) Session 4b' 任一子环节 (e.g. KG visualization G6 复杂度) 卡住, 不会拖累其他 brand-mode 页面 (c) Frank 可在 4b'.2 完成后先看 brand-mode 真实样, 再决定是否调整 4b'.3 优先级

### **D3 · MVP 4 周到 7-11 周拉长**
Python pivot 后总工作量重估 = 7-11 周, 比原 4 周预算长。Frank 决策:
- 接受 MVP 时间拉长
- 减 MVP 范围 (e.g. 只做 brand-mode 不做 industry-mode, MVP 后追加)
- 减 MVP 引擎 (3 → 2, e.g. 只 doubao + deepseek-CN, ChatGPT 后追加)

### **D4 · 是否新建 DECISION_LOG.md**
Cut-1 建议新建 docs/DECISION_LOG.md 做决策中央索引。
- 利: 真相源更清晰, 跨 Session 引用方便
- 弊: 又一个文档需维护, MEMORY.md 已类似功能

**建议**: 建 (Light 版), 只做反向索引 (决策号 → Session 列表), 内容仍以 CLAUDE.md / MEMORY.md 为准。

---

## 八、本报告交付物

- 11 Sessions 全量 drift 清单 (P0=24 / P1=20 / P2=15, 共 ~70 项)
- 5 条 Cross-Cutting 建议
- 4 项 Frank 决策点 (D1-D4)
- 修复执行顺序 (10 步, 6-10h 内可关闭)

**报告生成日期**: 2026-04-26
**审查方式**: 5 Agent 并行扫描 + 综合
**下一步**: Frank 决策 D1-D4, 然后启动 P0 修复
