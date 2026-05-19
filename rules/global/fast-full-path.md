---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead]
hardness: SOFT
---

# Fast Path And Full Path

**Why**：不是每个请求都需要 Epic → Frontend Visualization → PRD → split issues。

## Rule

### Fast Path 使用条件（bug fix 或小改进，且全部满足）

- 影响一个产品或工程领域
- 不改 PRD requirement / public contract / schema / migration / deployment 架构
- 有清晰的 reproduction 或 acceptance check
- 一个 issue / 一个 branch / 一个 PR 能完成

### Full Path 触发条件（任一为真）

- 新的 user-facing workflow 或材料级 UX 方向
- PRD requirement / 产品 contract 可能改变
- API / database / migration / scheduler / worker / CI/CD / deployment contract 跨领域改动
- 多个 deliverable 必须排序
- release 风险高或 rollback 路径不清

Full Path 可用 Epic、PRD linkage、Frontend Visualization、多个 deliverable issue。
**Fast Path 不应创建这些 artifact，除非它们服务于该具体 fix。**

## Cross-references

- [rules/documentation/issue-pr-prd-contract.md](../documentation/issue-pr-prd-contract.md)
