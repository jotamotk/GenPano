---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [all]
hardness: SOFT
---

# Real Agent Topology

**Why**：诚实抽象——多个 hat 是同一 agent 在切角色，不要演假交接戏。

## Rule

- 只有一个 coordinator 在不同时刻戴不同 hat。**named agent role 是责任视图，不是独立的人**
- 不要按 agent role 拆 issue；按 deliverable 拆——一个 issue 应对应一个 user-visible 或
  engineering outcome，能被 accept 或 close
- **Lead hat 不写业务代码**。它可维护协调 artifact：PRD、GitHub issue、PR review comments、
  merge plans、verification plans、workflow docs
- Codex 只能在 issue 有清晰 execution contract 后，切到 implementation / QA / review /
  release hat。**不要假装发生了向独立 agent 的 handoff**，当同一个 coordinator 仍在继续工作
- pruning hat 是减法视图：定期问什么可以删 / 退役，但**报告候选**，不要由自动化直接删
- 并行或重叠工作中，Lead hat 拥有 CD 协调：有意排序 live test-environment deploy，
  监控重叠的 Build & Deploy run，安全时取消被替代的 deploy run，验证最终 live env 跑的是
  intended 的最新 `main` SHA

## Cross-references

- [rules/global/peer-review.md](peer-review.md) —— hat 自循环 bias 的解药
- [rules/global/orchestrator-discipline.md](orchestrator-discipline.md)
