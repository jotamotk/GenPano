---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead]
hardness: SOFT
---

# Issue Closure

**Why**：关闭原因明确能让未来 audit 看清"为什么这个 issue 结束"。

## Rule

关闭 issue 时使用以下 closure type 之一：

| 类型 | 适用 | Codex 是否可关 |
|---|---|---|
| `Human Input Accepted` | 用户接受 online 结果并关闭，或显式委托关闭 | **不可**自动关，除非用户显式委托 |
| `Completed` | 链接 PR / commit / acceptance 结果 / verification evidence / live evidence | 可在 verification 通过后关 |
| `Won't Do` | 原因 / 决定人 / 接受的风险 / 备选路径 | 需 product owner 确认，除非是 Codex 误建的明显重复 |
| `Split/Superseded` | 替代 issue 链接 / 哪部分 scope 去了哪 / 本 issue 不再拥有什么 | product scope 改时优先 product owner 确认 |
| `Duplicate` | canonical issue 链接 + 为什么完全覆盖 | 完全重叠时可关；否则先问 |

## Cross-references

- [rules/documentation/issue-writing.md](issue-writing.md)
- [rules/documentation/human-input-channel.md](human-input-channel.md)
