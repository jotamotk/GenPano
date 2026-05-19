---
last-reviewed: 2026-05-19
owner-hat: Implementation
next-review-by: 2026-11-19
status: active
applies-to: [Implementation]
hardness: HARD
---

# Admin Backend Boundary

**Why**：Legacy Flask admin_console/ 已删除，不允许复活第二个 Admin backend。

## Rule

- 所有 Admin API 在 FastAPI backend 里的 `/admin/api/*` 下
- legacy Flask `admin_console/` 包已被移除。**不要**重建第二个 Admin backend
- 添加 Admin auth/API 工作 → 在 FastAPI backend 内做，**除非用户显式 approve 新架构**
- Admin SPA shell 位于 `backend/static/admin.html`，由 FastAPI 服务

## Verification

```bash
verify: test ! -d admin_console && test -f backend/static/admin.html
```

## Cross-references

- [rules/frontend/admin-surface.md](../frontend/admin-surface.md)
- [rules/frontend/admin-frontend-workflow.md](../frontend/admin-frontend-workflow.md)
