# GENPANO - Harness Engineering 方法论

> 一个人 + AI 从 0→1 做产品的系统方法

---

## 1. 什么是 Harness Engineering

Harness Engineering 是一种以"人类驾驭 AI 引擎"为核心的产品开发方法。

类比马术: 骑手 (Human) 不需要自己跑，但必须看得清方向、把得住缰绳、知道什么时候该加速什么时候该刹车。马 (AI) 有力量有速度，但需要骑手控制节奏和方向。

```
传统开发:  人写代码，AI 辅助补全
AI 辅助:   人写架构，AI 写部分代码，人 review
Harness:   人控方向+质量，AI 写全部代码+文档，人驾驭全程
```

**核心理念**: 人类的价值不在于写代码，而在于:
- **判断力**: 什么该做什么不该做
- **品味**: 产品该长什么样
- **领域知识**: 市场、用户、商业模式
- **质量把关**: 最终为产出质量负责

---

## 2. 全生命周期设计

Harness Engineering 不只是"让 AI 写代码"，而是覆盖产品从构思到上线的每个阶段。

```
┌─────────────────────────────────────────────────────────────────┐
│                    HARNESS ENGINEERING 全流程                     │
│                                                                 │
│  Phase 0        Phase 1          Phase 2          Phase 3       │
│  ════════       ════════         ════════         ════════       │
│  产品设计        工程构建          测试验证          上线运营       │
│                                                                 │
│  ┌──────┐      ┌──────┐        ┌──────┐        ┌──────┐       │
│  │Cowork│ ───→ │Claude│ ───→   │Human │ ───→   │Claude│       │
│  │对话式│      │ Code │        │+ AI  │        │ Code │       │
│  │产品设│      │Session│       │协同验 │        │+ 人工│       │
│  │计    │      │×N    │        │证    │        │运维  │       │
│  └──────┘      └──────┘        └──────┘        └──────┘       │
│                                                                 │
│  交付物:        交付物:          交付物:          交付物:         │
│  PRD           可运行代码        测试报告          线上产品        │
│  PRODUCT_PLAN  CLAUDE.md更新    Bug修复           监控数据        │
│  SESSIONS.md   模块文档         性能基线           迭代计划        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 0: 产品设计 (Cowork 对话式)

**工具**: Claude Desktop Cowork 模式
**角色分配**: 人提供 What 和 Why，AI 输出 How 和结构化文档

### 3.1 工作流

```
                    ┌──────────────────┐
                    │  人: 产品愿景     │
                    │  "我想做一个..."  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  AI: 结构化提问   │
                    │  挖掘需求细节     │
                    └────────┬─────────┘
                             │
              ┌──────────────▼──────────────┐
              │  对话循环 (核心价值区)        │
              │                              │
              │  人: 纠偏 + 判断 + 领域知识   │
              │   "不对，应该是 Bottom-Up"    │
              │   "这个架构太重了"            │
              │   "范围上需要 GEO 优化建议"   │
              │                              │
              │  AI: 结构化 + 挑战 + 补盲区   │
              │   "你考虑过双区域的代理问题吗"│
              │   "账号管理有自动化方案..."    │
              │   完善细节，更新文档           │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  交付物 (三件套)   │
                    │  PRD.md           │
                    │  PRODUCT_PLAN.md  │
                    │  CLAUDE_CODE_     │
                    │  SESSIONS.md      │
                    └──────────────────┘
```

### 3.2 人类在 Phase 0 的职责

| 职责 | 具体行为 | 典型发言 |
|------|---------|---------|
| **战略判断** | 决定做什么不做什么 | "GEO 优化建议做，但不产品化 action" |
| **领域纠偏** | 纠正 AI 的错误假设 | "不是 Top-Down，应该 Bottom-Up" |
| **技术决策** | 基于实际约束选方案 | "测试阶段用单节点+代理" |
| **验证信息** | 确认 AI 不确定的外部信息 | "鲁班SMS 我已验证可用" |
| **质量标准** | 定义什么叫"好" | "PANO Score 需要三级评分" |

### 3.3 AI 在 Phase 0 的职责

| 职责 | 具体行为 |
|------|---------|
| **结构化思维** | 把零散想法变成 PRD 章节 |
| **补盲区** | 主动提出人类没想到的问题 (代理方案、账号管理...) |
| **一致性维护** | 确保 PRD/PLAN/SESSIONS 三份文档逻辑一致 |
| **细节落地** | 把"需要 PANO Score"变成完整的接口定义和计算公式 |
| **文档输出** | 直接写出 Claude Code 可消费的高质量 Prompt |

### 3.4 Phase 0 质量门 (Gate)

Phase 0 完成的标准——所有 ✅ 才能进入 Phase 1:

```
□ PRD 覆盖所有模块，无"TODO"或"待定"
□ 每个 Non-Goal 都有明确理由 (不是遗忘，是刻意不做)
□ 技术架构的关键决策都有"为什么"
□ CLAUDE_CODE_SESSIONS.md 每个 Session 的 Prompt 自包含
  (Claude Code 只读 Prompt + CLAUDE.md 就能开始工作)
