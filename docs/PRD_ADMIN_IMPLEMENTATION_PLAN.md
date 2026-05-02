# Query Admin 实施计划
> 2026-05-02 override: the orange `admin_console` Admin is the only Admin system.
> The legacy FastAPI Admin auth/API package has been removed. Historical
> references in this file to a separate FastAPI Admin backend are superseded.
> Do not restore a second Admin frontend or backend.

> 日期：2026-04-30
> 范围：以 `admin_console` 为唯一 Admin 的 GENPANO 内部运营控制台
> 来源：`docs/PRD.md`、`docs/ADMIN_PRD.md`、`docs/ADMIN_PRD_B_PIPELINE.md`、`docs/ADMIN_PRD_C_KG.md`、`docs/DATA_MODEL.md`、`docs/ADAPTER_CONTRACT.md`、当前已跑通业务代码

## 1. 最新决策

当前 Admin 方向已调整：

- **唯一 Admin 是 `admin_console` Admin**。
- 不再建设独立的 `frontend/src/admin` React Admin。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- `admin_console/app.py` + `admin_console/templates/admin.html` 是当前 Admin 的真实入口。
- FastAPI 后端继续承担产品端 API / 用户认证 / 后续平台 API，不作为 Admin 主实现面。

这意味着后续 session 不能按“新建 Admin 前后端”的思路执行，而要围绕现有 `admin_console` Admin 做：

- 对齐 PRD / Admin PRD 的运营能力
- 保留已经跑通的业务代码和 3 个 LLM adapter
- 做差异审计、补洞、验收和必要的小步重构
- 避免把可运行的采集链路重写坏

## 2. 文档定位

这份文档不是权威 PRD，也不是旧 Claude 文档。它只是给新 session 分工用的执行地图。

权威来源优先级：

1. 当前已经跑通并验证过的业务代码，尤其是 `geo_tracker` 和 `admin_console`
2. `docs/ADAPTER_CONTRACT.md`
3. `docs/DATA_MODEL.md`
4. `docs/ADMIN_PRD_B_PIPELINE.md`
5. `docs/ADMIN_PRD_C_KG.md`
6. `docs/ADMIN_PRD.md`
7. `docs/PRD.md`

如果 PRD 和已跑通代码冲突，不能默认 PRD 胜出。应先输出差异和决策建议。

## 3. 当前代码基线

当前观察到的 Admin 基线：

- `frontend/src/admin` 已不存在。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- `admin_console/app.py` 是 Admin 后端主入口，包含：
  - Flask app
  - `/admin` 页面
  - `/api/admin-auth/session`
  - `/api/admin-auth/login`
  - `/api/admin-auth/logout`
  - `/api/admin-auth/change-password`
  - `/api/stats`
  - `/api/queries`
  - `/api/queries/<id>/retry`
  - `/api/queries/batch_trigger`
  - `/api/accounts`
  - `/api/accounts/import_cookies`
  - `/api/accounts/<id>/status`
  - `/api/accounts/<id>/reset`
  - `/api/accounts/<id>/auto_login`
  - `/api/sms_register`
  - `/api/analyzer/*`
  - `/api/topics`
  - `/api/prompts`
  - 其他查询、截图、HTML artifact、回填、分析接口
- `admin_console/templates/admin.html` 是 Admin UI 主入口，已经包含：
  - 登录态 / 非登录态
  - Admin shell
  - Pipeline / attempts 相关视图
  - Account pool 相关视图
  - Analyzer / KG / audit 等部分 UI 或 placeholder
  - 根据正式 `/admin` 和临时 `/query/admin` mount 自动解析 API base
- `admin_console/scripts/admin_reset_password.py` 已存在，用于 Admin 密码重置。
- `geo_tracker` 里已有 3 个 LLM adapter 相关业务代码，是当前要保护的资产。

关键现状判断：

- Admin 已经不是“待新建系统”，而是“已有可运行系统，需要和 PRD 对齐并补足运营闭环”。
- P0 不应创建新的 Admin 技术栈。
- P1 不应重写 adapter。

## 4. 执行原则

1. **`admin_console` Admin 是唯一 Admin**
   - Admin 页面和接口优先在 `admin_console/app.py` 与 `admin_console/templates/admin.html` 内演进。
   - 不新增 `frontend/src/admin`。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.

