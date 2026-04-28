---
name: Session preview env requirement (decision #29.C) and how to register multi-round deviations
description: Cross-Session pattern for documenting deviations from the "every Session must produce a clickable preview URL + frontend-backend wiring + Frank browser self-verification" cross-cutting requirement. A0' has 4 rounds — use this pattern for any future Session that needs to defer preview env coverage.
type: feedback
---

## 横切要求 (CLAUDE.md 决策 #29.C)

> 每个 Session 结束必须 (1) 代码经 Git CI/CD 上 preview env (Vercel / Render / Fly.io 任一); (2) 前后端联动可点击产物; (3) Frank 能在浏览器自验.
>
> Session 0' (CI/CD 基建) 必须先消化此横切要求.

## Why this rule exists

Frank 是 solo founder, AI 工程方法论是 "Frank 看到能跑的产物 / Claude Code 才能继续". 这条要求是把 "纸面 Phase Gate" → "可触摸 Phase Gate" 的关键关卡; 任何延后必须有等效证据 (Layer 1 + Layer 2 + Layer 3 evidence chain) 兜底.

## How to apply

**Default**: 每个 Session 结束 PR 必须挂 Vercel/Render preview URL, Frank 浏览器跑 ≥1 场景, 截图回写交付报告.

**Exception (deviation registration)**: 当 Session 触及 sandbox 限制 / docker daemon 缺席 / 长场景重跑 / 邮件实际发送 / 等环境性 blocker 时, 必须按以下模板登记 4 段证据 + 转交闭环.

### Multi-round deviation accumulation pattern (A0' 模板)

A0' 累计 4 轮偏离 (决策 #30 A/B/C/D), 每轮独立登记 + 转交统一进 A1' batch. 模板:

```
**X. Round N · <场景> 跳过 (Step <K>, <date>)**: 
- 客观限制陈述 (sandbox / docker / long scenario / mock-mode 等)
- 等效证据 (Layer 1 + Layer 2 + Layer 3 一一对应)
- 4 层证据链 (curl / DB / log / actual side-effect) — Layer 3 mock 验证必备
- 转交目标 Session + 修复路径同 PR 闭环短句

收尾 (本决策的 E 段): Phase Gate 接受标准 + 转交清单 (含 Bug N + 跨 Session 工具链清理)
```

### A0' 4-round 实例 (供后续 Session 引用)

- Round 1 = Vercel preview 跳过 (Step 8): sandbox localhost:4001 → Windows 主机不可达 → Phase Gate 接受 Layer 1+2 双绿 → A1' frontend admin shell 联动一起落
- Round 2 = docker compose 跳过 (Step 8): Windows 主机无 docker daemon → uvicorn local + curl 实测等效 → A1' Redis + Postgres 编排一起落
- Round 3a = 手工 L3 9 场景重跑跳过 (Step 11): Step 8 evidence 已沉淀 → LAYER3_REPORT §3 一对一引用 → A1' Step 8 evidence pin 闭环
- Round 3b = 邮件实际发送跳过 + Bug 4 logger gap (Step 11): mock mode 4 层证据链 (curl 202 + DB 行 + uvicorn log 缺 admin_email.skipped + Resend 未调) → 三候选根因 (logger level / handler attach / dictConfig 合并) → A1' dictConfig + structlog + JSONRenderer + Resend live 同 PR

## When this pattern fires

**Trigger**: Session Phase Gate 接近收尾, 任一 Layer 3 (Frank 浏览器自验) 项无法本机跑通, 而 Layer 1 + Layer 2 已绿 + 有等效证据.

**Anti-pattern (DO NOT)**:
- ❌ 静默跳过 Layer 3 但不登记 deviation
- ❌ 把 deviation 写在 commit body 但不进 CLAUDE.md / DECISION_LOG.md
- ❌ "推到下个 Session" 但不指明 fix path / 同 PR 闭环条件
- ❌ 把 4 层证据链中的 (iii) log 缺失视为 "不重要" — 那是 observability gap, 必须作为独立 Bug 登记

## A0' 实测产物 (供后续 Session 复制学习)

- `CLAUDE.md` 决策 #30 (A-E 5 段)
- `docs/DECISION_LOG.md` row 30 (一行索引)
- `docs/SESSION_A0_STEP_11_LAYER3_REPORT.md` (252 行 / 7 节 — 4 层证据链 + Bug 4 完整登记)
- `backend/docs/SESSION_A0_STEP_8_SMOKE_CHECKLIST.md` "A0' Phase Gate 后 known issues" Bug 1-4 + Step 11.5 verify gap addendum

下次 Session 触发 deviation 时, 先打开此 4 个文件中任一参考形式, 不要从零起草.