□ 验收标准可客观判断 (不是"大概 OK"，而是"API 返回 200")
□ 人类已用自己的领域知识审查过所有关键设计
□ 成本估算合理，在预算范围内
```

---

## 4. Phase 1: 工程构建 (Claude Code Sessions)

**工具**: Claude Code CLI
**角色分配**: 人驾驭节奏和质量，AI 写全部代码

### 4.1 Session 生命周期

每个 Session 严格按以下流程执行:

```
┌─────────────────────────────────────────────────────┐
│ PRE-FLIGHT (人类, Session 开始前)                     │
│                                                     │
│ 1. 确认前置 Session 的验收标准全部通过                 │
│ 2. 阅读 CLAUDE.md 确认上下文完整                      │
│ 3. 审查本次 Session 的 Prompt:                       │
│    - 是否有需要根据实际情况调整的内容?                  │
│    - 前一个 Session 有没有遗留问题要一起修?            │
│ 4. 准备好环境 (DB running, deps installed)            │
│ 5. 复制 Prompt → 粘贴给 Claude Code                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ EXECUTION (AI 执行, 人类监控)                         │
│                                                     │
│ Claude Code 按 Prompt 自主执行。                      │
│ 人类此时做什么:                                       │
│   - 观察进展: AI 的思路是否合理?                       │
│   - 不频繁打断: 让 AI 保持完整上下文                   │
│   - 记录问题: 发现可疑设计先记下来，等 AI 完成再 review │
│   - 有明确方向性错误时才介入纠偏                       │
│                                                     │
│ 何时介入:                                            │
│   ✅ AI 选了明显错误的技术路线 (如用了 Browserbase)     │
│   ✅ AI 理解错了需求 (如把 Web-First 做成 API-First)   │
│   ❌ AI 的代码风格不是你喜欢的 (Session 结束后再调整)   │
│   ❌ AI 在调试一个 bug (给它时间，它通常能自己解决)      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ REVIEW (人类主导, Session 完成后)                      │
│                                                     │
│ 1. 逐条检查验收标准                                   │
│ 2. 运行核心流程 (手动 smoke test)                     │
│ 3. 代码审查重点 (不需要逐行看，关注):                  │
│    - 架构: 模块划分是否合理?                           │
│    - 抽象: 接口设计是否可扩展?                         │
│    - 安全: 有没有硬编码密钥/明显漏洞?                  │
│    - 幂等: 爬取/调度是否考虑了失败重试?                │
│ 4. 记录需要修复的问题                                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ FIX (AI 修复, 同一 Session 或 追加 Session)           │
│                                                     │
│ 场景 A: 小问题 (同一 Session 继续)                    │
│   "验收标准第3条没通过，xxx 返回 500，请修复"          │
│                                                     │
│ 场景 B: 设计问题 (追加修复 Session)                   │
│   "AccountPool 没实现自动补充，请按 PRD 4.3.2 补全"   │
│                                                     │
│ 场景 C: 返工 (罕见，说明 Prompt 设计有问题)            │
│   回到 Phase 0 重新审视 PRD 对应章节                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ POST-FLIGHT (人类, 进入下一 Session 前)               │
│                                                     │
│ 1. 确认 Claude Code 已更新 CLAUDE.md                  │
│ 2. Git commit + tag (session-X-complete)             │
│ 3. 更新验收标准 checklist (打勾)                      │
│ 4. 回顾: 这个 Session 有什么教训?                     │
│    - Prompt 哪里不够清晰?                             │
│    - AI 在哪里走了弯路?                               │
│    - 下个 Session 的 Prompt 需要调整吗?               │
│ 5. (可选) 回到 Cowork 对话调整后续 Session Prompt      │
└─────────────────────────────────────────────────────┘
```

### 4.2 CLAUDE.md: 跨 Session 的共享大脑

CLAUDE.md 是 Harness Engineering 的核心基础设施。它是 AI 在每个新 Session 开始时恢复全部项目上下文的唯一入口。

**CLAUDE.md 应包含**:

```markdown
# GENPANO

## 项目概述
一句话说清楚这是什么。

## 技术栈
前端/后端/数据库/队列/部署 — 具体版本号。

## 目录结构
src/ 下每个模块的功能说明。

## 开发命令
启动、测试、构建、数据库迁移 — 可直接复制执行。

