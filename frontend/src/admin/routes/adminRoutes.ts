/**
 * Session A1' Step 9 · 17-page admin route table
 *
 * Module split per SESSION_A1_PRIME_PROMPT.md §0.3 + ADMIN_PRD §4.1-§4.4:
 *   A · Users (3 pages)            — A1.x list / detail / login-audit
 *   B · Pipeline monitoring (6)    — B1-B6 overview / engines / queue /
 *                                    accounts pool / proxies / retry-center
 *   C · Knowledge graph (6)        — C1-C6 industries / brands / products /
 *                                    aliases-relations / brand submissions /
 *                                    discovery logs
 *   D · Cost + Audit (2)           — D1 cost daily, D7 audit log only
 *                                    (the other 5 D-module pages are NOT in
 *                                    Step 9 scope — see prompt §0.3)
 *
 * Imported by both <AdminLayout /> (sidebar nav) and App.jsx (route
 * mounting) to keep paths in sync.
 */

export interface AdminRoute {
  path: string;
  label: string;
}

export interface AdminRouteGroup {
  module: 'A' | 'B' | 'C' | 'D';
  label: string;
  routes: AdminRoute[];
}

export const ADMIN_ROUTE_GROUPS: AdminRouteGroup[] = [
  {
    module: 'A',
    label: '用户管理',
    routes: [
      { path: '/admin/users', label: '用户列表' },
      { path: '/admin/users/login-audit', label: '登录审计' },
    ],
  },
  {
    module: 'B',
    label: '采集管线',
    routes: [
      { path: '/admin/pipeline/overview', label: '总览' },
      { path: '/admin/pipeline/engines', label: '引擎健康' },
      { path: '/admin/pipeline/queue', label: '队列状态' },
      { path: '/admin/accounts-pool', label: '账号池' },
      { path: '/admin/pipeline/proxies', label: '代理节点' },
      { path: '/admin/pipeline/retry-center', label: '失败重试' },
    ],
  },
  {
    module: 'C',
    label: '知识图谱',
    routes: [
      { path: '/admin/kg/industries', label: '行业 / 品类树' },
      { path: '/admin/kg/brands', label: '品牌库' },
      { path: '/admin/kg/products', label: '产品库' },
      { path: '/admin/kg/aliases-relations', label: '别名 + 关系审核' },
      { path: '/admin/kg/brand-submissions', label: '用户提交品牌' },
      { path: '/admin/kg/discovery-logs', label: 'Discovery 日志' },
    ],
  },
  {
    module: 'D',
    label: '成本 + 审计',
    routes: [
      { path: '/admin/cost/daily', label: '日成本' },
      { path: '/admin/audit-log', label: '审计日志' },
    ],
  },
];

/** Flattened path list for tests / breadcrumb tools. */
export const ADMIN_ROUTE_PATHS: string[] = ADMIN_ROUTE_GROUPS.flatMap((g) =>
  g.routes.map((r) => r.path),
);
