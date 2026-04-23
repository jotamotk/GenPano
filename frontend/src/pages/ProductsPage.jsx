/*
 * DEPRECATED — 产品顶级路由已废弃 (PRD §4.6.1 三视角重构, 2026-04-16)
 * ─────────────────────────────────────────────────
 * 产品不再作为顶层 tab 存在. 产品天然隶属于品牌:
 *   - 入口: /brands/:id?tab=products  (BrandDetailPage 的"产品"子 Tab)
 *   - 详情: /brands/:brandId/products/:productId  (BrandProductDetailPage)
 *
 * 本文件保留仅用于避免构建期/IDE 索引断链. 当 Frank 下一次整理
 * repo 时可以安全删除 (git rm frontend/src/pages/ProductsPage.jsx).
 *
 * 请勿在此添加新功能 — 所有产品相关 UI 应该去 BrandDetailPage 的
 * 产品 Tab 或 BrandProductDetailPage.
 */
import { Navigate } from 'react-router-dom';

export default function ProductsPage() {
  // Defensive redirect: if someone restores this route, send them to the
  // brand list, which now owns product drilldown.
  return <Navigate to="/brands" replace />;
}
