---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Implementation, QA]
hardness: SOFT
---

# Evidence-First Debugging

**Why**：基于代码假设的诊断会绕远路 —— 多个事故验证过，详 [rules/INCIDENTS.md#905](../INCIDENTS.md#905)。

## Rule

任何根因排查的第一步必须是从坏掉的 surface 直接抓真实响应/输出作为硬证据，并
`grep` 全部调用者验证 live test 环境实际走的代码路径。**禁止以"读代码推断行为"或
"假设端点走某段 SQL/handler"替代直接观察。**

诊断标签（如 `_profile_state="query_profile_id_null"`）不是代码 gate；相关性不是因果。
必须验证实际控制流。

## Minimum Evidence Checklist（开 PR 前必跑）

1. **Capture**：抓取（或向用户索取）坏掉 surface 的实际响应 —— API JSON / 日志行 /
   渲染文本截图 / DB 行，相应的那种。**贴到 issue 或 PR body**。
2. **Grep callers**：`grep` 你怀疑的 function/handler/formatter 的每个调用者；不要
   假设单个 endpoint 服务该 surface。
3. **Read live env code path**：阅读 *live test 环境* 实际执行的 SQL / 代码路径，
   不是你认为它执行的。
4. **State cause-and-effect**：显式陈述假定的因果链，然后指向证据确认每一环。

未走完这 4 步的"行为推断"是 hypothesis，不是 diagnosis。**不要在 hypothesis 上 ship fix**。

## Cross-references

- [rules/testing/evidence-first-shipping.md](evidence-first-shipping.md) —— 契约改动的对称版本
- [rules/testing/business-goal-root-cause.md](business-goal-root-cause.md) —— Root Cause Gate
