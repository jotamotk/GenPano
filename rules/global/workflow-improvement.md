---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead]
hardness: SOFT
---

# Workflow Improvement Notes

**Why**：流程摩擦应被表达，但在提议规则变更前先分类——避免反射性加规则。

## Rule

Codex 应主动暴露 process friction，但**先分类再提议改规则**：

| 类型 | 描述 |
|---|---|
| `Efficiency` | 重复低价值工作、等待、模板噪音、重复状态更新 |
| `Constraint` | gate / forbidden scope / approval 步骤感觉过严。**怀疑地对待**，解释该约束预防了什么风险 |
| `Reliability` | 减少遗漏证据 / 过期状态 / 错误关闭 的改动 |
| `Topology Correction` | 规则假设多个独立 agent，而真实拓扑是一个 coordinator 戴 hat |

小笔记可进 governance / process issue。**未经 accepted issue 或显式用户指令，不要改 workflow 规则。**

## Cross-references

- [rules/MAINTENANCE.md](../MAINTENANCE.md) —— 规则变更流程
- [rules/global/agent-topology.md](agent-topology.md)
