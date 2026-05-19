---
last-reviewed: 2026-05-19
owner-hat: Implementation
next-review-by: 2026-11-19
status: active
applies-to: [Implementation]
hardness: SOFT
---

# Admin Frontend Workflow

**Why**：先确认渲染来源，再动 UI。Vite 代理结构容易让人误判 ownership。

## Rule

改任何 Admin UI 之前：

1. **确认 branch 不是 `main`**
2. **检查渲染路径**：`frontend/vite.config.js` + `/admin` 响应 + 实际渲染橙色 Admin 页的 server 代码
3. **保留**完整 Admin 导航与现有 Admin 页面
4. **保持 `/admin/api/*` 作为 API 边界**；不要用它证明 UI 属于第二个 Admin frontend
5. 编辑后**跑相关 frontend build 或 smoke check**

### 当前 Admin Boundary 事实

- 本地开发：`http://127.0.0.1:5173/admin` 通过 Vite proxy 从 FastAPI（端口 `4000`）服务
- **不要从 URL 推断 ownership**。改任何 Admin UI 前，验证哪个文件渲染浏览器页 + 陈述确切文件路径
- Admin SPA shell 现在位于 `backend/static/admin.html`，由 FastAPI 服务
- 所有 Admin API 在 FastAPI backend 里的 `/admin/api/*` 下

## Verification

```bash
verify: test -f backend/static/admin.html && grep -q 'proxy' frontend/vite.config.js
```

## Cross-references

- [rules/frontend/admin-surface.md](admin-surface.md)
- [rules/backend/admin-boundary.md](../backend/admin-boundary.md)
