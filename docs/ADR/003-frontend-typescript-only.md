# ADR-003: 前端全 TypeScript + 单入口 main.tsx

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
当前 `frontend/src/` 双入口（`App.jsx + main.jsx` 生产；`App.tsx + main.tsx` 仅 Auth 原型）冲突；21 个 page 是 `.jsx`（无类型）；7 个 component 同样；双 contexts 目录 (`context/` + `contexts/`)；4 个废弃 page（`DashboardPage.linear.jsx` / `LandingPageLegacy.jsx` / `IndustryPage.jsx` / `QueriesPage.jsx`）；mock.js 引用散落 21 page 让切真实数据时无类型保护。

**Decision**:
单入口 `main.tsx → App.tsx`，删除 `App.jsx + main.jsx + 4 废弃 page`。21 个 `.jsx` page + 7 个 `.jsx` component 全部转 `.tsx` 加严格类型。合并 `context/ ↔ contexts/` 到 `contexts/`。`tsconfig.json` 启用 `strict: true` / `noUncheckedIndexedAccess: true` / `exactOptionalPropertyTypes: true` / `allowJs: false`（终态）。ESLint `no-restricted-imports` 禁止 `pages/**` import `data/mock`（warn → error 渐进）。Vite 框架不变。

**Consequences**:
- ✅ API 切换时类型契约保护（`api-types.d.ts` 由 OpenAPI 生成）。
- ✅ 单一构建路径，不会再被 `App.tsx` 误导。
- ✅ React Refactor 速度提升（IDE 跳转 / 重命名可靠）。
- ⚠️ 21 page 转 `.tsx` 工作量约 4 工程日；可拆 PR，每 PR 5-7 个 page。
- ⚠️ `react-router-dom` v6 类型严格化可能暴露 router prop 错误，需修。
- ⚠️ 新人入职门槛略升（必须懂 TS）；但与 backend Pydantic 契约对齐，长期 ROI 高。

**Alternatives**:
- **保持 JS + TS 混用**：现状的痛点延续，每页 mock 切 API 时 type unsafe，否决。
- **迁 Next.js 14**：SSR / 路由文件化对 SEO 有利，但需要重写所有 page，工作量是 TS 化的 5 倍，本计划范围外。