## 架构决策
关键的"为什么"：为什么自建 Playwright 不用 Browserbase、
为什么 Bottom-Up 不 Top-Down、为什么测试阶段单节点。

## 已知问题 / TODO
当前存在的问题和临时方案。

## Session 进度
已完成 Session 0-2，当前 Session 3。
```

**维护规则**:
- 每个 Session 结束时 Claude Code 必须更新 CLAUDE.md
- 人类在 POST-FLIGHT 阶段审查更新内容
- 如果 CLAUDE.md 过长 (>500 行)，拆分子文档 (docs/architecture.md 等)，CLAUDE.md 保留索引

### 4.3 Session 中断处理

当 Claude Code 的 context window 不够完成一个 Session:

```
中断时:
1. 让 Claude Code 输出进展总结:
   "请总结: 已完成的任务、正在进行的任务、剩余任务、当前代码状态"
2. 让 Claude Code 更新 CLAUDE.md

恢复时 (新 session):
┌────────────────────────────────────────────┐
│ 请阅读 CLAUDE.md 了解项目上下文。            │
│                                            │
│ 我们正在执行 Session X。                    │
│ 已完成: [从中断总结中复制]                   │
│ 请继续完成: [剩余任务]                       │
│                                            │
│ 验收标准 (参考 CLAUDE_CODE_SESSIONS.md):     │
│ [复制未完成的验收条目]                       │
└────────────────────────────────────────────┘
```

### 4.4 Session 间的反馈循环

这是 Harness Engineering 区别于"扔 Prompt 等结果"的关键:

```
Session N 完成
     │
     ▼
┌──────────────┐     ┌──────────────────────────┐
│ Review 发现   │ ──→ │  决策:                    │
│ AI 的选型不佳 │     │  A. 小修: 同 Session 修    │
│              │     │  B. 中修: 追加 Fix Session │
│              │     │  C. 大修: 回 Phase 0 调PRD │
└──────────────┘     └──────────────────────────┘
                              │
Session N+1 的 Prompt          │
根据 Review 发现调整 ◄─────────┘
```

**实际例子 (来自本项目)**:
- Phase 0 对话中发现"API-First 不对" → 修改 PRD → 影响 Session 1 Prompt
- Phase 0 对话中发现"需要双区域" → 重写部署架构 → 影响 Session 0 和 Session 5
- Phase 0 对话中发现"测试阶段用单节点" → 调整 Session 5 → 影响部署验收标准

这种反馈不是在 Session 执行中临时发生的，而是在 Pre-flight/Post-flight 阶段系统性地处理。

---

## 5. Phase 2: 测试验证 (人机协同)

**工具**: Claude Code + 人工测试
**角色分配**: AI 写测试和修 Bug，人做探索性测试和最终判断

### 5.1 测试策略

```
┌───────────────────────────────────┐
│  Layer 1: AI 自动测试 (Session内)  │
│  单元测试 + 集成测试               │
│  每个 Session 验收标准中已包含      │
└───────────────┬───────────────────┘
                │
┌───────────────▼───────────────────┐
│  Layer 2: 人工 Smoke Test         │
│  Session 完成后手动跑核心流程       │
│  注册→创建项目→爬取→查看Dashboard  │
└───────────────┬───────────────────┘
                │
┌───────────────▼───────────────────┐
│  Layer 3: 端到端验证 (Session 5后) │
│  全引擎爬取 + 全流程 + 边界情况    │
│  开一个专门的 Fix Session 修 Bug   │
└───────────────┬───────────────────┘
                │
┌───────────────▼───────────────────┐
│  Layer 4: Beta 用户验证            │
│  5-10个真实用户试用，收集反馈       │
│  反馈汇总后开迭代 Session          │
└───────────────────────────────────┘
```

### 5.2 Bug 修复 Session 模板

Session 5 完成后，几乎一定会有一个 Fix Session:

```
请阅读 CLAUDE.md。

以下是 MVP 端到端测试中发现的问题，请逐个修复:

## 严重 (必须修)
1. [具体问题描述 + 复现步骤 + 期望行为]
2. ...

## 一般 (尽量修)
3. ...

## 体验优化 (有时间就修)
4. ...

修复完成后请:
- 跑一遍相关测试确认不 regress
- 更新 CLAUDE.md 的已知问题列表
```

---

## 6. Phase 3: 上线运营 (持续 Harness)

上线后，Harness Engineering 不会停止，而是进入持续运营模式:

### 6.1 日常运维 Session

```
请阅读 CLAUDE.md。

检查以下运营指标:
1. 爬取成功率 (过去 24h 各引擎)
2. 账号池水位 (各引擎可用账号数)
3. API 响应时间 (P50/P95)
4. 异常日志

