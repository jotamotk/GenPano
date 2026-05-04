# PRD ↔ FE Page 交叉表

> 日期：2026-05-04 · Phase P.5
> 范围：21 frontend pages × {PRD 章节, 后端端点, 数据表, 测试链路, Phase} 矩阵。
> 用途：① 任何 PR 改某 page 时同步检查该表；② CI `test_prd_page_links.py` 校验 page 注释中的 `PRD §X.Y` 锚点全部存在；③ 新人接手 page 时一眼看到上下游。
> 维护规则：每次开新 PR 改 page → 同步更新此表。

---

## 用户产品 Pages（17 个）

### Auth Flow（5 pages）

| Page File | PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `pages/AuthPage.jsx` (升级 .tsx) | §3.1 / §3.3 / §3.4 | `/api/auth/lookup`、`/login`、`/register`、`/forgot-password`、`/google` | `users`、`user_auth_tokens` | e2e auth-register / auth-login | 1 |
| `pages/EmailSentPage.tsx` | §3.5 | `/api/auth/resend-verification` | `user_auth_tokens` | e2e auth-register | 1 |
| `pages/SetupPage.tsx` | §3.6 | `/api/auth/setup-token`、`/setup` | `users`、`user_auth_tokens` | e2e auth-register（含 OAuth setup） | 1 |
| `pages/ForgotPasswordPage.tsx` | §3.7 | `/api/auth/forgot-password` | `user_auth_tokens` | e2e auth-reset | 1 |
| `pages/ResetPasswordPage.tsx` + `ResetPasswordSuccessPage.tsx` | §3.8 | `/api/auth/reset-password` | `users`、`user_auth_tokens` | e2e auth-reset | 1 |

### Onboarding + Project（2 pages）

| Page File | PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `pages/OnboardingPage.jsx` (.tsx) | §4.1.1b | `/v1/industries`、`/v1/industries/:id/top-brands`、`POST /v1/projects` | `projects`、`industries`、`brands`、`geo_score_daily` | e2e onboarding | 1 |
| `pages/ProjectSettingsPage.jsx` (.tsx) | §4.1.2 / §4.1.2a | `PATCH /v1/projects/:id`、`DELETE /v1/projects/:id`、`POST/DELETE …/competitors` | `projects`、`project_competitors` | unit ProjectContext + e2e multi-project | 1 |

### Brand Mode（9 pages）

| Page File | PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `pages/DashboardPage.jsx` (= `/brand/overview`, .tsx) | §4.6.1a | `GET /v1/projects/:id/overview` | `geo_score_daily`、`brands`、`response_analyses`、`brand_group_shared_domains` (A.6) | e2e brand-overview + 4 态 RTL | 2.1 + A.6 |
| `pages/brand/BrandVisibilityPage.jsx` (.tsx) | §4.6.1b | `GET /v1/projects/:id/metrics?series=mention,sov,rank` | `geo_score_daily`、`brand_mentions` | 4 态 RTL + 多租户 6 case | 2.1 |
| `pages/TopicsPage.jsx` (.tsx) | §4.6.1c | `GET/PATCH/DELETE /v1/projects/:id/topics` | `topics`、`project_topic_pins`、`prompts` | 4 态 RTL + topic pin/ignore | 2.2 |
| `pages/brand/BrandSentimentPage.jsx` (.tsx) | §4.6.1d | `GET /v1/projects/:id/sentiment[/keywords|drivers]` | `response_analyses`、`sentiment_drivers` | 4 态 RTL | 2.2 |
| `pages/brand/BrandCitationsPage.jsx` (.tsx) | §4.2.7.A-F + §4.6.1e | `GET /v1/projects/:id/citations[/domains|pages]` | `citation_sources` (含 A.3/A.4/A.5 列)、`response_analyses` | 4 态 RTL + 归因模块 | 2.2 + A.3/A.4/A.5 |
| `pages/brand/BrandProductsPage.jsx` (.tsx) + `BrandProductDetailPage.jsx` (.tsx) | §4.6.1f | `GET /v1/projects/:id/products[/:pid]` | `products`、`product_score_daily`、`product_feature_mentions` | 4 态 RTL | 2.3 |
| `pages/brand/BrandCompetitorsPage.jsx` (.tsx) | §4.6.1g | `GET /v1/projects/:id/competitors/metrics` | `project_competitors`、`competitor_mention_daily` (A.7)、`geo_score_daily` | 4 态 RTL + 矩阵气泡 | 2.3 + A.7 |
| `pages/DiagnosticsPage.jsx` (.tsx) | §4.7.0-a + §4.7.1 + §4.8 | `GET /v1/projects/:id/diagnostics`、`PATCH /v1/projects/:id/diagnostics/:diag_id` | `diagnostics`、`response_analyses`、`citation_sources`、`sentiment_drivers` | 4 态 RTL + 25 规则 happy + DiagnosticCard 渲染 | 2.3 + D + A.9 |
| `pages/ReportsPage.jsx` (.tsx) | §4.7 + §4.7.2 | `GET/POST /v1/projects/:id/reports`、`/.../share`、`/report-schedules` | `report_jobs`、`report_schedules`、`report_share_tokens` | e2e report-export + 4 type × 10 section RTL | RP |

