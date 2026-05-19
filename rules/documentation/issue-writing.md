---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [all]
hardness: SOFT
---

# Issue Writing Standard

**Why**：issue 是任务控制面板，不是聊天室。三周后再看仍应有用。

## Rule

- 每个 substantive issue comment 以**结论**开头，然后 evidence，然后 next action
- 用前缀作为写作辅助，**不是官僚**：
  `QUESTION` / `DECISION` / `BLOCKER` / `STATUS` / `PRD-CHANGE` / `EVIDENCE`

### 前缀语义

- `QUESTION`：**一次问完**所有已知 clarifying question，并陈述无答时的默认假设
- `BLOCKER`：陈述何处被阻、影响、选项、谁/什么能解阻
- `STATUS`：**仅**用于 material 状态改变。不发不改变当前状态 / 风险 / 决策 / 下一步的过程叙述
- `DECISION`：仅记录已定决策；issue body 有 `## Decisions` 节时必须 copy 进去
- `PRD-CHANGE`：陈述 PRD 文本 / 观察到的代码或产品现实 / 冲突 / 向 product owner 请求的决定
- `EVIDENCE`：记录确切证据：PR / run URL / commit SHA / route / request id / 截图 / Playwright
  trace / 服务器诊断 / API readback

### 完成语言（三态）

- `Business success proven` —— 最终业务 artifact / readback 已在
- `Diagnostic progress only` —— 观测性改善但业务结果未证
- `Blocked / decision needed` —— 根因 / acceptance / 安全下一步不确定

### Comment 自检

发 comment 前自问：核心判断是什么？支持证据？什么变了？下一步？

## Cross-references

- [rules/documentation/issue-pr-prd-contract.md](issue-pr-prd-contract.md)
- [rules/documentation/issue-closure.md](issue-closure.md)