2. **先审计，再改造**
   - 尤其是 Pipeline、adapter、账号池、代理池、analyzer。
   - 已跑通逻辑不能因为 PRD 文案不同就重写。

3. **保护 3 个 LLM adapter**
   - 不默认改 adapter 行为。
   - 涉及 adapter contract 时，先输出差异矩阵。
   - PRD 与已验证代码冲突时，列为人工决策。

4. **Admin 写操作必须有审计或明确补洞计划**
   - 当前 `admin_console` 中已有一些 mutation：retry、batch trigger、account status、reset、delete、auto login、analyzer trigger 等。
   - P0 要先盘点这些 mutation 是否审计。
   - P1 新增 mutation 必须写审计。

5. **正式 `/admin` 与临时 `/query/admin` 要分清**
   - 正式 Admin 应通过 `/admin` 暴露。
   - `admin_console` 内部 API 当前仍多为 `/api/*`。
   - 需要确认 nginx / compose 是否将 `/admin/api/*` 正确转发到 admin_console。

6. **App 产品端与 Admin 分离**
   - `frontend` 继续做用户侧 App。
   - `admin_console` 负责内部 Admin。
   - 不把 Admin 重新塞回 App React 路由。

7. **真实数据优先，少造 mock truth**
   - `admin_console` 已经连接真实查询、账号、analyzer、artifact 等数据。
   - 对尚未接入的模块，可以返回明确空状态，但不要在 UI 里制造不可追溯的假真相。

## 5. P0：大多数工作之前的基础

P0 的目标不是“搭一个新 Admin”，而是把现有 `admin_console` Admin 的边界、部署、安全、审计和契约整理清楚。

### P0.1 Baseline 与现状盘点

任务：

- 记录 `git status --short --untracked-files=all`。
- 确认活跃 Admin 文件：
  - `admin_console/app.py`
  - `admin_console/templates/admin.html`
  - `admin_console/requirements.txt`
  - `admin_console/scripts/admin_reset_password.py`
  - `docker-compose.yml`
  - `docker-compose.preview.yml`
  - `nginx-preview.conf`
  - `.github/workflows/deploy*.yml`
- 明确哪些旧 Admin 路径已废弃：
  - `frontend/src/admin`
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- 不删除、不恢复、不重写旧路径，除非用户明确要求清理。

验收：

- 输出当前 Admin 入口、路由、部署路径说明。
- 标出 pre-existing dirty files。
- 没有触碰无关文件。

### P0.2 部署与路由对齐

任务：

- 确认正式 `/admin` 是否由 admin_console 服务。
- 确认 `/admin/api/*` 是否转发到 admin_console 的 `/api/*`。
- 确认临时 `/query/admin` 是否仍可用，以及是否只作为测试入口。
- 检查 `nginx-preview.conf`、`docker-compose*.yml`、GitHub deploy workflow 是否与“admin_console 是唯一 Admin”一致。
- 更新必要注释或文档，避免后续 session 误以为 React Admin 仍存在。

验收：

- `/admin` 的服务归属清楚。
- `/admin/api/*` 的转发规则清楚。
- preview / production compose 不再暗示独立 React Admin。

### P0.3 Admin Auth 基线

任务：

- 审计 `admin_console/app.py` 中 Admin auth：
  - `ADMIN_SESSION_SECRET`
  - session cookie name / secure / path
  - login rate limit
  - bcrypt cost
  - `admin_users`
  - `admin_login_attempts`
  - login / logout / change-password
  - formal `/admin` API 保护逻辑
- 确认正式 `/admin` mount 下 API 是否必须登录。
- 确认临时 `/query/admin` 下是否按预期可放宽或保护。
- 检查 `admin_reset_password.py` 是否和当前表结构一致。

验收：

- 列出 auth 已满足项、风险项、缺口项。
- 不引入第二套 Admin auth。
- 如做修补，只在 `admin_console` 体系内修补。

### P0.4 Mutation 与 Audit 盘点

任务：

- 盘点 `admin_console/app.py` 里所有 `POST` / `PUT` / `DELETE`：
  - query retry
  - batch trigger
  - mark failed
  - account import cookies
  - account status
  - account reset
  - account delete
  - auto login
  - sms register
  - backfill citations
  - profile create / update / delete
  - analyzer trigger / rerun
