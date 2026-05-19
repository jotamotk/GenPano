---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Implementation, Review]
hardness: SOFT
---

# Evidence-First Shipping

**Why**：测试绿 ≠ 跨边界契约对齐 —— 详 [rules/INCIDENTS.md#948-960](../INCIDENTS.md#948-960)。

## Rule

改动跨边界的值（API field、enum、schema、URL param、contract status）时，**不要 merge
直到手动追踪一个真实值穿过 consumer**。

backend + frontend 测试套件都过了，不意味着 consumer gate 接受 producer 的新值。

## Minimum Evidence in PR Body Before Merge

至少一组 producer-consumer trace：

- producer 发出的一个新值：`<actual value>`
- consumer 对该输入的返回：`<actual return>`
- **粘贴**，不要假设

如果存在多个 consumer：重复，或引用 grep 证明一个 consumer 覆盖了新值集合中的所有值。

**贴不出这个 trace，PR 就没准备好 merge。**

## Cross-references

- [rules/testing/evidence-first-debug.md](evidence-first-debug.md) —— 反向（bug fix）版本
- [rules/testing/acceptance-evidence.md](acceptance-evidence.md) —— 验证证据格式
