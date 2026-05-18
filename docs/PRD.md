---
status: superseded
last_verified: 2026-05-18
supersedes: archive/PRD-v1.3-2026-04-15.md
owner: docs-maintenance
---

# PRD — Stub（旧 PRD 已归档）

> ⚠️ **Stop.** 旧的 `docs/PRD.md` (v1.3, 2026-04-15, 500KB) 已经严重脱离产品现状，不再是事实来源。完整历史副本已迁移到 [`docs/archive/PRD-v1.3-2026-04-15.md`](archive/PRD-v1.3-2026-04-15.md)。
>
> 本文件保留在 `docs/PRD.md` 路径下，**只是为了让历史交叉引用（约 18 个其他文档 + CI anchor 检查）能跳转到这份警告页**，不要把它扩展成新的 PRD。

## 当前产品事实来源（按可信度从高到低）

1. **代码本身** — `frontend/`、`backend/`、`migrations/` 的实际实现就是产品当前形态。任何文档与代码冲突，以代码为准。
2. **原始 mock 数据 + 前端原型** — [`frontend/src/data/mock.js`](../frontend/src/data/mock.js) 承载了**最初设计期望的产品形态**。后续偏离这份期望的代码改动，许多并非有意为之。需要回到"产品本来想做什么"的问题时，看这个文件。
3. **GitHub issues / PRs** — 最新 epic / PR 描述记录了"为什么这样改"，是变更动机的事实来源。
4. **未被本次归档的 docs**（见 [`docs/INDEX.md`](INDEX.md)） — 如 `ADMIN_PRD.md`、`DATA_MODEL.md`、`ADAPTER_CONTRACT.md`、`openapi.yaml` 等仍在维护，但同样需要逐份核对 `last_verified` 后再信任。

## Agents：阅读规则

- **不要**打开 [`docs/archive/PRD-v1.3-2026-04-15.md`](archive/PRD-v1.3-2026-04-15.md)，除非用户显式让你查"PRD 历史里 X 是怎么写的"。
- **不要**基于这份 stub 或被归档 PRD 的章节锚点（§4.2.3a、§4.5.2、§4.7、§4.8 等）写新代码 / 新测试 / 新 PR。这些锚点描述的是历史意图，不代表当前代码。
- **不要**再写 `PRD_ADDENDUM_*.md` 这种增量补丁。任何新的产品需求都直接落到代码、issue / PR 描述，或者新建一个**有明确边界、有 `last_verified`、不超过 50KB** 的单一 PRD 子文档。
- 引用 PRD 时必须改写为"~~PRD §4.X~~ → 见 `frontend/src/data/mock.js` 或 `<具体代码路径>`"。

## 已知遗留的悬空引用

下列文档仍指向旧 PRD 的章节锚点，需要后续清理（**本次归档不修，让 CI / grep 暴露依赖**）：

- `docs/RUNBOOK_vm_per_account_ramp.md`
- `docs/CODEX_PROMPT_SEGMENT_PROFILE.md`
- `docs/DESIGN_TOKENS.md`
- `docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md`
- `docs/PRD_PAGE_MAP.md`（含 CI 断言）
- `docs/PRD_ADDENDUM_PHASE_P.md`
- `docs/ADMIN_PRD_ADDENDUM_PHASE_P.md`
- `docs/PRD_CODEX_READY.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DASHBOARD_REDESIGN_PROPOSAL.md`

清理顺序建议：先评估每篇文档自身是否也已 stale，整批 archive 比逐条改链接更划算。
