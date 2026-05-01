# GENPANO 研发计划

> 日期：2026-04-30
> 依据：`docs/PRD_CODEX_READY.md`
> 目标：让 Codex 可以按计划从当前原型和已跑通业务代码出发，完整研发出产品。

## 1. 总体策略

当前不是从零开始。

已有资产：

- 产品主 App 前端原型：`http://localhost:3000/`
- Admin 原型：`http://localhost:5000/admin`
- Query Admin 实现：`query_tool/app.py` + `query_tool/templates/admin.html`
- 已跑通的 3 个 LLM adapter 业务代码：`geo_tracker`
- 用户认证 FastAPI：`backend/app/api/v1/auth`

研发策略：

1. 先冻结“原型即需求”的事实。
2. 先审计 adapter 和 query_tool Admin，不盲改。
3. 用真实 API 替换产品 App 的 mock truth。
4. 用 Query Admin 承担运营闭环。
5. 每个阶段都以可运行、可验收、可回滚为目标。

## 2. 并行研发泳道

### A. PRD / 契约 / 审计泳道

目标：

- 保证 Codex 不被历史 PRD、废弃 Admin、旧 session 文档带偏。

工作：

- 维护 `docs/PRD_CODEX_READY.md`。
- 维护 `docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md`。
- 对 3 个 adapter 做 contract 差异审计。
- 梳理 DATA_MODEL 与当前真实 DB / query_tool 代码差异。

产出：

- Adapter 差异矩阵。
- Query Admin mutation audit matrix。
- DATA_MODEL drift 清单。

### B. 产品 App 泳道

目标：

- 让 `http://localhost:3000/` 从前端原型逐步变成生产可用 App。

工作：

- 保留当前 `App.jsx` 的 Brand / Industry IA。
- 统一 App 入口，避免 `App.jsx` / `App.tsx` 双入口混乱。
- 完成 auth / setup / onboarding。
- 产品数据 API 化。
- 逐页替换 mock truth。

产出：

- 用户可登录、设置项目、查看品牌 / 行业数据。
- Brand Mode / Industry Mode 页面读取真实 API 或明确空状态。

### C. Query Admin 泳道

目标：

- 让 `http://localhost:5000/admin` 成为可运营控制台。

工作：

- P0：路由、部署、登录、安全、审计、mutation 盘点。
- P1：Overview、Pipeline、Account Pool、Analyzer、KG、Cost、Alerts、Audit。
- 清理原型中的假数据，改为真实 API 或明确空状态。

产出：

- Frank 能通过 Admin 发现问题、定位问题、触发修复、查看结果。

### D. Pipeline / Adapter 泳道

目标：

- 保护已跑通 adapter，同时补齐可观测和 contract。

工作：

- 审计 ChatGPT / 豆包 / DeepSeek。
- 统一 error code / status / retry 口径。
- 确认 artifact 保存与 Admin 回看。
- 确认 analyzer 与 response 的链路。

产出：

- Adapter 不被重写坏。
- Admin 可看到每次 attempt 的关键事实。

### E. 后端数据 / API 泳道

目标：

- 支撑产品 App 和 Admin 的真实数据。

工作：

- 对齐 `DATA_MODEL.md` 与当前真实表。
- 补产品端 `/api/*` 或 `/api/v1/*`。
- 明确哪些 API 属于 FastAPI，哪些属于 query_tool。
- 更新 `docs/openapi.yaml` 或记录暂不更新原因。

产出：

- 产品侧受保护 API。
- Admin 侧 query_tool API。
- 数据口径可追踪。

### F. QA / 部署泳道

目标：

- 保证每个薄切片都能跑、能验收、能部署。

工作：

- 后端 targeted tests。
- 前端 build。
- query_tool smoke。
- localhost 页面验收。
- Docker / nginx / GitHub workflow 对齐。

产出：

- 本地可跑。
- preview 可部署。
- 关键路径可手测。

## 3. 阶段计划

### Phase 0：冻结事实与防跑偏

目标：

- 让所有后续 Codex session 知道当前真实方向。

任务：

- 确认 `query_tool` Admin 是唯一 Admin。
- 确认产品主 App 当前入口是 `main.jsx -> App.jsx`。
- 标注 `App.tsx/main.tsx` 的定位，避免误用。
- 更新文档入口。

验收：

- 新 session 只读 `PRD_CODEX_READY.md` 就不会去新建 React Admin / FastAPI Admin。

### Phase 1：P0 Query Admin 基础

目标：

- 把现有 Query Admin 的基础边界补齐。

任务：

- 路由 / 部署对齐：
  - `/admin`
  - `/admin/api/*`
  - `/query/admin`
- Admin Auth 审计：
  - session secret
  - cookie
  - login rate limit
  - reset password script
- Mutation 盘点：
  - retry
  - batch trigger
  - account status/reset/delete
  - import cookies
  - auto login
  - analyzer rerun
  - profile CRUD
- 设计 audit helper 或审计补洞方案。

验收：

- 有 Query Admin P0 审计报告。
- 正式 `/admin` 被登录保护。
- 高风险 mutation 清单明确。

### Phase 2：Adapter Contract 审计

目标：

- 确认 3 个已跑通 adapter 与 contract 的差异。

任务：

- 审计 ChatGPT。
- 审计豆包。
- 审计 DeepSeek。
- 对照：
  - response_source
  - error code
  - retry
  - account unavailable 状态
  - cookie 生命周期
  - proxy / CAPTCHA / timeout
  - artifact
  - analyzer 链路

验收：

