---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Implementation]
hardness: SOFT
---

# Orchestrator And Subagent Discipline

**Why**：subagent 不继承 AGENTS.md，只看 orchestrator 写的 prompt。这是先前 bug 突破所有规则
之处——orchestrator 写了带 hypothesis 的 prompt，subagent 当事实执行。详 [rules/INCIDENTS.md#905](../INCIDENTS.md#905)。

## Rule

1. **首次 dispatch = investigate-only**：bug-fix 任务第一次 subagent 调用必须产出证据
   （broken-surface output、live env code path、grep callers），**不是代码**。第一次调用
   withhold Edit/Write 工具权限。用 `Explore` subagent 或在 subagent 定义里限制 `tools:`。

2. **Prompt 必须引用本仓库规则**：每个 bug-fix / incident / contract-changing 任务的
   subagent prompt **必须包含字面字符串 "AGENTS.md"** + 相关章节名（例："Read AGENTS.md
   Evidence-First Debugging before proceeding"）。省略即非合规，无论结果如何。**CI 抓不到这个，
   orchestrator 自己负责**。

3. **不要 pre-bake hypothesis**：反例 `"The bug is at foo.py:42; fix it."` 把调查折叠为命令，
   是先前事故复发原因。合规：`"User reports <symptom>. Capture broken-surface evidence,
   grep callers, identify live code path. Do not edit code."` 陈述症状与未知，不是原因。

4. **二次失败递归 revert**：若 subagent 输出产生了被用户 reject 的 PR，orchestrator 必须
   revert 该 subagent 的改动再 dispatch 后续——不要用另一个 subagent 往前打补丁。
   这是 Hard Rule 5 在 orchestration 层的应用。

5. **Skills 是首选载体**：当同一个 prompt 模式反复出现（evidence capture / PR body composition /
   safe subagent dispatch），把它包装为 `.claude/skills/` 里的 skill，让规则随调用走，
   不依赖 orchestrator 记忆。Skill 不替代 CI——它提升合规率，不主张自己是 gate。

## 失败模式（这条规则预防的）

orchestrator 略读 AGENTS.md，dispatch 一个 subagent 带 `"fix the timeout bug at scraper.py:88"`，
subagent 改一行，PR 开出，lint 过了因为 orchestrator 手填 ledger 同样基于 hypothesis。
**CI 无法检测 hypothesis-grounded ledger。只有 orchestrator 能。**

## Cross-references

- [rules/global/peer-review.md](peer-review.md) —— 高风险决策的 peer subagent 强化
- [rules/testing/evidence-first-debug.md](../testing/evidence-first-debug.md)
