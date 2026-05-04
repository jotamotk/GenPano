# ADR-005: 多租户 `org_id` 预留位

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
PRD §1.3 列了团队管理为核心功能，但 §38 明确 MVP 不做。当前 `users` 表 1:1 映射用户，`projects.user_id` 直接挂用户。Phase 2 上团队时如果改 schema，会触发大量数据迁移 + service 层重写（凡是用 `user_id` 的多租户校验都要换成 `org_id`）。

**Decision**:
现在就加 `organizations` 表 + `users.default_org_id` + `projects.org_id`（以及 `commercial_leads`、`report_jobs`、`brand_submissions`、`user_api_keys` 等多租户表都加 `org_id`）。每个新用户自动建一个 personal org，所有数据落到该 org。`current_project()` 依赖按 `project.org_id IN user.org_ids` 校验（personal org 一对一兼容现 `user_id` 路径）。**不**上 invitation / member / role UI（Phase T 再做）。

**Consequences**:
- ✅ Phase 2 上团队管理（邀请 / role / 转让 project）零迁移成本。
- ✅ 多租户校验统一抽象到 `current_org()` 依赖。
- ⚠️ 每用户多一行 `organizations` 记录（开销可忽略）。
- ⚠️ Service 层早期写 `org_id` 过滤显得冗余，但属一次性投资。
- ⚠️ 如果 Phase 2 决定不做团队（产品定位变化），冗余字段保留无害。

**Alternatives**:
- **不预留位，Phase 2 再迁**：迁移成本极高（schema + 所有 service + 所有 API），否决。
- **完整上团队（Phase T 立即做）**：UI 设计 + 邀请邮件 + 计费方案需求大，PRD §38 已明确推迟。
