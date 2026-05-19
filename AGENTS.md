# AGENTS.md — Repository contract for ALL agents

Canonical entry for Claude / Codex / Cursor / Aider / Devin / 人类。Agent 专属配置
（`CLAUDE.md` / `.cursorrules` / `.codex/` 等）**只指向本文件，不复制规则**。

明细规则按关注点拆到 [`rules/`](rules/) 子目录，每条规则单独成文件。维护流程与反 context 中毒
约束见 [`rules/MAINTENANCE.md`](rules/MAINTENANCE.md)。

---

## 0. Agent 开场约定

任何 agent 第一次响应前自报当前 hat：`Lead` / `Implementation` / `QA` / `Review` /
`Release` / `Pruning`。切换 hat 时显式声明。本规则对齐每条规则 frontmatter 的 `applies-to` 字段。

---

## 1. 项目目标

- **产品**：追踪 LLM（Doubao / ChatGPT / Gemini / DeepSeek …）如何谈论品牌
- **协作目标**：速度 + 可回滚；GitHub issue/PR 是事实源，chat 不是
- **不变量**：本文件 + `rules/` 是 canonical；CI 是唯一硬 gate

---

## 2. 协作原则（Hard Rules — 必读 6 条）

1. **EVIDENCE BEFORE CODE** — 详 [rules/testing/evidence-first-debug.md](rules/testing/evidence-first-debug.md)
2. **DB ACCESS IS AVAILABLE VIA CI/CD** — 用 readonly workflow，不用"没权限"借口
3. **DO NOT SHIP ON HYPOTHESIS** — 详 [rules/testing/evidence-first-debug.md](rules/testing/evidence-first-debug.md)
4. **TEST PASSING != BUG FIXED** — 至少一个 fixture 绑真值，详 [rules/testing/acceptance-evidence.md](rules/testing/acceptance-evidence.md)
5. **SECOND FAILED ITERATION → FULL REVERT** — 详 [rules/global/orchestrator-discipline.md](rules/global/orchestrator-discipline.md)
6. **ORCHESTRATOR DISCIPLINE** — 详 [rules/global/orchestrator-discipline.md](rules/global/orchestrator-discipline.md)

---

## 3. 规则索引（按关注点）

| 关注点 | 子目录 | 何时读 |
|---|---|---|
| 全局/工作流 | [rules/global/](rules/global/README.md) | 所有任务起点 |
| 前端 | [rules/frontend/](rules/frontend/README.md) | 改 `frontend/` 或 Admin UI |
| 后端 | [rules/backend/](rules/backend/README.md) | 改 `backend/` 或 `/admin/api/*` |
| 测试与证据 | [rules/testing/](rules/testing/README.md) | 改 bug / 写 PR 之前 |
| 安全与执行 | [rules/security/](rules/security/README.md) | CI / 秘密 / 不可绕过 gate |
| 文档/issue/PR | [rules/documentation/](rules/documentation/README.md) | 写 issue / PR / PRD |

各子目录有 `README.md` 列具体规则。补充：

- [rules/INCIDENTS.md](rules/INCIDENTS.md) — war story 与 PR timeline
- [rules/MAINTENANCE.md](rules/MAINTENANCE.md) — 维护流程 / 反中毒约束 / Cross-agent Consistency Contract

---

## 4. 三层强制模型

- **L1（hard gate）**：`.github/workflows/pr-body-lint.yml` — 所有 agent 必过
- **L2（feedback）**：`issue-body-lint.yml` — web UI 强制，API 提醒
- **L3（best-effort）**：各 agent carrier（hook / 配置文件） — 取决于 agent 是否真读