- 判断哪些需要写 Admin audit。
- 如果当前没有统一 audit 表 / audit helper，提出最小实现方案。

验收：

- 有 mutation audit matrix。
- 新增写操作不允许无 audit。
- 如果时间允许，先补统一 audit helper 和最关键 mutation 的 audit。

### P0.5 Adapter Contract 审计准备

任务：

- 不改 adapter。
- 找出 3 个 LLM adapter 的实际代码路径。
- 列出 adapter contract 核对项：
  - `response_source`
  - error code
  - attempt 粒度
  - retry 状态
  - `NO_ACCOUNT_AVAILABLE` / `COOKIE_EXPIRED` 状态口径
  - account / cookie 生命周期
  - proxy / CAPTCHA / timeout
  - artifact 保存：HAR / screenshot / raw_html
  - analyzer 读取路径

验收：

- 输出“下一步 Adapter 审计 session prompt”或审计清单。
- 不重写 adapter。

## 6. P1：Admin MVP 运营主干

P1 的目标是在现有 `admin_console` Admin 上补齐 MVP 运营能力，而不是迁移到新技术栈。

推荐顺序：

1. 先补现有 Admin 首页 / Overview 的真实指标
2. 再补 Pipeline / attempts / accounts 已有页面的数据完整性
3. 再补 KG / analyzer / audit / alert / cost 等缺口
4. 最后再考虑 UI 重排或抽象

### P1.1 Admin Overview

目标：

- 打开 `/admin` 后能 10 秒判断平台是否健康。

任务：

- 基于 `admin_console` 已有 `/api/stats`、`/api/queries`、`/api/accounts`、`/api/analyzer/*` 聚合 Overview。
- 展示：
  - active alerts 或空状态
  - 今日 query / response 成功率
  - running / pending / failed / completed
  - account pool 水位
  - engine health
  - analyzer 最新状态
  - 需要人工处理的 inbox 数量
- 不要只做前端随机图表；没有真实数据就显示明确空状态。

验收：

- `/admin` 已登录后可见 Overview。
- 数据来自 admin_console API 或明确空状态。
- 未登录正式 `/admin/api/*` 返回 401。

### P1.2 Pipeline Attempts 运营

目标：

- 让 Frank 能看失败、筛选、重试、批量触发，并定位原始 artifact。

任务：

- 对齐现有 `/api/queries`：
  - pagination
  - status filter
  - engine filter
  - brand / topic / prompt filter
  - error reason
  - latency
  - timestamps
- 对齐 retry / batch trigger / mark failed 的状态和审计。
- 确认 screenshot / HTML artifact API 可从 attempt 详情打开。

验收：

- 失败任务可筛选。
- 单条 retry 可用。
- 批量 trigger 可用。
- artifact 可查看或明确显示缺失原因。

### P1.3 Account Pool / Proxy / 登录资源

目标：

- 让账号池、cookie、自动登录、SMS 注册等已跑通能力变成可运营页面。

任务：

- 对齐 `/api/accounts` 页面数据。
- 确认 import cookies、status 修改、reset、delete、auto_login、sms_register 的行为。
- 标注哪些操作需要二次确认和 reason。
- 审计写操作。

验收：

- 每个 engine 的账号水位可见。
- 账号状态变更可操作并有反馈。
- 高风险操作不静默执行。

### P1.4 Analyzer / Brands / Topics / Prompts

目标：

- 让 analyzer 结果能从 Admin 里查、筛、回看。

任务：

- 对齐已有：
  - `/api/analyzer/stats`
  - `/api/analyzer/brands`
  - `/api/analyzer/responses`
  - `/api/analyzer/response/<id>`
  - `/api/analyzer/daily`
  - `/api/topics`
  - `/api/prompts`
- 检查 response detail 是否能回溯 query、prompt、brand、engine、source artifact。
- Analyzer trigger / rerun 必须可审计。

验收：

- 能从品牌 / topic / prompt 维度筛 response。
- 单条 response detail 足够排查问题。
- rerun 有状态反馈。

### P1.5 KG 治理基础

目标：

- 不急着实现完整 ADMIN_PRD_C_KG 九页，而是先把 admin_console 里已有 KG / analyzer 数据入口整理成可用基础。

任务：