如有异常请诊断原因并修复。
```

### 6.2 迭代 Session

用户反馈和数据驱动的功能迭代，回到 Phase 0 → Phase 1 循环:

```
Phase 0 (Cowork):        分析反馈 → 确定优先级 → 更新 PRD
Phase 1 (Claude Code):   写代码 → Review → 部署
Phase 2 (测试):          验证 → 修复
```

---

## 7. Harness Engineering 反模式 (避坑)

### ❌ 反模式 1: 放任不管 ("扔 Prompt 等结果")

```
错误: 复制 Prompt → 去喝咖啡 → 回来发现 AI 跑偏了整个架构
正确: 保持在旁观察，关键分叉点及时介入
```

### ❌ 反模式 2: 过度干预 ("微管理 AI")

```
错误: AI 每写 10 行代码就打断 "为什么用 forEach 不用 map"
正确: 让 AI 保持完整上下文，Session 结束后统一 Review
唯一例外: 方向性错误要立即纠偏
```

### ❌ 反模式 3: 跳过 Phase 0 ("直接让 AI 写代码")

```
错误: "帮我做一个 GEO 监测工具" → 直接给 Claude Code
正确: 先用 Cowork 对话把 PRD 打磨到位 → 再给 Claude Code
Phase 0 投入的时间在 Phase 1 会十倍回报
```

### ❌ 反模式 4: 不更新 CLAUDE.md ("断裂的记忆")

```
错误: Session 3 发现 Session 1 的接口设计有问题，直接改了代码
      但 CLAUDE.md 还是旧的描述 → Session 4 的 AI 会懵
正确: 每个 Session 结束必须更新 CLAUDE.md，让它反映真实代码状态
```

### ❌ 反模式 5: Prompt 即兴创作 ("想到哪写到哪")

```
错误: 临时组装 Session 3 的 Prompt，遗漏 PANO Score 需求
正确: Phase 0 阶段就把所有 Session Prompt 设计好 + Review
```

### ❌ 反模式 6: 不回头修正 ("沉没成本")

```
错误: Phase 0 设计了 API-First，Session 1 执行后发现不对
      但因为"已经写了代码"不愿改
正确: 回到 Phase 0 纠偏，重新生成 Session Prompt
      代码是 AI 写的，重写的成本远低于人类手写代码
```

---

## 8. 资源估算

### 时间分配 (GENPANO 8-10 周 MVP, Python 反转后, 2026-04-26 重估)

> 决策 #29 (Python 反转) 后, MVP 由原 Next.js 单体 7 Session 重排为 11 Session × 4 Milestone (M1 Foundation / M2 Pipeline / M3 KG+Planner / M4 Analyzer+UI)。详见 `REPLAN_2026_04_26.md`。

| 阶段 | 人类时间 | AI 时间 | 总日历时间 |
|------|---------|---------|-----------|
| Phase 0 产品设计 (已完成) | — | — | (sunk cost) |
| **M1 Foundation** | | | |
| Session 0' 仓库基建 + CI/CD + preview env | 2h (Review) | 4-6h | 1.5 天 |
| Session A0' Admin 认证脚手架 (FastAPI + JWT) | 2h (Review) | 4-6h | 1.5 天 |
| Session 4a' 用户系统 + Onboarding | 2h (Review) | 3-5h | 1.5 天 |
| **M2 Pipeline** | | | |
| Session 1' Adapter 框架 + Parser (Camoufox/httpx) | 2h (Review) | 5-7h | 2 天 |
| Session 1.5' KG 冷启动 (LLM + dedupe + 关系边) | 2h (Review) | 4-6h | 1.5 天 |
| Session 1.2' MVP 3 引擎 Live (Camoufox + Luban) | 3h (Review) | 6-8h | 2 天 |
| **M3 KG + Planner** | | | |
| Session 2' Planner (Topic/Prompt/Query 三层) | 2h (Review) | 4-6h | 1.5 天 |
| Session 2.1' Planner LLM Refinement | 2h (Review) | 3-5h | 1 天 |
| Session 3' 分析引擎 + API + MCP Server | 3h (Review) | 5-7h | 2 天 |
| **M4 Analyzer + UI** | | | |
| Session A1' Admin 用户管理 + KG QA | 2h (Review) | 4-6h | 1.5 天 |
| Session 4b' Dashboard + 报告 (前端 IA v2.0) | 3h (Review) | 5-7h | 2 天 |
| Fix Sessions (跨 M1-M4) | 3-5h | 4-6h | 1.5-2 天 |
| **合计** | **~28-35h** | **~51-75h** | **~20-25 天 (8-10 周)** |

**人类的 25-35 小时主要花在**: 产品设计对话 (40%) + Code Review (30%) + 手动测试 (20%) + 环境/部署 (10%)

**人类几乎不花时间在**: 写代码、写文档、写测试、调试

---

## 9. Checklist: 每个 Session 的标准流程

```
PRE-FLIGHT ✈️
  □ 前置 Session 验收标准全部 ✅
  □ CLAUDE.md 是最新的
  □ Prompt 已根据实际情况调整
  □ 开发环境就绪 (DB, deps, env vars)
  □ Git 状态干净 (上个 Session 已 commit)