详 [rules/security/enforcement.md](rules/security/enforcement.md) +
[rules/MAINTENANCE.md `Cross-agent Consistency Contract`](rules/MAINTENANCE.md#5-cross-agent-consistency-contract)。

---

## 5. 维护

变更规则前必读：[rules/MAINTENANCE.md](rules/MAINTENANCE.md)。

元 lint：`python3 scripts/lint_rules.py rules/`（CI workflow `rules-lint.yml` 自动跑）。

---

## 6. Hard Rule Digest

`.claude/hooks/session-start.sh` 用 awk 从此块抽取注入到 session 上下文。
**禁止 hook 脚本里手写硬规则。** 改本块前跑 `bash .claude/hooks/session-start.sh` smoke。

<!-- DIGEST-BEGIN -->
1. EVIDENCE BEFORE CODE. 抓真实输出再写代码。file:line 不是证据。
2. DB ACCESS IS AVAILABLE VIA CI/CD. 用 readonly workflow，不用"没权限"借口。
3. DO NOT SHIP ON HYPOTHESIS. 4 步证据链跑不下来 → BLOCKED。
4. TEST PASSING != BUG FIXED. 至少一个 fixture 绑真值。
5. SECOND FAILED ITERATION → FULL REVERT. 第三次前先回滚。
6. ORCHESTRATOR DISCIPLINE. 首次 dispatch 仅 investigate；子 agent prompt 必须含 "AGENTS.md"。
<!-- DIGEST-END -->

---

## 7. 旧章节名 → 新路径（兼容老 PR/issue 引用）

老 PR / issue / commit message 中引用 `AGENTS.md ### Foo` 形式的章节，按下表跳转：

| 旧引用 | 新路径 |
|---|---|
| `AGENTS.md ### Evidence-First Debugging` | [rules/testing/evidence-first-debug.md](rules/testing/evidence-first-debug.md) |
| `AGENTS.md ### Business Goal And Root Cause Gates` | [rules/testing/business-goal-root-cause.md](rules/testing/business-goal-root-cause.md) |
| `AGENTS.md ### Evidence-First Shipping` | [rules/testing/evidence-first-shipping.md](rules/testing/evidence-first-shipping.md) |
| `AGENTS.md ### Orchestrator And Subagent Discipline` | [rules/global/orchestrator-discipline.md](rules/global/orchestrator-discipline.md) |
| `AGENTS.md ## Enforcement` | [rules/security/enforcement.md](rules/security/enforcement.md) |
| `AGENTS.md ### Acceptance And Verification Evidence` | [rules/testing/acceptance-evidence.md](rules/testing/acceptance-evidence.md) |
| `AGENTS.md ### Tiered E2E` | [rules/testing/tiered-e2e.md](rules/testing/tiered-e2e.md) |
| `AGENTS.md ### Issue Writing Standard` | [rules/documentation/issue-writing.md](rules/documentation/issue-writing.md) |
| `AGENTS.md ### Issue, PR, And PRD Contract` | [rules/documentation/issue-pr-prd-contract.md](rules/documentation/issue-pr-prd-contract.md) |
| `AGENTS.md ### Issue Closure` | [rules/documentation/issue-closure.md](rules/documentation/issue-closure.md) |
| `AGENTS.md ### Human Input Channel` | [rules/documentation/human-input-channel.md](rules/documentation/human-input-channel.md) |
| `AGENTS.md ### Fast Path And Full Path` | [rules/global/fast-full-path.md](rules/global/fast-full-path.md) |
| `AGENTS.md ### Workflow Improvement Notes` | [rules/global/workflow-improvement.md](rules/global/workflow-improvement.md) |
| `AGENTS.md ### Pruning Automation` | [rules/global/pruning-automation.md](rules/global/pruning-automation.md) |
| `AGENTS.md ### Real Agent Topology` | [rules/global/agent-topology.md](rules/global/agent-topology.md) |
| `AGENTS.md ## Codex Coordination Workflow` | [rules/global/codex-coordination.md](rules/global/codex-coordination.md) |
| `AGENTS.md ## Admin Surface Rule` | [rules/frontend/admin-surface.md](rules/frontend/admin-surface.md) |
| `AGENTS.md ## Current Admin Boundary` | [rules/backend/admin-boundary.md](rules/backend/admin-boundary.md) + [rules/frontend/admin-frontend-workflow.md](rules/frontend/admin-frontend-workflow.md) |
| `AGENTS.md ## Admin Frontend Workflow` | [rules/frontend/admin-frontend-workflow.md](rules/frontend/admin-frontend-workflow.md) |
| `AGENTS.md ## Admin Product Terms` | [rules/frontend/admin-product-terms.md](rules/frontend/admin-product-terms.md) |