- 盘点当前 Admin UI 里 KG 相关区域是 mock、静态数据还是真 API。
- 如果是 mock，标注并替换为真实 read API 或明确空状态。
- 优先做：
  - brand list
  - discovered / pending brand 基础列表
  - alias conflict 可视化或占位
  - discovery logs 可读入口
- 写操作如 approve / reject / merge 暂不做或必须 audit。

验收：

- KG 区域不再伪装成真实数据。
- 已接入的数据来源清楚。
- mutation 未准备好时按钮禁用或标注未接入。

### P1.6 Cost / Alerts / Audit

目标：

- 补齐最低限度运营闭环。

任务：

- 先判断当前是否已有：
  - cost 表 / daily aggregation
  - alerts 表 / alert 状态
  - audit 表 / audit 页面
- 如果没有，先做最小 read model 或明确空状态。
- 优先补 audit，因为它是 Admin 写操作的底线。

验收：

- Audit 页面或 API 能查到关键写操作。
- Alerts 没有真实数据时显示空状态，不用假数据冒充。
- Cost 没有真实聚合时显示待接入来源。

## 7. Adapter 审计任务

这是建议单独开 session 做的任务，优先级高于任何深度 Pipeline 改造。

目标：

- 判断 3 个已跑通 LLM adapter 与 `ADAPTER_CONTRACT.md` 的一致性。
- 不改代码，只输出差异矩阵。

审计矩阵：

| 契约项 | ChatGPT | 豆包 | DeepSeek | 结论 |
|---|---|---|---|---|
| response_source 是否落库 | 待审计 | 待审计 | 待审计 |  |
| error code 是否符合 contract | 待审计 | 待审计 | 待审计 |  |
| NO_ACCOUNT_AVAILABLE / COOKIE_EXPIRED 状态口径 | 待审计 | 待审计 | 待审计 |  |
| retry 策略 | 待审计 | 待审计 | 待审计 |  |
| account / cookie 生命周期 | 待审计 | 待审计 | 待审计 |  |
| proxy / CAPTCHA / timeout 处理 | 待审计 | 待审计 | 待审计 |  |
| HAR / screenshot / raw_html artifact | 待审计 | 待审计 | 待审计 |  |
| attempt 粒度 | 待审计 | 待审计 | 待审计 |  |
| analyzer 读取路径 | 待审计 | 待审计 | 待审计 |  |

输出分类：

- 一致
- PRD / contract 落后于代码
- 代码违反 contract
- 需要人工决策
- 可低风险修复
- 高风险，暂不动

## 8. 给新 Session 的 Prompt 模板

### Prompt A：P0 Query Admin 基础

```text
你是 Codex，请基于 docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md 执行 P0。

重要上下文：
- 现在唯一 Admin 是 admin_console Admin。
- 不要新建 frontend/src/admin。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- admin_console/app.py 和 admin_console/templates/admin.html 是 Admin 真实实现。
- geo_tracker 中已有跑通的 3 个 LLM adapter，是需要保护的资产。

目标：
整理现有 admin_console Admin 的基础边界、部署路径、认证、安全、审计和 adapter 审计准备。

请先阅读：
- docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md
- admin_console/app.py
- admin_console/templates/admin.html
- admin_console/scripts/admin_reset_password.py
- admin_console/requirements.txt
- docker-compose.yml
- docker-compose.preview.yml
- nginx-preview.conf
- .github/workflows/deploy.yml
- .github/workflows/deploy-preview.yml
- docs/ADAPTER_CONTRACT.md
- docs/DATA_MODEL.md

要求：
1. 先运行 git status，保护现有 dirty worktree。
2. 不回滚、不删除用户已有改动。
3. 不重写 adapter。
4. 不迁移到 React Admin 或 FastAPI Admin。
5. 输出或修正：
   - 当前 Admin 入口和路由说明
   - /admin 与 /admin/api 的部署转发关系
   - Admin auth 已满足项 / 风险项 / 缺口项
   - admin_console 中所有 mutation 的 audit matrix
   - adapter contract 审计清单
6. 如果要改代码，只做最小补洞，优先修正 admin_console Admin 自身明显问题。
7. 最终汇报改动文件、检查结果、剩余风险、给 P1 的接入说明。
```

### Prompt B：P1 Query Admin 运营主干

