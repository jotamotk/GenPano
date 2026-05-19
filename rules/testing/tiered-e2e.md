---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, QA]
hardness: SOFT
---

# Tiered E2E

**Why**：E2E 在证明 acceptance claim 处必跑，但应有 scope。

## Rule

| Tier | 范围 |
|---|---|
| **Tier 0** | 静态检查、unit tests、contract tests、touched layer 的 focused backend/frontend tests |
| **Tier 1** | 针对 exact reported bug 或 changed user path 的 User-Symptom Replay。**Fast Path 的默认 UI-visible E2E** |
| **Tier 2** | 当 frontend / backend / auth / scheduler / worker / deployment 边界交互时，相邻契约的 focused smoke |
| **Tier 3** | 高风险变更的完整 Playwright / release-gate E2E：多 PR release、主用户工作流、迁移、auth、scheduler、worker、live 部署 gate |

## 反例

- **不要**在更小的 replay 已能证明 claim 时跑完整 E2E 作为仪式
- **不要**跳过 targeted replay，用无关的绿色测试替代

## Cross-references

- [rules/testing/acceptance-evidence.md](acceptance-evidence.md)