### Industry Mode（4 pages）

| Page File | PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `pages/industry/IndustryOverviewPage.jsx` (.tsx) | §4.6.2a | `GET /v1/industries/:iid/overview` | `industry_benchmark_daily`、`brands` | 4 态 RTL | 3 |
| `pages/industry/IndustryRankingPage.jsx` (.tsx) | §4.6.2b | `GET /v1/industries/:iid/ranking` | `geo_score_daily`、`brands` | 4 态 RTL + offset 分页 | 3 |
| `pages/industry/IndustryTopicsPage.jsx` (.tsx) | §4.6.2c | `GET /v1/industries/:iid/topics` | `topics`、`prompts`、`industry_topic_daily` (A.10) | 4 态 RTL | 3 + A.10 |
| `pages/KnowledgeGraphPage.jsx` (.tsx) (= `/industry/knowledge-graph`) | §4.0.1a + §4.6.2d | `GET /v1/industries/:iid/kg` | 5 张 `kg_*` + `brand_groups`、`brand_group_shared_domains` | e2e industry-kg + 1000 节点 perf | K |

### Discovery + Settings（5 pages）

| Page File | PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `pages/LandingPage.jsx` (.tsx) | §4.1.1c | 公开端点（landing 文案，无后端） | — | visual snapshot | R.1 |
| `pages/BrandsPage.jsx` (.tsx) | §4.6.0 | `GET /v1/brands?industryId=&q=`、`POST /v1/brands/submissions` | `brands`、`geo_score_daily`、`brand_submissions` | 4 态 RTL + brand submission flow | 1 + E.2 |
| `pages/BrandSimulatorPage.jsx` (.tsx) | §4.2.7.E | `POST /v1/projects/:id/simulator/run` | `domain_authorities`、`industry_pricing_params`、`citation_sources` | unit simulator 公式 + e2e | E.4 |
| `pages/SettingsPage.jsx` (.tsx) | §4.10 + §4.5.2 | `/v1/users/me`、`/v1/users/me/api-keys`、`/v1/users/me/notifications` | `users`、`user_api_keys`、`user_notification_preferences` | 4 态 RTL + 3 toggle 持久化 + API key 生成 | 1 + M + N |
| 顶栏 🔔 铃铛 | §4.6 顶栏 + §4.7.3 | `/v1/alerts`、`/v1/alerts/unread-count` | `alerts` | unit AlertBell + e2e | N |

---

## Admin Pages（≈ 30 模块，列出主要 9 个 Phase O 新增）

| Admin Module | ADMIN_PRD 章节 | 后端端点 | 数据表 | 关键测试 | Phase |
| --- | --- | --- | --- | --- | --- |
| `/admin/pipeline/overview` | §4.2.1 | `/api/admin/pipeline/overview` | `query_executions`、`attempts`、`llm_responses`、`response_analyses` | admin-only 6 case | O.1.1 |
| `/admin/pipeline/engines` | §4.2.2 | `/api/admin/pipeline/engines[/:engine/recheck]` | `engine_health_daily`、`attempts` | engine_health.aggregate Celery + alert | O.1.2 |
| `/admin/pipeline/queue` | §4.2.3 | `/api/admin/pipeline/queue` | `query_executions` | admin 6 case | R.4 |
| `/admin/pipeline/proxies` | §4.2.5 | `/api/admin/pipeline/proxies[/:id]` | `proxies`、`proxy_health_daily` | admin CRUD 6 case | O.1.4 |
| `/admin/pipeline/retry-center` | §4.2.6 | `/api/admin/pipeline/retry-center[/:query_id]/retry` | `query_executions`、`attempts` | retry mutation + audit_decorator | O.1.3 |
| `/admin/kg/discovery-logs` | §4.3.6 | `/api/admin/kg/discovery-logs[/stats\|/:id/mark-hallucination]` | `discovery_log` | hallucination rate 计算 | O.1.5 + K.5 |
| `/admin/cost/daily` | §4.4.1 | `/api/admin/cost/daily[/breakdown\|/budget-thresholds]` | `cost_events`、`budget_thresholds` | 6 source 写入点 + 预算告警 | O.2.1 |
| `/admin/audit-log` | §4.4.7 | `/api/admin/audit-log[/:id\|/export]` | `admin_audit_log` | audit_decorator coverage CI | O.2.2 + ADR-014 |
| `/admin/mcp-ops` | §4.4.6 | `/api/admin/mcp-ops/[overview\|users\|calls\|api-keys/:id/suspend\|/resume]` | `mcp_call_log`、`user_api_keys` | 配额自动暂停 | O.2.3 + M |
| `/admin/alerts` (operator) | §4.4.2 | `/api/admin/alerts[/:id\|/escalate\|/mark-all-read]` | `alerts (scope=operator)` | scope 隔离单测 | O.3.1 + N + ADR-013 |
| `/admin/comms` | §4.4.4 | `/api/admin/comms[/:id/send\|/preview\|/cancel]` | `comms_announcements` | audience 路由 + 邮件批发送 | O.3.2 |
| `/admin/commercial/leads` | §4.4.5 | `/api/admin/commercial/leads[/:id\|/export]` | `commercial_leads` | status 流转 + lead_diagnostic 报告链接 | O.3.3 + RP.8 |
| `/admin/schedule` | §4.4.3 | `/api/scheduler/[config\|runs\|schedules]` | `scheduler_config`、`scheduler_runs` | cron 编辑 + 失败重跑 | O.4 + R.4 |
| `/admin/kg/{categories,brands,products}` | §C.1-C.3 | `/api/admin/kg/{categories,brands,products}[/...]` | `kg_categories`、`kg_brands`、`kg_products` | admin CRUD + audit 高风险 | K.3 |
| `/admin/kg/{brand-relations,product-relations,candidates}` | §C.4-C.5 | `/api/admin/kg/{brand-relations,product-relations,candidates}/[...]` | `kg_brand_relations`、`kg_product_relations`、`kg_relation_candidates` | bulk-review + 关系审核 | K.3 + ADR-012 |
| `/admin/kg/{diff,quality}` | §C.8-C.9 | `/api/admin/kg/{diff,quality}` | 多表 JOIN 派生 | 24h diff + quality 监控 | K.3 |
| `/admin/kg/brand-submissions` | §C.6 | `/api/admin/kg/brand-submissions/[:id/approve\|/reject\|/duplicate]` | `brand_submissions` | 审核状态机 | E.2 + K.3 |
| `/admin/domain-authorities` | §A.4 | `/api/admin/domain-authorities[/:domain\|/bulk-import]` | `domain_authorities` | 200 种子录入 + bulk import | A.4 |
| `/admin/brand-groups` | §A.6 | `/api/admin/brand-groups[/:id/members]` | `brand_groups`、`brand_group_members` | admin CRUD + audit | A.6 |
| `/admin/industry-pricing-params` | §4.7.6 | `/api/admin/industry-pricing-params` | `industry_pricing_params` | 4 行业种子 + audit:high | E.4 |