EXECUTION 🏃
  □ 复制 Prompt 粘贴给 Claude Code
  □ 观察执行，只在方向性错误时介入
  □ 记录可疑点 (不打断)

REVIEW 🔍
  □ 逐条检查验收标准
  □ 手动 Smoke Test 核心流程
  □ 代码审查 (架构、抽象、安全、幂等)
  □ 记录需修复的问题

FIX 🔧
  □ 小修: 同 Session 追问
  □ 中修: 开 Fix Session
  □ 大修: 回 Phase 0

POST-FLIGHT 🛬
  □ Claude Code 已更新 CLAUDE.md
  □ git commit + tag
  □ 验收 checklist 全部打勾
  □ 回顾教训，调整后续 Prompt (如需)
```

---

## 10. Agent 自动化与质量保障

### 10.1 核心问题: Echo Chamber

当 AI 写代码、AI 跑测试、AI 做 Review，最大风险是**回音室效应**: AI 的盲区无法被自身检测到。

```
Echo Chamber 示例:
  AI 写了一个 Parser → AI 写了测试 → 测试通过 ✅
  但是: Parser 漏处理了一种边界情况
  AI 写测试时也没想到这种情况 → 盲区一致 → 假阳性通过
```

**解法核心原则**: 用多个**不同视角**的验证层形成交叉覆盖，让任何单一盲区至少被另一层捕获。

### 10.2 三层质量保障架构

```
┌─────────────────────────────────────────────────────────┐
│                  Agent 自动化质量保障                      │
│                                                         │
│  Layer 1: 可执行验收 (Executable Acceptance)              │
│  ════════════════════════════════════════                │
│  把验收标准变成 shell 脚本/测试用例                        │
│  100% 自动化，每个 Session 必须全部 PASS                  │
│                                                         │
│  Layer 2: 对抗性验证 (Adversarial Verification)           │
│  ════════════════════════════════════════                │
│  独立 Agent 尝试"破坏"系统                               │
│  与 Executor Agent 完全隔离，不共享上下文                  │
│  目标: 找到 Layer 1 漏掉的问题                           │
│                                                         │
│  Layer 3: 规约对齐检查 (Spec Compliance)                  │
│  ════════════════════════════════════════                │
│  独立 Agent 对比 PRD ↔ 实际代码                          │
│  检测"代码能跑但不符合需求"的偏差                         │
│                                                         │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─                │
│  人类 Checkpoint: 只在关键节点介入                        │
│  Phase Gate Review + 异常升级                            │
└─────────────────────────────────────────────────────────┘
```

### 10.3 Layer 1: 可执行验收 (Executable Acceptance)

**原则**: 一切验收标准必须可被脚本自动验证。如果不能写成脚本，就不是好的验收标准。

**改造方法**: 把每个 Session 的验收标准转化为 `verify-session-X.sh`:

```bash
#!/bin/bash
# verify-session-1.sh — 爬取引擎 Session 验收 (Python pivot, 2026-04-26)
set -e

echo "=== Session 1' 验收 ==="

# 1. 结构验证: 必须存在的文件
echo "[Check 1] File structure..."
REQUIRED_FILES=(
  "src/scraping/browser_manager.py"
  "src/scraping/engines/chatgpt_adapter.py"
  "src/scraping/engines/doubao_adapter.py"
  "src/scraping/engines/deepseek_adapter.py"
  "src/scraping/account_pool.py"
  "tests/scraping/"
  "alembic/versions/"
)
for f in "${REQUIRED_FILES[@]}"; do
  [ -e "$f" ] || { echo "FAIL: Missing $f"; exit 1; }
done
echo "  PASS"

# 2. 接口合规: Adapter 必须继承 EngineAdapter ABC
echo "[Check 2] Interface compliance..."
grep -q "class.*EngineAdapter" src/scraping/engines/chatgpt_adapter.py \
  || { echo "FAIL: ChatGPT adapter missing base class"; exit 1; }
echo "  PASS"

# 3. 测试通过 (pytest)
echo "[Check 3] Unit tests..."
pytest tests/scraping/ -v --tb=short \
  || { echo "FAIL: Tests failed"; exit 1; }
echo "  PASS"

# 4. 数据迁移完整性: Alembic head 与 model 一致
echo "[Check 4] Alembic migration check..."
alembic check \
  || { echo "FAIL: Alembic migrations out of sync with models"; exit 1; }
