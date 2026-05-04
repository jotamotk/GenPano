# ADR-014: Audit Decorator 统一注入

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
ADMIN_PRD §5.2 + §4.4.7 要求每个 admin 写操作必有 audit log。当前 `admin_console/app.py` 散落式写 audit（部分 mutation 写、部分不写）。Phase R.4 迁 FastAPI + Phase O 新增 9 模块共 35+ 端点，依赖人工记忆写 audit 必出错。

**Decision**:
新建 `backend/app/admin/audit.py`：定义 `@audit(action: str, severity: str, capture_diff: bool = True)` 装饰器，所有 admin 写操作（POST / PUT / PATCH / DELETE）必须装饰。装饰器自动：① 提取 operator from request.state.user；② capture before/after snapshot；③ 写 `admin_audit_log` 表。CI 加 `test_audit_decorator_coverage.py`：扫所有 `backend/app/api/admin/` 下的写路由，断言每个有 `@audit` 装饰；缺失即 fail。高风险操作 severity='high'（freeze_user / brand_merge / batch_retry / config_change / 等 12 类，详见 PRD addendum §5.7）。

**Consequences**:
- ✅ 强制覆盖：CI 不通过 = PR 不能合，杜绝漏审。
- ✅ Diff 自动捕获（before/after JSONB），无需手写 capture 代码。
- ✅ Phase O.2.2 审计日志页直接消费 `admin_audit_log`，无数据缺口。
- ⚠️ before/after snapshot 实现需要每个 resource 类型的 reader（Brand / User / Project / etc.），初次抽象工作量约 1.5 工程日。
- ⚠️ Diff JSON 存储成本：每次写约 1-5 KB，admin 每天约 200 写 → 1MB/天可控。
- ⚠️ 极端大对象（如全量 segment_profiles 列表）需要截断，避免 audit log 膨胀。

**Alternatives**:
- **手写 audit 在每个 view 里**：维护成本高 + 易漏，否决。
- **DB trigger 自动写**：跨 ORM/raw SQL 不一致，业务上下文缺失（不知道是哪个 operator），否决。
- **AOP 中间件全局拦截**：装饰器更显式，operator 一眼看出哪些是 audited，更好读，选定。
