---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [all]
hardness: HARD
---

# Issue, PR, And PRD Contract

**Why**：契约是 CI 拦截的依据。详 [rules/security/enforcement.md](../security/enforcement.md)。

## Rule

### Issue 强制

- 任何 problem / incident / bug / 需求 gap / blocker / release 风险 / workflow gap 报告给 Codex，
  必须在 GitHub 捕获为新 issue 或链到已有 issue，**然后才能继续 durable 工作**
- 每个 issue 必须使用共享 priority taxonomy：1 个必填 `Priority`、1 个必填 `Priority Rationale`、
  恰好 1 个匹配 label：`priority:p0` / `priority:p1` / `priority:p2` / `priority:p3`
- **issue body = 当前事实源**；comment = draft 讨论 + audit trail。状态变化时保持
  `## Current State` 与 `## Decisions` current

### Downstream Issue

必须 inline execution contract。**不要**依赖未解的 pointer（如仅写 `depends on #<NNN>`）作为
唯一 scope 来源。

execution contract 应含：Goal / Path（fast 或 full）/ Owner Hat / Parent Business Goal /
Allowed Scope / Forbidden Scope / Contract Snapshot / Acceptance Matrix / Root Cause Gate /
Failure Chain Review / Verification Evidence Ledger / Dependencies / Handoff（相关时）。

### PRD

PRD 是 product-owner-approved facts。**实施中发现 PRD 问题 → Codex 必须请求 `PRD-CHANGE`；
不得静默改写 PRD intent。**

### PR 必须含

- Linked Issue
- Owner Hat
- Summary
- Scope
- Acceptance Matrix status
- Verification Evidence Ledger
- Test Integrity Statement
- Risks
- Handoff
- PRD Coverage（涉及产品行为时）

### 引用习惯

- `Refs #<NNN>`：最终 acceptance 前
- `Closes #<NNN>`：仅当 issue closure path 被 approve

### 冲突

issue text 描述 intent；代码 + live behavior 描述 reality。**冲突时 stop，在 issue 提出。**

## Cross-references

- [rules/security/enforcement.md](../security/enforcement.md) —— CI lint 的实际字段名
- [rules/testing/business-goal-root-cause.md](../testing/business-goal-root-cause.md)
- [rules/testing/acceptance-evidence.md](../testing/acceptance-evidence.md)
