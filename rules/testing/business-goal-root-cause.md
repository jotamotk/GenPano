---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Review]
hardness: SOFT
---

# Business Goal And Root Cause Gates

**Why**：仅修复可见错误状态不等于解决业务问题。事故记录见 [rules/INCIDENTS.md](../INCIDENTS.md)。

## Rule

第一目标是 issue 的业务目标。**仅改变可见错误状态的 fix 不算完成。**

### Issue/Epic 必填项（拆分子任务前）

Human Input 与 Epic issue 在拆分子任务前必须陈述：
- `Business Goal`
- `Final Success Evidence`
- `What Does NOT Count As Done`

### Incident PR 必过的 Root Cause Gate

- Direct trigger（直接触发）
- Underlying product/system root cause（底层根因）
- Evidence proving it（证据）
- Alternatives ruled out（已排除的备选）
- Remaining unknowns（残余未知）
- Why this fix produces the final business outcome（为什么本 fix 能交付业务结果）

### 根因未明时

PR 只能标记为 `diagnostics/instrumentation only`；**不要呈现为 incident 的 fix**。

### Review 必含 Failure-Chain Review

- 为什么这件事发生？
- 为什么先前的 guard 失效？
- 为什么本 fix 能达到业务目标？
- 下一个可能的失败是什么？
- 什么样的 live 证据证明成功？

### Live 重试预飞行检查

Live retry 或其他 live budget 花费要预飞行：
- 当前 row / object 状态
- Retry 计数或等价预算
- Account / session 状态（相关时）
- 操作后果
- 预期最终证据
- 下层失败时的 fallback

### 完成语言只有三态

- `Business success proven`
- `Diagnostic progress only`
- `Blocked / decision needed`

## Cross-references

- [rules/testing/evidence-first-debug.md](evidence-first-debug.md)
- [rules/testing/acceptance-evidence.md](acceptance-evidence.md)
- [rules/security/enforcement.md](../security/enforcement.md) —— CI lint 检测 Root Cause Gate 字段