```text
你是 Codex，请基于 docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md 执行 P1。

重要上下文：
- 现在唯一 Admin 是 admin_console Admin。
- 不要新建 frontend/src/admin。
- Legacy FastAPI Admin backend has been removed; do not recreate a second Admin backend.
- 在 admin_console/app.py 和 admin_console/templates/admin.html 上演进。
- 不要重写 geo_tracker 的 3 个 LLM adapter。
- PRD 与已跑通代码冲突时，不默认 PRD 胜出，要列为人工决策。

目标：
在现有 admin_console Admin 上补齐 Admin MVP 运营主干，优先做真实可用的薄切片。

优先顺序：
1. Admin Overview 真实指标 / 明确空状态
2. Pipeline attempts 筛选、详情、retry、batch trigger、artifact 回看
3. Account pool / cookie / auto_login / sms_register 运营闭环
4. Analyzer / brands / topics / prompts 查询和 rerun
5. KG 基础 read / review，不成熟 mutation 先禁用或必须 audit
6. Audit / alerts / cost 最小闭环

请先阅读：
- docs/PRD_ADMIN_IMPLEMENTATION_PLAN.md
- admin_console/app.py
- admin_console/templates/admin.html
- docs/ADMIN_PRD.md
- docs/ADMIN_PRD_B_PIPELINE.md
- docs/ADMIN_PRD_C_KG.md
- docs/ADAPTER_CONTRACT.md
- docs/DATA_MODEL.md
- geo_tracker 相关 adapter / tasks / pool / analyzer 代码，但不要主动改 adapter

要求：
1. 先运行 git status，保护现有 dirty worktree。
2. 不做大重构，优先小步补洞。
3. 不允许只做前端假数据；真实表未就绪时返回明确空状态。
4. 新增或修改的 Admin 写操作必须有 audit 或明确说明为什么暂缓。
5. 对危险操作加确认和 reason。
6. 能跑就跑 admin_console / frontend / backend 的相关 smoke 或 targeted checks。
7. 最终汇报：
   - 完成了哪些 P1 切片
   - 改了哪些文件
   - 哪些 API / UI 可用
   - audit 覆盖情况
   - checks 结果
   - 剩余风险和下一步建议
```

### Prompt C：Adapter Contract 审计

```text
你是 Codex，请先不要改代码。我要你审计当前已经跑通的 3 个 LLM adapter 是否与 PRD / ADAPTER_CONTRACT 一致。

背景：
仓库里已有业务代码和 3 个 LLM adapter，可能已经能跑通。不要因为 PRD 写法不同就重写可运行代码。

请重点阅读：
- docs/PRD.md §4.2、§4.3
- docs/ADAPTER_CONTRACT.md
- docs/DATA_MODEL.md 中 pipeline / ai_responses / attempts 相关部分
- geo_tracker/agent/**
- geo_tracker/tasks/**
- geo_tracker/pool/**
- geo_tracker/analyzer/**
- admin_console/app.py 中读取 query / account / analyzer 的接口
- 相关测试和运行脚本

要求：
1. 先运行 git status，保护现有 dirty worktree。
2. 优先用代码事实说话，不要凭 PRD 猜。
3. 不要重写 adapter。
4. 不要删除已有可运行逻辑。
5. 输出矩阵：ChatGPT / 豆包 / DeepSeek × 契约项。
6. 契约项至少包括：
   - response_source 是否落库
   - error code 是否符合 ADAPTER_CONTRACT
   - NO_ACCOUNT_AVAILABLE / COOKIE_EXPIRED 是否保持 PENDING 而非 FAILED
   - 重试策略是否一致
   - 账号池 / cookie 生命周期是否一致
   - proxy / CAPTCHA / timeout 处理是否一致
   - raw artifact，如 HAR / screenshot / raw_html 是否有保存路径
   - attempt 粒度是否正确
   - 成功率统计是否排除账号不可用类错误
7. 最终只提交审计报告和建议。如果必须改代码，先列出最小改动方案，不要直接动。
```

## 9. 不可妥协规则

- 不再新建独立 React Admin。
- 不再新建独立 FastAPI Admin 主路径。
- 不重写已经跑通的 3 个 LLM adapter。
- PRD 与代码冲突时先审计，不盲改。
- Admin 写操作必须有 audit 或明确标记为待补底线风险。
- 正式 `/admin` 必须有登录保护。
- `admin_console` Admin 不能只展示不可追溯的假数据。
- 当前工作区 dirty 时，不做大范围无关重构。