echo "  PASS"

# 5. 功能验证: 实际执行一次爬取 (mock 模式)
echo "[Check 5] Smoke test..."
MOCK_MODE=true python -m src.scraping.smoke_test \
  || { echo "FAIL: Smoke test failed"; exit 1; }
echo "  PASS"

# 6. 安全检查: 无硬编码密钥
echo "[Check 6] No hardcoded secrets..."
! grep -rn "sk-[a-zA-Z0-9]" src/scraping/ \
  || { echo "FAIL: Hardcoded secrets found"; exit 1; }
echo "  PASS"

echo "=== All checks passed ✅ ==="
```

**关键点**:
- 验收脚本在 Phase 0 就设计好 (写进 CLAUDE_CODE_SESSIONS.md)
- Session Prompt 中要求 Claude Code 在完成后自行跑验收脚本
- 验收脚本与业务代码由不同的"时间点"产出: 脚本在 Phase 0，代码在 Phase 1

### 10.4 Layer 2: 对抗性验证 (Adversarial Verification)

**问题**: Layer 1 只能验证"有没有做到"，无法验证"有没有做错"。

**方案**: 启动一个**独立的 Agent Session**，只给它验收标准和代码访问权限，**不给它 Session Prompt** (避免和 Executor 共享思路)。

```
┌──────────────────────────────────────────────────────┐
│  Adversarial Agent Prompt 模板                        │
│                                                      │
│  你是一个代码安全审计员。                               │
│  请阅读 CLAUDE.md 了解项目背景。                       │
│                                                      │
│  现在审查 src/scraping/ 目录:                          │
│                                                      │
│  1. 错误处理审查:                                      │
│     - 列出所有没有 try-catch 的异步调用                 │
│     - 列出所有忽略了返回值的 Promise                    │
│     - 网络超时是否有合理的 fallback?                    │
│                                                      │
│  2. 边界情况:                                         │
│     - 空响应/null 值是否处理?                          │
│     - 并发竞争条件 (如账号池同时被两个 worker 取用)?     │
│     - 超长响应/超大 HTML 是否有内存保护?                │
│                                                      │
│  3. 安全:                                             │
│     - 有无注入风险 (拼接用户输入到 selector/XPath)?     │
│     - 代理/密钥是否在日志中泄露?                       │
│                                                      │
│  4. 资源泄露:                                         │
│     - Browser context 是否在 finally 中关闭?           │
│     - 是否有可能泄露 Playwright 进程?                  │
│                                                      │
│  对每个发现，给出: 文件、行号、严重级别 (P0-P3)、修复建议 │
│  输出到 review/session-X-adversarial.md                │
└──────────────────────────────────────────────────────┘
```

**为什么有效**: 对抗性 Agent 只看代码，不知道 Executor 的"设计意图"。它从**攻击者/SRE**的视角审查，这个视角与写代码时的**建设者**视角正交，能覆盖不同的盲区。

**检查清单模板** (按 Session 类型定制):

| Session 类型 | 对抗性审查重点 |
|---|---|
| 爬取引擎 (Python + Camoufox) | 资源泄露 (browser context 未 close / Playwright 进程残留), 并发安全 (asyncio task 取消传播, account_pool 取号竞态), 反检测绕过 (Camoufox stealth 配置 / humanize 鼠标轨迹 / fingerprint drift 是否被 wire 进 hot path), HAR sanitize (cookie/authorization header 是否真的脱敏, 测试 fixture 是否泄露 token), 错误恢复 (CAPTCHA 三级兜底是否真有兜底, COOKIE_EXPIRED 是否触发 cooldown) |
| 数据分析 (FastAPI + SQLAlchemy) | 计算正确性 (mention_rate 分母口径, sentiment 0.45/0.55 边界), 除零/空值 (空 query 集合 / 单引擎数据缺失), 浮点精度 (Decimal vs float 在金额字段), N+1 query (SQLAlchemy lazy load 是否引爆), 性能 (聚合查询是否走索引) |
| API/MCP (FastAPI) | 认证绕过 (Depends 是否真生效 / token 验证 short-circuit), 输入验证 (Pydantic v2 strict 模式, query param coercion), 速率限制 (slowapi key 是否唯一, Redis 不可达时 fail-open vs fail-close), 错误信息泄露 (ValidationError 是否吐内部字段名, HTTPException detail 是否带堆栈) |
| Dashboard (React + Vite) | XSS/CSRF, 响应式断裂, 状态一致性, 加载异常 (前端 stack 不变, 沿用 JSX) |
| 部署 (Docker + preview env) | 密钥管理 (.env 不进镜像, GitHub Actions secrets), 权限最小化 (容器 USER 非 root), 容器逃逸, 日志敏感信息 (httpx/httpcore 日志默认是否打 Authorization) |

### 10.5 Layer 3: 规约对齐检查 (Spec Compliance)

**问题**: 代码能跑、测试通过、安全也没问题——但它实现的不是 PRD 要求的东西。

**方案**: 专门的 Agent 拿着 PRD 对应章节逐条检查代码实现。

```
┌──────────────────────────────────────────────────────┐
│  Spec Compliance Agent Prompt 模板                    │
│                                                      │
│  你是产品经理助理，负责验证代码实现是否符合需求文档。     │
│                                                      │
│  请阅读以下文件:                                      │
│  1. PRD.md 的第 4.X 节 (对应本 Session 的需求范围)     │
│  2. src/ 下对应的实现代码                              │
│                                                      │
│  逐条对比 PRD 中的功能要求，输出:                      │
│                                                      │
│  | PRD 条目 | 是否实现 | 实现位置 | 偏差说明 |          │
│  |---------|---------|---------|---------|           │
│  | 4.2.1 多引擎 | ✅ | src/scraping/engines/ | — |  │
│  | 4.2.3 stealth | ⚠️ | browser_manager.py L45 |   │
│  |   用了 playwright 原生而非 Camoufox stealth |       │
│  | 4.3.2 账号池自动补充 | ❌ | — | Luban SMS 未接入 │
│                                                      │
│  重点检查:                                            │
│  - PRD 中标注为 P0 的功能是否全部实现                   │
│  - 数据模型是否与 PRD 定义一致                         │
│  - 接口命名/参数是否与 PRD 描述匹配                    │
│  - 非功能需求 (性能/限制) 是否满足                      │
│                                                      │
│  输出到 review/session-X-compliance.md                │
└──────────────────────────────────────────────────────┘
```

### 10.6 人类 Checkpoint: 最小化但不可消除

即使三层 Agent 验证全部通过，仍有**两类问题**只有人能判断:

```
┌─────────────────────────────────────────────────────┐
│  人类 Checkpoint 设计                                │
│                                                     │
│  频率: 不是每个 Session，而是每个 Phase Gate          │
│                                                     │
│  Gate 1: Session 0' 完成后 (基建+CI/CD 确认)          │
│    □ 技术选型是否合理? (FastAPI/SQLAlchemy/Alembic)   │
│    □ 目录结构是否清晰? (src/api / src/platform / ...) │
│    □ Platform/User 双层数据模型是否正确?              │
│    □ Preview env 一键部署可访问                       │
│    □ 阅读 review/ 中的 adversarial 报告              │
│    ⏱ ~30min                                        │
│                                                     │
│  Gate 2: Session 1.5' 完成后 (平台数据+爬取确认)      │
│    □ 爬取引擎核心流程是否通顺?                        │
│    □ 品牌/产品发现 pipeline 结果抽检                  │
│    □ 4 个行业数据图谱质量审核                         │
│    □ 亲手触发一次爬取看结果                           │
│    □ 阅读 review/ 中的 compliance 报告               │
│    ⏱ ~1h                                           │
│                                                     │
│  Gate 3: Session 3' 完成后 (分析引擎+API+MCP 确认)    │
│    □ Query 生成 + 分析引擎 + API 全链路通顺?          │
│    □ MCP Server 可用?                                │
│    □ PANO Score 计算合理?                            │
│    ⏱ ~45min                                        │
│                                                     │
│  Gate 4: Session A1' + 4b' 完成后 (产品体验确认)      │
│    □ Dashboard 看一遍: 交互是否合理?                  │
│    □ Onboarding: 选行业→立即看到品牌数据?             │
│    □ 作为用户跑一遍完整流程                           │
│    □ "这像一个我会用的产品吗?"                        │
│    ⏱ ~1h                                           │
│                                                     │
│  Gate 5: Preview env → Production 切换 (上线确认)     │
│    □ 部署是否正常?                                   │
│    □ 全引擎爬取跑一遍                                │
│    □ 平台采集 pipeline 连续 3 天稳定?                 │
│    □ 签字上线                                       │
│    ⏱ ~1h                                           │
│                                                     │
│  异常升级:                                           │
│  - 任何 Layer 报告 P0 问题 → 立即通知人类             │
│  - Adversarial Agent 发现 ≥3 个 P1 → 升级            │
│  - Compliance 检查有 PRD P0 功能未实现 → 阻断         │
└─────────────────────────────────────────────────────┘
```

**人类时间估算变化**:
| 模式 | 每 Session 人类时间 | 7 Session 合计 |
|------|-------------------|---------------|
| 全手动 Review | 2-4h | 14-28h |
| Agent 自动化 + Phase Gate | 0.5h (平均) + Gate 4h | ~7-8h |

节省约 50-70% 的人类审查时间，同时质量覆盖率更高 (三层交叉验证 > 单人 Review)。

### 10.7 自动化编排: Session 全自动流水线

当三层验证就位后，一个 Session 可以跑成流水线:

```
┌─────────────────────────────────────────────────────────┐
│  Agent Pipeline: 单个 Session 自动化流程                   │
│                                                         │
│  Trigger: 人类确认 "开始 Session X"                      │
│                                                         │
│  Step 1: Pre-flight Check (自动)                        │
│  ┌─────────────────────────────────┐                    │
│  │ □ 前置 Session tag 存在?         │                    │
│  │ □ CLAUDE.md 最后修改时间正确?     │                    │
│  │ □ verify-session-(X-1).sh PASS? │                    │
│  │ □ Git clean?                    │                    │
│  └─────────────┬───────────────────┘                    │
│                │ 全部 PASS                               │
│  Step 2: Execution (Claude Code Agent)                  │
│  ┌─────────────▼───────────────────┐                    │
│  │ 使用 Session X Prompt 执行       │                    │
│  │ 预计 3-6h                       │                    │
│  └─────────────┬───────────────────┘                    │
│                │ 完成                                    │
│  Step 3: Layer 1 — 可执行验收 (自动)                     │
│  ┌─────────────▼───────────────────┐                    │
│  │ bash verify-session-X.sh        │                    │
│  └─────────────┬───────────────────┘                    │
│                │ PASS                                    │
│  Step 4: Layer 2 — 对抗性验证 (独立 Agent)               │
│  ┌─────────────▼───────────────────┐                    │
│  │ 新 Claude Code Session          │                    │
│  │ Prompt = adversarial-X.md       │                    │
│  │ 输出 → review/session-X-adv.md  │                    │
│  └─────────────┬───────────────────┘                    │
│                │                                        │
│  Step 5: Layer 3 — 规约对齐 (独立 Agent)                 │
│  ┌─────────────▼───────────────────┐                    │
│  │ 新 Claude Code Session          │                    │
│  │ Prompt = compliance-X.md        │                    │
│  │ 输出 → review/session-X-comp.md │                    │
│  └─────────────┬───────────────────┘                    │
│                │                                        │
│  Step 6: 结果汇总 & 决策                                 │
│  ┌─────────────▼───────────────────┐                    │
│  │ 有 P0? → 自动开 Fix Session      │                    │
│  │ P1 ≥ 3? → 升级给人类             │                    │
│  │ 全部 OK → git commit + tag       │                    │
│  │         → 触发下一个 Session      │                    │
│  └─────────────────────────────────┘                    │
│                                                         │
│  Phase Gate? → 暂停，等待人类 Review                     │
└─────────────────────────────────────────────────────────┘
```

### 10.8 Fix Loop: 自动修复 + 收敛保护

当验证发现问题，自动修复需要防止无限循环:

```
问题发现
    │
    ▼
