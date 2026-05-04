# ADR-001: Admin Flask → FastAPI 单进程

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
当前后端拆成两个 Python 进程：`backend/` (FastAPI，仅 auth) 和 `admin_console/` (Flask，15391 LOC，含全部运营 API)。这导致：① 部署多一个服务 + nginx upstream + Docker compose 复杂；② 鉴权 / session / audit 双套实现；③ ORM 反复定义；④ 共享逻辑（topic_plan / prompt_matrix / segment_profiles）无法被 FastAPI 端复用。

**Decision**:
把 `admin_console/app.py` 全量迁到 `backend/app/api/admin/*` 13 个子路由器（session / brands / topic_plan / prompt_matrix / query_pool / scheduler / segments / profiles / accounts / users / analyzer / artifacts / stats）。Flask 进程退役，所有运营 API 落 FastAPI。`admin_console/` 4 个共享模块（topic_plan.py / prompt_matrix.py / segment_profiles.py / _layer_classifier.py 共 ~2400 LOC）移到 `backend/app/services/`。Admin HTML 模板（`admin.html`）保留并迁到 FastAPI Jinja2Templates 渲染。Admin auth 从 Flask session 改为 FastAPI cookie session（`SessionMiddleware`），保留 `secret_key` 兼容（不需重新登录）。

**Consequences**:
- ✅ 单进程部署，`docker-compose.yml` 移除 admin 服务定义；nginx 一处 upstream（FastAPI :4000）。
- ✅ 鉴权 / audit / 共享 service 单点维护。
- ⚠️ 一次性迁移成本 5 工程日（Phase R.4），按子路由器分批 PR 降低风险；每迁完一个 router，Flask 侧旧 route 加 deprecation log，preview 验证 1-2 天后删除。
- ⚠️ Admin 操作员需重新熟悉 URL 结构 — 但路径保持 `/admin/*` 与 `/api/admin/*` 不变，零感知。
- ⚠️ 部署回滚：要保留 Flask 镜像 1 个版本，故障时回滚到双进程模式。

**Alternatives**:
- **保持现状（Flask + FastAPI 并存）**：节省迁移成本，但运营和用户共用 ORM 漂移、双 audit 系统、Phase O 新增 9 模块若加在 Flask 会让 admin_console 文件膨胀到 25k+ LOC。否决。
- **拆成 4+ 服务（auth-svc / user-api / admin-svc / worker-svc）**：理论最干净，但运维成本高、网络层增加 RTT、与 5 工程师团队规模不匹配。Phase 2 业务规模上来后再考虑。