---

## 跨页基础设施

| 模块 | 用途 | 关联 Phase |
| --- | --- | --- |
| `frontend/src/lib/apiClient.ts` | 统一 fetch + Bearer + 401 拦截 + RFC 7807 | Phase 0 |
| `frontend/src/contexts/ProjectContext.tsx` | active project + competitors + WatchBrand | Phase 1 |
| `frontend/src/contexts/AuthContext.tsx` | JWT + user object | Phase 1 |
| `frontend/src/contexts/LocaleContext.tsx` | zh/en + Intl.format | R.1 |
| `frontend/src/contexts/ThemeContext.tsx` | light/dark | R.1 |
| `frontend/src/components/ui/{Skeleton,EmptyState,ErrorState}.tsx` | 4 态通用组件 | Phase 0 |
| `frontend/src/components/auth/AuthPromptModal.tsx` | 匿名→注册 hook | Phase 1（hook 7 类对应不同 Phase）|
| `frontend/src/components/topbar/AlertBell.tsx`（新建）| 顶栏铃铛 | N.5 |
| `frontend/src/lib/emailDomains.ts`（新建）| 企业邮箱黑名单 SSOT | Phase 1 |

---

## 删除 / 归档

| 文件 | 原因 | 处理 |
| --- | --- | --- |
| `frontend/src/App.jsx`、`main.jsx` | 双入口冲突 | R.1 删 |
| `pages/DashboardPage.linear.jsx` | Linear skin 已删除 | R.1 删 |
| `pages/LandingPageLegacy.jsx` | 旧 landing | R.1 删 |
| `pages/IndustryPage.jsx` | 已被 `industry/IndustryOverviewPage.jsx` 替代 | R.1 删 |
| `pages/QueriesPage.jsx` | 0 字节空文件 | R.1 删 |
| `frontend/src/data/mock.js` | 21 page 引用 mock | Phase 5 mock 退役（fixture 抽到 `__ci_fixtures__/sampleData.ts`）|
| `frontend/src/components/dev/SkinToggle.jsx` | DEAD FILE 标注 | R.1 删 |

---

## CI 校验

新建 `backend/tests/test_prd_page_links.py`：

```python
def test_all_page_prd_anchors_valid():
    """扫 frontend/src/pages/**/*.tsx，提取 'PRD §X.Y' 引用，
    断言 docs/PRD.md / ADMIN_PRD.md 中存在对应 anchor。"""
    ...
```

新建 `backend/tests/test_prd_page_map_complete.py`：

```python
def test_all_pages_in_map():
    """扫 frontend/src/pages/**/*.tsx，断言 docs/PRD_PAGE_MAP.md 全部覆盖。"""
    ...
```

---

*本文件随每个 PR 改 page 时同步更新；如发现 PRD 缺章节或后端缺端点，先补 PRD / openapi.yaml 再继续。*