- 输出差异矩阵。
- 标出“可低风险修复”和“需人工决策”。
- 不直接重写 adapter。

### Phase 3：P1 Query Admin 运营主干

目标：

- 让 Admin 从原型变成可运营工具。

任务顺序：

1. Overview
   - 真实 KPI / 空状态
   - Pipeline funnel
   - Engine health
   - Inbox
2. 用户管理
   - 用户列表 read-only
   - 用户详情 read-only
   - 登录审计 read-only
   - moderation 表与 audit helper
   - freeze / unfreeze
   - force password reset
   - soft delete 后置
3. Pipeline Attempts
   - 查询 / 筛选 / 分页
   - retry / batch trigger / mark failed
   - artifact 回看
4. Account Pool
   - 账号状态
   - cookies 导入
   - reset / delete / auto login / sms register
5. Analyzer
   - stats / brands / responses / detail / daily
   - trigger / rerun
6. KG 基础
   - brand review read
   - discovery logs read
   - mock 区域改空状态或真实 API
7. Audit / Alerts / Cost
   - 先 audit
   - 再 alerts
   - 最后 cost aggregation

验收：

- Frank 可通过 Admin 完成一次“发现失败任务 -> 查看 artifact -> retry -> 查看状态”的闭环。
- Frank 可通过 Admin 查看用户列表、用户详情和登录审计。
- 账号池操作有清楚反馈。
- 写操作具备审计或明确风险记录。

### Phase 4：产品 App Auth / Setup 稳定

目标：

- 用户可以顺畅注册、验证、设置资料、进入 App。

任务：

- 确认当前入口文件。
- 统一 auth API base。
- 验证：
  - lookup
  - register
  - email sent
  - setup token
  - setup
  - login
  - forgot password
  - reset password
  - OAuth callback
- 确认 public-only / protected route 行为。

验收：

- 新用户注册后能进入 onboarding / setup。
- 老用户登录后进入产品页。
- 未登录访问数据页会被拦截。

### Phase 5：产品 App 数据 API 化

目标：

- 把用户侧核心页面从 mock truth 迁移到真实 API。

优先顺序：

1. Current project / project state
2. Brand overview
3. Brand visibility
4. Brand topics
5. Brand sentiment
6. Brand citations
7. Brand products
8. Brand competitors
9. Industry overview
10. Industry ranking
11. Industry topics
12. Industry knowledge graph

验收：

- 每迁移一页，页面支持：
  - loading
  - empty
  - error
  - real data
- 不再新增页面级 mock truth。
- API 401 时统一处理。

### Phase 6：Reports / Diagnostics / Commercial

目标：

- 补齐用户侧行动层。

任务：

- Reports：
  - list
  - generate
  - schedule
  - export
- Diagnostics：
  - list
  - detail
  - data-driven suggestion
- Commercial leads：
  - lead form
  - Admin 可见

验收：

- 用户能从诊断进入咨询 / 线索。
- Admin 能看到线索。
- 报告导出有服务端限制。

### Phase 7：硬化与发布

目标：

- 从可用变成可发布。

任务：

- 删除或隔离废弃入口。
- 更新 README / 部署文档。
- 更新 openapi。
- 增加 smoke checklist。
- 核查敏感信息：
  - cookies
  - localStorage
  - tokens
  - logs
  - screenshots
- 确认 production env。

验收：

- 本地和 preview 都能跑。
- Admin 受保护。
- 产品 App 可登录并看核心数据。
- Adapter 不回退。

## 4. 建议新开 Session 分工

### Session 1：P0 Query Admin 基础

目标：

- 只做 Query Admin 基础审计与最小补洞。

禁止：

- 不做 React Admin。
- 不做 FastAPI Admin。
- 不改 adapter 深层逻辑。

### Session 2：Adapter Contract 审计

目标：

- 只审计 3 个 LLM adapter。

禁止：

- 不直接改 adapter。
- 不根据 PRD 盲目重写。

### Session 3：P1 Query Admin 运营主干

目标：

- 在 Session 1 和 2 的结果上做 Admin 真实运营能力。

建议启动条件：

- Session 1 已明确 `/admin` / `/admin/api` / audit 风险。
- Session 2 已明确 adapter 差异。

### Session 4：产品 App API 化

目标：

- 从 Brand Overview 开始逐页接真实 API。

建议启动条件：

- FastAPI user auth 已稳定。
- current project API 或临时 project read model 已确定。

## 5. 每个任务的固定验收模板

每个 Codex session final 必须汇报：

- 读取了哪些文档和原型代码。
- 改了哪些文件。
- 完成了哪些 PRD 条目。
- 哪些行为可以在 localhost 验收。
- 跑了哪些检查。
- 哪些检查没跑，为什么。
- 是否触碰 adapter。
- 是否新增 Admin 写操作。
- Admin 写操作是否有 audit。
- 剩余风险。

## 6. 当前最高优先级

如果只做两个 session，推荐：

1. **P0 Query Admin 基础**
2. **Adapter Contract 审计**

原因：

- Query Admin 是唯一 Admin，必须先防止后续 session 建错方向。
- Adapter 是已跑通的核心资产，必须先保护。
- P1 Admin 运营主干依赖这两个结论，否则容易把可运行链路改坏。

如果必须并行 P0 + P1：

- P1 只能做 query_tool Overview / Attempts / Account / Analyzer 的薄切片。
- P1 不碰 adapter 深层逻辑。
- P1 不新建 Admin 技术栈。
- P1 遇到 contract 冲突必须列为人工决策。