┌──────────────────┐
│ 分级:             │
│ P0 → Fix Session │
│ P1 → Fix Session │
│ P2 → 追加到同     │
│      Session      │
│ P3 → 记录到       │
│      backlog      │
└────────┬─────────┘
         │
    ┌────▼────┐
    │ Fix     │──→ 重新跑 Layer 1-3
    │ Session │
    └────┬────┘
         │
    ┌────▼────────────────────────┐
    │ 收敛检查:                    │
    │ - Fix 轮次 ≤ 3 → 继续自动   │
    │ - Fix 轮次 > 3 → 升级人类   │
    │   (说明问题超出 AI 能力)     │
    │ - 新引入的 P0 → 立即升级人类 │
    └─────────────────────────────┘
```

**Anti-Pattern: 无限修复循环**
```
Fix 1: 修了 A，引入了 B
Fix 2: 修了 B，引入了 C
Fix 3: 修了 C，A 又回来了
→ 三轮未收敛 → 升级人类，说明底层设计可能有问题
```

### 10.9 Agent 自动化质量保障 Checklist

```
设计阶段 (Phase 0):
  □ 每个 Session 的验收标准都可以转为 verify-session-X.sh
  □ 每个 Session 都有对应的 adversarial prompt 模板
  □ 每个 Session 都有对应的 compliance prompt 模板
  □ Phase Gate 节点已确定
  □ 升级规则明确 (什么问题需要人类介入)

执行阶段 (Phase 1):
  □ Pipeline 按 Step 1-6 顺序执行
  □ 三层验证结果都保存在 review/ 目录
  □ Fix Loop 不超过 3 轮
  □ Phase Gate 处人类完成审查

运营阶段:
  □ 回顾每个 Session 的验证命中率 (哪层发现了真问题)
  □ 持续优化 adversarial prompt (加入新发现的盲区类型)
  □ 验收脚本随代码演进更新
```
