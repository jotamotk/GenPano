# CLAUDE_CODE_SESSIONS_PYTHON.md

GENPANO Python 重构 Session 总索引 (2026-04-26 起)

本文档是 Python 架构反转 (CLAUDE.md 决策 #29) 后的 Session 实施总索引,取代 master `docs/CLAUDE_CODE_SESSIONS.md` 中已被 `docs/REPLAN_2026_04_26.md §4` 反转的 TS 实施部分。

## 1. 阅读顺序

1. **必读 (按序)**:
   - `docs/REPLAN_2026_04_26.md` — Python 反转决策书 + 11 Session 规格 (§4)
   - `CLAUDE.md` 决策 #25 (Prompt 公约 12 条) + #29 (Python 反转) + #30 (preview 强制) + #31 (分支规则) + #32 (工作仓)
   - `docs/SESSION_0_PRIME_PROMPT.md` — Session 0' 是所有后续 Session 的格式范本 + 基础设施前置
2. **首跑准备**:
   - `docs/PRD.md` (425KB v1.3) — 产品语义真相源
   - `docs/HARNESS_ENGINEERING.md` — 38 条 harness 规则血统
   - `docs/TEST_STRATEGY.md` v1.1 §9-§13 — 异常场景 + 优先级 + 血统表
3. **按需读**:
   - `docs/ADMIN_PRD.md` + `docs/ADMIN_PRD_B_PIPELINE.md` + `docs/ADMIN_PRD_C_KG.md` — Admin 侧 (A0' / A1' 必读)
   - `docs/ADAPTER_CONTRACT.md` — 引擎契约 (1' / 1.2' 必读)
   - `docs/DATA_MODEL.md` — 数据模型 (1.5' / 2' 必读)

## 2. Session 总览

| # | Session | 主题 | Milestone | 周期 | 状态 | Prompt 文件 |
|---|---------|------|-----------|------|------|-------------|
| 0' | Session 0' | Python 后端基础设施 + CI/CD + Preview Env | M1 | 1 周 | 已起草 | `docs/SESSION_0_PRIME_PROMPT.md` |
| A0' | Session A0' | Admin 认证 Python 重写 | M1 | 0.5 周 | 待起草 | `docs/SESSION_A0_PRIME_PROMPT.md` |
| 4a' | Session 4a' | User Auth + Onboarding 4 步引导 | M1 | 1 周 | 待起草 | `docs/SESSION_4A_PRIME_PROMPT.md` |
| 1' | Session 1' | Adapter 框架 + Account/Proxy Pool | M2 | 1 周 | 待起草 | `docs/SESSION_1_PRIME_PROMPT.md` |
| 1.5' | Session 1.5' | 知识图谱 Platform Layer 冷启动 | M2 | 1 周 | 待起草 | `docs/SESSION_1_5_PRIME_PROMPT.md` |
| 1.2' | Session 1.2' | Camoufox + 3 引擎 Live + Luban SMS Live | M2 | 1.5 周 | 待起草 | `docs/SESSION_1_2_PRIME_PROMPT.md` |
| 2' | Session 2' | Planner Pipeline (Topic→Prompt→Query) | M3 | 1 周 | 待起草 | `docs/SESSION_2_PRIME_PROMPT.md` |
| 2.1' | Session 2.1' | Planner LLM Refinement | M3 | 0.5 周 | 待起草 | `docs/SESSION_2_1_PRIME_PROMPT.md` |
| 3' | Session 3' | 分析引擎 + 用户态 API + MCP Server | M3 | 1.5 周 | 待起草 | `docs/SESSION_3_PRIME_PROMPT.md` |
| A1' | Session A1' | Admin 用户管理 + KG 审核 + Pipeline 监控 | M4 | 1 周 | 待起草 | `docs/SESSION_A1_PRIME_PROMPT.md` |
| 4b' | Session 4b' | IA v2.0 完整化 (mock→real API) | M4 | 1 周 | 待起草 | `docs/SESSION_4B_PRIME_PROMPT.md` |

合计: 11 Session, 8-10 周 (含 buffer)。

## 3. Milestone 分组

### Milestone 1 — Auth E2E + Preview 基线 (Week 1-2.5)
- **包含**: 0' + A0' + 4a'
- **可验证**: Frank 在浏览器登录 user 账号 + admin 账号, 完成 onboarding 4 步, 看到空 dashboard。Preview env 上 PR 自动产 URL。
- **依赖**: 0' → A0' (并行 4a')

### Milestone 2 — Pipeline E2E + Admin Response 验证 (Week 2.5-5.5)
- **包含**: 1' + 1.5' + 1.2'
- **可验证**: 任选 1 行业 (e.g. beauty) 跑通 KG 冷启动 + 1 个 query 经 Camoufox + 鲁班 SMS 拿到 3 引擎 (chatgpt/doubao/deepseek-CN) 真实 response 落库。Admin 可看到 ai_responses 行 + browser_profile 注入。
- **依赖**: 1' → 1.5' (并行) → 1.2' 串接

### Milestone 3 — User API + MCP (Week 5.5-8)
- **包含**: 2' + 2.1' + 3'
- **可验证**: Planner dump 3 维度 topic + naturalized prompt + LLM-rewritten query。Frank 注册 MCP token + 用 Claude Desktop 调 `genpano_get_brand_visibility`。
- **依赖**: 2' → 2.1' → 3'

### Milestone 4 — IA v2.0 全态 + Admin Beta (Week 8-10)
- **包含**: A1' + 4b'
- **可验证**: 9 brand sub-views + 4 industry sub-views 全部接真实 API 渲染。Admin 可在浏览器审 KG / 看 Pipeline 监控 / 管 user。
- **依赖**: A1' (并行 4b')

## 4. 依赖图

```
                                 ┌─────────────────────────┐
                                 │      Session 0'         │
                                 │  Python 基础设施 + CI/CD  │
                                 └────┬─────────────┬──────┘
                                      ↓             ↓
                         ┌─────────────────┐  ┌──────────────────┐
                         │   Session A0'    │  │   Session 4a'    │
                         │   Admin Auth     │  │  User Auth+Onb.  │
                         └────────┬─────────┘  └────────┬─────────┘
                                  ↓                     ↓
                         ┌────────────────────────────────────────┐
                         │              M1 完成                    │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │     Session 1'           Session 1.5'  │
                         │     Adapter 框架          KG 冷启动     │
                         │     (并行)                              │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │           Session 1.2'                  │
                         │  Camoufox + 3 引擎 Live + Luban Live   │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │              M2 完成                    │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │           Session 2'                    │
                         │     Planner Pipeline (规则模板)         │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │           Session 2.1'                  │
                         │     Planner LLM 增强                    │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │            Session 3'                   │
                         │  分析 + 用户 API + MCP Server          │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌────────────────────────────────────────┐
                         │              M3 完成                    │
                         └────────────┬───────────────────────────┘
                                      ↓
                         ┌─────────────────┐  ┌──────────────────┐
                         │   Session A1'    │  │   Session 4b'    │
                         │  Admin 用户/KG   │  │  IA v2.0 接 API  │
                         │   /Pipeline 监控  │  │  (并行)           │
                         └────────┬─────────┘  └────────┬─────────┘
                                  ↓                     ↓
                         ┌────────────────────────────────────────┐
                         │              M4 完成 / MVP             │
                         └────────────────────────────────────────┘
```

## 5. 共享公约

所有 Session Prompt 必须遵守:

### 5.1 Prompt 编写公约 (CLAUDE.md 决策 #25, 12 条)

- **规则 1** 真相源锚定: 同一信息只能有一处权威, Prompt 引用不重抄
- **规则 2** 前置 Grep 契约: §0 必须 3-6 条 grep 让 Claude Code 自证
- **规则 3** 偏离必记录: 实施中与真相源冲突时, 进度报告必须 C1/C2/... 列出, 同步 CLAUDE.md
- **规则 4** 真相源双向同步: 改真相源的 PR 同步触发 grep + 更引用段号 + CLAUDE.md 新决策
- **规则 5** §1 必须声明真相源索引表
- **规则 6** 段号锚到最小单元 (`§4.2.7.C` 不写 `§4`)
- **规则 7** Session 收尾反查一致性 (重跑 §0 grep)
- **规则 10** MVP Scope-Cut 双列表: ✅ 做 / ❌ 不做, 禁 "核心功能" 模糊措辞
- **规则 11** Pre-Send Decision-Freshness Check: 发 Prompt 前 30min 跑 3 grep
- **规则 12** 显式 STOP-Trigger: Type A 环境 / B 真相源 / C 范围

### 5.2 Session 体系横切要求

- **决策 #30 (preview 强制)**: 每 Session 必须 (1) 代码上 preview env (2) 前后端联动可点击 (3) Frank 浏览器自验
- **决策 #31 (分支规则)**: 每 Session 从 main fork 一个 `session-<X>` 分支, 不并入 claude/* 历史
- **决策 #32 (工作仓)**: `C:\Users\frank.wang\genpano` (jotamotk/GenPano.git), `query_tool/` Phase 2 排除

### 5.3 Phase Gate 三层验收

- **Layer 1 (机器)**: `verify-session-<X>.sh` 跑 lint + test + harness selftest + 数据契约 + 数据库迁移 + Celery 烟测
- **Layer 2 (Harness)**: `npm run ci:harness:selftest` 全绿 (Python 部分跑 `python -m harness selftest`)
- **Layer 3 (人审)**: Frank 在 preview env 浏览器点验关键路径

### 5.4 Prompt 必需结构 (§0-§8)

模板源: `docs/SESSION_0_PRIME_PROMPT.md` (304 行已验证)

- **§0 Pre-flight Grep 契约**: 6 条 grep, F1-F6 编号
- **§1 真相源索引表**: ≥ 16 行 + [引用]/[修改]/[反向工程入口] 标签 + 修改清单 + 版本警告
- **§2 MVP Scope**: ✅ 表 (项 + 锚点 + 验收信号) + ❌ 表 (项 + 推迟到 + 理由), N1, N2, ... 编号
- **§3 STOP Triggers**: Type A (A1-A4) / B (B1-B3) / C (C1-C3) + STOP 报告模板
- **§4 Phase Gate**: G<sessionId>.1-G<sessionId>.N + 自动 vs 人审标注
- **§5 12 步交付**: Step 0 → Step 12 原子 commit ≤ 5 文件, 标题格式 `Session X' Step N: <主题>`
- **§6 交付报告模板**
- **§7 Closing Loop**: 重跑 §0 grep 后再终极 commit
- **§8 Final Reminders**: 1-10 编号, 给 Claude Code 的最终注意

## 6. 与 master Sessions 的关系

每个 Python Session Prompt 的 §1 真相源索引表必须列出对应的 master Session (CLAUDE.md 决策号), 例如:

| Python Session | Master Session (CLAUDE.md 决策) | 关系 |
|----------------|--------------------------------|------|
| 0' | 决策 #21 (Review 修复闭环) | 取代 (TS Session 0 → Python 基础设施) |
| A0' | 决策 #24 (Session A0 Admin 认证) | 取代 (TS 实现报废, 算法保留) |
| 4a' | 决策 #21 + #10 (Onboarding) | 取代 (TS Session 4a 报废) |
| 1' | 决策 #22 (Session 1 Adapter 框架) | 取代 (算法语义保留, 实现 Python) |
| 1.5' | 决策 #23 (Session 1.5 KG 冷启动) | 取代 (算法保留, 实现 Python) |
| 1.2' | 决策 #28 (Session 1.2 Camoufox + Live) | 取代 (CLAUDE.md 描述的 TS 流程, Python 直接落地) |
| 2' | 决策 #26 (Session 2 Planner) | 取代 (语义保留, Python 实现) |
| 2.1' | 决策 #27 (Session 2.1 LLM Refinement) | 取代 (Canned + Live 双路保留) |
| 3' | 决策 #19 (Citation 6 行动面) | 新增 (master 未实施, Python 首落) |
| A1' | 决策 #21.E (Admin Session A5) | 合并 (A1 + A2 + A3 + A4 + A5 合并) |
| 4b' | 决策 #20 (V2 分析页统一) | 取代 (frontend 现状接 real API) |

## 7. 后续追加 Session

如 MVP 完成后追加 Session, 命名按 `Session X.Y'` 续号 (e.g. `Session 1.2.1'`), Prompt 文件名 `SESSION_<X>_<Y>_<Z>_PRIME_PROMPT.md`。Phase 2 Session (TSX 迁移 / Aliyun ACR 部署 / Multi-tenant) 待 MVP 完成后单独索引。

## 8. 历史 / 决策追溯

- **2026-04-26**: 本文档首建, 配合 REPLAN_2026_04_26.md 决策 #29 Python 反转
- **2026-04-26**: Session 0' Prompt 起草, 11 Session 总索引建立
- **TBD**: Session A0' / 4a' 起草

每个 Session Prompt merge 后回填本表的 "状态" 列 + 链接 PR。
