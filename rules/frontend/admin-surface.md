---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Implementation, Review]
hardness: HARD
---

# Admin Surface Rule

**Why**：2026-05-02 决策——避免出现第二个 Admin 产品。详 [rules/INCIDENTS.md#admin-surface-2026-05-02](../INCIDENTS.md#admin-surface-2026-05-02)。

## Rule

- 产品 surface 叫 **Admin**。**不要**在 UI 文案、规划、route ownership 引入第二个产品（如 "Query Tool Admin"）
- 橙色 `/admin` operator console 是**唯一**的 Admin UI
- Admin 必须保持一个 system 在 `/admin` 与 `/admin/*` 下。**不要**把它拆成丢失现有页面
  （Topic Plan / Prompt Matrix / Query Pool / Segment / Profile）的独立 mini-app
- **禁止创建或恢复**以下路径作为第二个 Admin frontend：
  - `frontend/src/admin/**`
  - `frontend/src/pages/admin/**`
  - `frontend-admin/**`
  - Next.js `app/admin/**`
- Admin Query Pool 与 Segment/Profile prototype 工作，使用 branch
  `codex/admin-query-pool-prototype` 或其他 user-approved 非 main 分支

## Verification

```bash
verify: test ! -d frontend/src/admin && test ! -d frontend/src/pages/admin && test ! -d frontend-admin
```

## Cross-references

- [rules/frontend/admin-frontend-workflow.md](admin-frontend-workflow.md)
- [rules/frontend/admin-product-terms.md](admin-product-terms.md)
- [rules/backend/admin-boundary.md](../backend/admin-boundary.md)
