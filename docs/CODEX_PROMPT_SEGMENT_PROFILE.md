# Codex Prompt: Admin Segment & Profile Development

Use this prompt for a focused Codex session to implement Segment & Profile beyond the frontend prototype.

> 2026-05-08 update (PR #386): the Flask `admin_console/` package has been
> ported to FastAPI under `backend/app/api/admin/*`; the Admin SPA shell now
> lives at `backend/static/admin.html`. References in the prompt below to
> `admin_console/app.py`, `admin_console/templates/admin.html`, or
> `admin_console/tests` describe the pre-migration layout — translate them to
> the current locations (`backend/app/api/admin/segments`,
> `backend/app/api/admin/profiles`, `backend/static/admin.html`,
> `backend/tests/`) before running.

```text
你在 C:\Users\frank.wang\genpano 工作。先阅读 AGENTS.md，严格遵守当前 Admin 边界：

- 橙色 /admin 是唯一 Admin，源码在 admin_console/。
- 不要创建或恢复 frontend/src/admin、templates/admin、frontend-admin 或第二套 Admin。
- 不要修改 query_tool 上古版本，也不要动已经可运行的 Topic Plan / Prompt Matrix / LLM scraper。
- 当前分支必须不是 main；优先使用 codex/admin-query-pool-prototype 或用户明确指定的分支。
- 当前页面原型在 admin_console/templates/admin.html，路由是 /admin/planner-profiles。

目标：
把 Admin 的 Segment & Profile 从前端原型推进到可研发落地的最小闭环。Segment 是人群分层，Profile 是单个 Segment 下的具体用户画像。UI 文案统一叫 Segment，不再叫 ProfileGroup；旧 profileGroup/profile_groups 只作为兼容字段，不泄漏到 Admin 前端。

必读文档：
- docs/ADMIN_PRD_B_PIPELINE.md §1.4 Segment & Profile
- docs/PRD.md §4.2.3a Segment / Profile Group
- admin_console/templates/admin.html 里 planner-profiles 页面当前实现
- admin_console/app.py 的现有 auth、API、DB helper、audit 模式

产品行为必须与当前页面一致：
1. Segment 列表页
   - 显示 Segment 总览、搜索、导入 Segment、LLM 生成 Segment、手动新建。
   - 表格字段：ID、Segment 名称与状态、行业、Profile 数与 active 数、采样权重、采样范围、操作。
   - 点击 Segment 行进入该 Segment 的 Profile 子页。
2. LLM 生成 Segment
   - 输入：品牌、行业、生成数量、默认状态、品牌定位/产品线、覆盖目标、约束。
   - 生成 Segment 草稿，人工确认后加入列表。
   - 新增 Segment 默认有空 Profile 池。
3. Segment CRUD / 导入
   - 字段：ID/code、名称、行业、状态、权重、年龄段、收入、区域、采样率、备注。
   - 删除必须 soft delete，不破坏历史 Query lineage。
4. Profile 子页
   - 进入后不要显示外层 Segment banner。
   - 顶部只保留紧凑上下文栏：返回 Segment、当前 Segment ID、状态、Profile 数、active 数、名称和说明。
   - 操作：LLM 生成 Profile、导出、导入、新建 Profile。
   - 搜索只针对当前 Segment 的 Profile。
   - 表格字段：ID、Profile 名称与状态、画像、需求、权重、操作。
5. LLM 生成 Profile
   - 只生成当前 Segment 下的 Profile。
   - 输入：品牌、数量、生成目标、约束。
   - 不要在 Profile 子页提供 LLM 生成 Query；Query 生成属于 Query Pool。
6. Profile CRUD / 导入 / 导出
   - 字段：ID/code、名称、画像、需求、权重、状态、persona_json。
   - 导出当前 Segment 的 CSV：id,segment_id,name,demographic,need,weight,status。

后端/API 要求：
- 所有非 GET 接口必须登录保护，并接入 Admin audit（如当前项目已有 helper，复用它）。
- 建议 API：
  - GET /admin/api/segments?page=&per_page=&q=&status=&industry_id=
  - POST /admin/api/segments
  - GET /admin/api/segments/:id
  - PUT /admin/api/segments/:id
  - DELETE /admin/api/segments/:id
  - POST /admin/api/segments/import
  - POST /admin/api/segments/generate
  - GET /admin/api/segments/:id/profiles?page=&per_page=&q=&status=
  - POST /admin/api/segments/:id/profiles
  - PUT /admin/api/segments/:id/profiles/:profile_id
  - DELETE /admin/api/segments/:id/profiles/:profile_id
  - POST /admin/api/segments/:id/profiles/import
  - GET /admin/api/segments/:id/profiles/export
  - POST /admin/api/segments/:id/profiles/generate
- 正式实现必须服务端分页/搜索，不要一次性加载全量 Segment/Profile。
- 默认分页建议：Segment 50/page，Profile 100/page。
- 搜索需要 debounce；分页/搜索/状态筛选应进入 URL query 或至少具备可恢复状态。
- Segment 权重全为 0 时，Query Pool 组装需要阻断并提示。

数据模型方向：
- 优先新增/使用 segments、profiles、segment_generation_logs、profile_generation_logs。
- 如果当前库已有 profile_groups 表，先评估迁移或兼容映射，不能把 ProfileGroup 暴露给 Admin UI。
- 删除用 is_deleted / deleted_at / status，不做物理删除。
- LLM 生成日志记录模型、prompt、输入参数、tokens、estimated_cost、created_by。

LLM 生成要求：
- 优先复用项目现有 LLM client / OpenAI 配置；如果没有成熟 helper，先做 service 层接口和可测试 fallback，不要把随机 mock 写死到业务 API。
- 生成结果必须可人工审核/编辑后入库。
- prompt 里要要求输出结构化 JSON，校验字段完整性、数量上限、重复名称和非法权重。

测试与验证：
- 增加或更新 admin_console/tests，覆盖：
  - Segment list pagination/search
  - Segment create/update/soft delete
  - Segment import
  - LLM Segment generation service boundary
  - Profile list under segment
  - Profile create/update/soft delete/import/export
  - LLM Profile generation service boundary
  - 未登录 mutation 返回 401/403
- 运行：py -3.14 -m pytest admin_console\tests
- 修改前端后至少做脚本语法检查；如果本地服务可用，用 /admin/planner-profiles 做浏览器 smoke check。

交付：
- 列出改过的文件。
- 说明哪些能力已接真实 DB/API，哪些仍是 service stub 或后续项。
- 不提交 PR，除非用户明确要求。
```

