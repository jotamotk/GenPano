---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead]
hardness: SOFT
---

# Human Input Channel

**Why**：Human Input 是用户的 durable 入口 + 最终 acceptance issue，不是 worker task / branch /
PR / PRD 本身。

## Rule

- **Lead hat 负责 triage**：把每条 raw item 分类为 `bug` / `feature change` / `new requirement` /
  `question/idea` / `needs clarification`
- Lead hat 必须确认 Human Input 的 `Business Goal` / `Final Success Evidence` /
  `What Does NOT Count As Done`。任一不清楚 → 在路由实施前发 `HUMAN DECISION NEEDED`
- Lead hat 必须把可执行的 Human Input 拆为一个或多个 executable issue：Fast Path issue /
  Full Path coordination issue / PRD-change request / scoped deliverable issue。每个子 issue
  用 `Refs #<human>` 链回
- Human Input 仅在 triage disposition 或 issue `DECISION` 记录了 accepted 用户 intent 后，
  才能成为 acceptance source
- **Codex 不得**直接基于含糊的 Human Input note 实施
- Lead hat 调度并协调所需 hat，直到子工作 merge、deploy、在相关 live route 验证
- 最终交付 = `Ready for User Acceptance` comment on Human Input issue with：
  live URL / user-visible 结果 / PR / deploy SHA / Playwright 或 live evidence / 已知 caveat
- **Human Input issue 保持开放**，直到用户能验证 online 结果。用户接受则关闭；
  Agent 仅在用户显式委托关闭时关

参考完整 SOP：[docs/AI_LEAD_WORKFLOW.md](../../docs/AI_LEAD_WORKFLOW.md)。
Claude Code 协作：[docs/AI_LEAD_CLAUDE_COLLABORATION.md](../../docs/AI_LEAD_CLAUDE_COLLABORATION.md)。

## Cross-references

- [rules/documentation/issue-closure.md](issue-closure.md)
- [rules/global/codex-coordination.md](../global/codex-coordination.md)
