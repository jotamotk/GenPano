---
last-reviewed: 2026-05-19
owner-hat: Pruning
next-review-by: 2026-11-19
status: active
applies-to: [Pruning, Lead]
hardness: SOFT
---

# Pruning Automation

**Why**：每次新增容易累积，减法不会自然发生——需要专门的视图。

## Rule

Codex 应有定期 pruning automation，**输出 report，不是 patch**。其工作是问什么可以移除：
debug 脚本、legacy 目录、dead code、未用 prototype、stale runbook、过时 issue template、
过时 AGENTS.md / rules/ 规则。

### Pruning Automation 输出格式

- 输出 `Pruning Report` 发到 governance 或 pruning inbox issue
- 每个候选必含证据：reference search / workflow 或 CI 使用 / docs 链接 / 开放 issue/PR
  依赖 / owner（已知时）/ rollback 或 restore 路径
- 推荐之一：`Delete` / `Keep` / `Replace` / `Needs Decision`

### 自动化禁止

- 自动化**不能**删文件
- 自动化**不能**关 issue
- 自动化**不能**改 workflow 规则

### 处理流程

- 低风险 docs / debug cleanup 可成 Fast Path issue
- runtime / CI / migration / data repair / live runtime path / 产品行为移除 → 范围 issue +
  显式 verification
- **首选真删，优于 archive 目录**——git history 已能恢复 artifact
- 仅当 compliance / audit / active incident evidence 需要时才 archive

## Cross-references

- [rules/MAINTENANCE.md](../MAINTENANCE.md) —— 弃用 ≥ 新增 约束
- [rules/global/workflow-improvement.md](workflow-improvement.md)
